# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del parser/preflight (perfil comercial_grid_v1) con workbooks sinteticos y datos
ficticios. La resolucion de sucursal usa ACG Order Branch Mapping (no Custom Field en
Address, no parseo de address_title). NINGUN nombre comercial real. No se crean Sales Orders.
"""

import io

import frappe
import openpyxl
from frappe.tests.utils import FrappeTestCase

from acg_customs.acg_customs.order_import import preflight
from acg_customs.permissions import IMPORTER_ROLE

CUSTOMER = "Cliente Preflight (Test)"
PROVIDER = "Proveedor Preflight"
PROVIDER2 = "Proveedor Preflight 2"
USER = "acg_pf_prov1@example.com"
USER2 = "acg_pf_prov2@example.com"

# Dataset canonico ficticio
PLU_A, ITEM_A = "9001", "PF-ITEM-A"
PLU_B, ITEM_B = "9002", "PF-ITEM-B"
PLU_DUP = "9999"  # resuelve a 2 items -> ambiguo
BRANCH_1, BRANCH_2 = "100", "200"
BRANCH_DISABLED = "300"  # mapping existe pero enabled=0 -> FAIL
BRANCH_DIRTY = "376"  # en el Excel aparece como "376 ." -> se normaliza a "376"


# --------------------------------------------------------------------------
# Construccion de workbook sintetico con la firma estructural del perfil
# --------------------------------------------------------------------------
def build_workbook(branches, products, quantities, *, sheet="PEDIDO COMERCIAL", header=None):
	"""branches: list[{code,name}] desde col O. products: list[{plu,articulo}] desde fila 7.
	quantities: dict[(prod_idx, branch_idx)] = valor."""
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = sheet
	hr = 6
	labels = header or {10: "PLU CIT", 11: "CLAVE CITY", 12: "CLAVE SAE", 13: "CLAVE CITY", 14: "ARTICULO"}
	for col, val in labels.items():
		ws.cell(row=hr, column=col, value=val)
	for i, b in enumerate(branches):
		c = 15 + i
		if b.get("code") is not None:
			ws.cell(row=hr - 2, column=c, value=b["code"])
		if b.get("name") is not None:
			ws.cell(row=hr, column=c, value=b["name"])
	for pi, p in enumerate(products):
		r = hr + 1 + pi
		if p.get("plu") is not None:
			ws.cell(row=r, column=10, value=p["plu"])
		ws.cell(row=r, column=14, value=p["articulo"])
	for (pi, bi), val in quantities.items():
		ws.cell(row=hr + 1 + pi, column=15 + bi, value=val)
	bio = io.BytesIO()
	wb.save(bio)
	return bio.getvalue()


def valid_workbook():
	return build_workbook(
		[{"code": BRANCH_1, "name": "Sucursal B1"}, {"code": BRANCH_2, "name": "Sucursal B2"}],
		[{"plu": PLU_A, "articulo": "ARTICULO A"}, {"plu": PLU_B, "articulo": "ARTICULO B"}],
		{(0, 0): 5, (1, 1): 3},
	)


def build_workbook_v2(branches, products, quantities, *, trailing=None):
	"""Layout del perfil pedido_grid_v2: hoja 'PEDIDO', encabezado fila 3 (D='TIENDAS',
	E='CLAVE'), clave de sucursal en fila 2, nombre en fila 3, sucursales desde col G(7),
	productos desde fila 7 (E=clave, F=articulo). `trailing` = columnas pegadas DESPUES del
	grid (p. ej. TOTAL + tablas auxiliares): list[(code, name, {prod_idx: qty})]."""
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "PEDIDO"
	hr = 3
	ws.cell(row=hr, column=4, value="TIENDAS")
	ws.cell(row=hr, column=5, value="CLAVE")
	for i, b in enumerate(branches):
		c = 7 + i
		if b.get("code") is not None:
			ws.cell(row=hr - 1, column=c, value=b["code"])
		if b.get("name") is not None:
			ws.cell(row=hr, column=c, value=b["name"])
	pr0 = 7
	for pi, p in enumerate(products):
		r = pr0 + pi
		if p.get("plu") is not None:
			ws.cell(row=r, column=5, value=p["plu"])
		ws.cell(row=r, column=6, value=p["articulo"])
	for (pi, bi), val in quantities.items():
		ws.cell(row=pr0 + pi, column=7 + bi, value=val)
	if trailing:
		base = 7 + len(branches)
		for j, (code, name, qmap) in enumerate(trailing):
			c = base + j
			if code is not None:
				ws.cell(row=hr - 1, column=c, value=code)
			if name is not None:
				ws.cell(row=hr, column=c, value=name)
			for pi, val in (qmap or {}).items():
				ws.cell(row=pr0 + pi, column=c, value=val)
	bio = io.BytesIO()
	wb.save(bio)
	return bio.getvalue()


# --------------------------------------------------------------------------
# Alta de datos ficticios (idempotente)
# --------------------------------------------------------------------------
def _ensure_role():
	if not frappe.db.exists("Role", IMPORTER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": IMPORTER_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def _ensure_customer():
	if not frappe.db.exists("Customer", CUSTOMER):
		leaf_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": CUSTOMER,
				"customer_type": "Company",
				"customer_group": leaf_group,
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)


def _ensure_address(title, *, customer=CUSTOMER, shipping=True, linked=True):
	atype = "Shipping" if shipping else "Billing"
	existing = frappe.db.get_value("Address", {"address_title": title, "address_type": atype})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": atype,
			"address_line1": "Calle Ficticia 1",
			"city": "Ciudad Test",
			"country": "Mexico",
			"links": [{"link_doctype": "Customer", "link_name": customer}] if linked else [],
		}
	).insert(ignore_permissions=True)
	return doc.name


def _ensure_mapping(customer, code, address, *, enabled=1, label=None):
	key = f"{customer}::{code}"
	existing = frappe.db.get_value("ACG Order Branch Mapping", {"mapping_key": key})
	if existing:
		frappe.db.set_value("ACG Order Branch Mapping", existing, "enabled", enabled)
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "ACG Order Branch Mapping",
			"customer": customer,
			"external_branch_code": code,
			"address": address,
			"enabled": enabled,
			"branch_label": label,
		}
	).insert(ignore_permissions=True)
	return doc.name


def _ensure_item(code, plu, customer=CUSTOMER):
	if frappe.db.exists("Item", code):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_group": "Products",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"customer_items": [{"customer_name": customer, "ref_code": plu}],
		}
	).insert(ignore_permissions=True)


def _ensure_provider(name, customer=None):
	if not frappe.db.exists("ACG Order Provider", name):
		frappe.get_doc({"doctype": "ACG Order Provider", "provider_name": name, "customer": customer}).insert(
			ignore_permissions=True
		)
	elif customer is not None:
		frappe.db.set_value("ACG Order Provider", name, "customer", customer)
	return name


def _ensure_user(email, provider):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(IMPORTER_ROLE)
	if not frappe.db.exists("ACG Order Provider User", email):
		frappe.get_doc({"doctype": "ACG Order Provider User", "user": email, "provider": provider}).insert(
			ignore_permissions=True
		)
	return email


def _make_import(provider, wb_bytes):
	prev = frappe.session.user
	frappe.set_user("Administrator")
	try:
		f = frappe.get_doc(
			{"doctype": "File", "file_name": "pedido.xlsx", "is_private": 1, "content": wb_bytes}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "ACG Order Import", "provider": provider, "excel_file": f.file_url})
		doc.insert(ignore_permissions=True)
		return doc
	finally:
		frappe.set_user(prev)


class TestPreflight(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_role()
		_ensure_customer()
		cls.addr_b1 = _ensure_address("Suc B1 Test")
		cls.addr_b2 = _ensure_address("Suc B2 Test")
		cls.addr_b3 = _ensure_address("Suc B3 Test")
		cls.addr_dirty = _ensure_address("Suc Dirty Test")
		cls.addr_billing = _ensure_address("Suc Billing Test", shipping=False)
		cls.addr_unlinked = _ensure_address("Suc Unlinked Test", linked=False)
		_ensure_mapping(CUSTOMER, BRANCH_1, cls.addr_b1, enabled=1)
		_ensure_mapping(CUSTOMER, BRANCH_2, cls.addr_b2, enabled=1)
		_ensure_mapping(CUSTOMER, BRANCH_DISABLED, cls.addr_b3, enabled=0)  # deshabilitado
		_ensure_mapping(CUSTOMER, BRANCH_DIRTY, cls.addr_dirty, enabled=1)  # clave "376"
		_ensure_item(ITEM_A, PLU_A)
		_ensure_item(ITEM_B, PLU_B)
		_ensure_item("PF-DUP-1", PLU_DUP)
		_ensure_item("PF-DUP-2", PLU_DUP)  # mismo ref_code -> ambiguo
		cls.provider = _ensure_provider(PROVIDER, customer=CUSTOMER)
		cls.provider2 = _ensure_provider(PROVIDER2, customer=CUSTOMER)
		cls.user = _ensure_user(USER, PROVIDER)
		cls.user2 = _ensure_user(USER2, PROVIDER2)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _run(self, wb_bytes, provider=PROVIDER):
		doc = _make_import(provider, wb_bytes)
		return doc, preflight.execute_preflight(doc)

	# 1 + 4 + 7: formato valido, sucursal y producto validos -> PASS
	def test_valid_format_passes(self):
		_, s = self._run(valid_workbook())
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["profile"], "comercial_grid_v1")
		self.assertEqual(s["branches_with_orders"], 2)
		self.assertEqual(s["branches_resolved"], 2)
		self.assertEqual(s["products_resolved"], 2)
		self.assertEqual(s["product_lines"], 2)
		self.assertEqual(s["total_units"], 8)
		self.assertEqual(s["product_resolution_key"], "plu_cit")

	# 2: hoja fuente faltante
	def test_missing_sheet_fails(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}],
			[{"plu": PLU_A, "articulo": "A"}],
			{(0, 0): 1},
			sheet="OTRA HOJA",
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertTrue(any("hoja fuente" in e.lower() for e in s["structural_errors"]))

	# 3 + 15: encabezado cambiado / formato no reconocido
	def test_changed_header_not_recognized(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}],
			[{"plu": PLU_A, "articulo": "A"}],
			{(0, 0): 1},
			header={10: "PLU CIT", 11: "X", 12: "Y", 13: "Z", 14: "OTRA COSA"},
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")

	# 5: sucursal sin mapping -> FAIL
	def test_branch_missing_fails(self):
		wb = build_workbook(
			[{"code": "55555", "name": "Inexistente"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 2}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual([b["code"] for b in s["branches_missing"]], ["55555"])

	# 6a: mapping deshabilitado -> FAIL (tratado como faltante)
	def test_branch_disabled_fails(self):
		wb = build_workbook(
			[{"code": BRANCH_DISABLED, "name": "Deshabilitada"}],
			[{"plu": PLU_A, "articulo": "A"}],
			{(0, 0): 2},
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual([b["code"] for b in s["branches_missing"]], [BRANCH_DISABLED])

	# 6b: duplicado/ambiguo bloqueado a nivel de datos (integridad del mapping)
	def test_duplicate_mapping_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "ACG Order Branch Mapping",
					"customer": CUSTOMER,
					"external_branch_code": BRANCH_1,  # ya existe -> ambiguo prohibido
					"address": self.addr_b2,
				}
			).insert(ignore_permissions=True)

	# 6c: mapping incoherente (Address no Shipping / no ligado) -> rechazado
	def test_mapping_integrity_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "ACG Order Branch Mapping",
					"customer": CUSTOMER,
					"external_branch_code": "801",
					"address": self.addr_billing,  # no Shipping
				}
			).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "ACG Order Branch Mapping",
					"customer": CUSTOMER,
					"external_branch_code": "802",
					"address": self.addr_unlinked,  # no ligado al customer
				}
			).insert(ignore_permissions=True)

	# 8: producto inexistente
	def test_product_missing_fails(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}], [{"plu": "123456", "articulo": "FANTASMA"}], {(0, 0): 2}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual([p["plu"] for p in s["products_missing"]], ["123456"])

	# 9: producto ambiguo
	def test_product_ambiguous_fails(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}], [{"plu": PLU_DUP, "articulo": "DUP"}], {(0, 0): 2}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual([p["plu"] for p in s["products_ambiguous"]], [PLU_DUP])
		self.assertEqual(len(s["products_ambiguous"][0]["candidates"]), 2)

	# 10: cantidad cero/vacia ignorada
	def test_zero_and_empty_ignored(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}, {"code": BRANCH_2, "name": "B2"}],
			[{"plu": PLU_A, "articulo": "A"}, {"plu": PLU_B, "articulo": "B"}],
			{(0, 0): 4, (0, 1): 0, (1, 0): None},  # solo 1 linea real
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["product_lines"], 1)
		self.assertEqual(s["branches_with_orders"], 1)
		self.assertEqual(s["total_units"], 4)

	# 11: cantidad invalida (texto) donde hay pedido -> FAIL
	def test_invalid_quantity_fails(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): "ABC"}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertTrue(any("no numerica" in e.lower() for e in s["structural_errors"]))

	# 12: varias sucursales con lineas distintas
	def test_multiple_branches_distinct_lines(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}, {"code": BRANCH_2, "name": "B2"}],
			[{"plu": PLU_A, "articulo": "A"}, {"plu": PLU_B, "articulo": "B"}],
			{(0, 0): 2, (0, 1): 7, (1, 1): 5},  # A@B1=2, A@B2=7, B@B2=5
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["product_lines"], 3)
		self.assertEqual(s["branches_with_orders"], 2)
		self.assertEqual(s["total_units"], 14)

	# 13: re-ejecucion determinista (mismo archivo/config -> mismo resumen)
	def test_deterministic_rerun(self):
		doc, s1 = self._run(valid_workbook())
		s2 = preflight.execute_preflight(doc)
		self.assertEqual(frappe.as_json(s1), frappe.as_json(s2))
		self.assertEqual(s2["file_sha256"], doc.file_sha256)

	# 14: usuario de otro proveedor NO puede ejecutar preflight
	def test_cross_provider_preflight_denied(self):
		doc = _make_import(PROVIDER, valid_workbook())
		frappe.set_user(self.user2)
		try:
			with self.assertRaises(frappe.PermissionError):
				preflight.run_preflight(doc.name)
		finally:
			frappe.set_user("Administrator")

	# run_preflight persiste status + summary
	def test_run_preflight_persists(self):
		doc = _make_import(PROVIDER, valid_workbook())
		frappe.set_user(self.user)
		try:
			res = preflight.run_preflight(doc.name)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(res["result"], "PASS")
		doc.reload()
		self.assertEqual(doc.status, "Preflight Passed")
		self.assertTrue(doc.preflight_summary)

	# Regla 1: columna agregada (r4 contiene TOTAL) se ignora (no OV, no error)
	def test_total_aggregate_column_ignored(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}, {"code": "TOTAL1", "name": "Subtotal"}],
			[{"plu": PLU_A, "articulo": "A"}, {"plu": PLU_B, "articulo": "B"}],
			{(0, 0): 6, (0, 1): 99, (1, 1): 99},  # col agregada con "pedidos" -> ignorada
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["branches_with_orders"], 1)  # solo B1
		self.assertEqual(s["total_units"], 6)  # el agregado no suma
		self.assertEqual(s["structural_errors"], [])

	# Regla 2: clave sucia "376 ." se normaliza a "376" y resuelve
	def test_dirty_branch_code_normalized(self):
		wb = build_workbook(
			[{"code": "376 .", "name": "Sucia"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 4}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["branches_with_orders"], 1)
		self.assertEqual(s["branches_resolved"], 1)

	# Regla 3a: nombre sin clave CON pedido -> FAIL
	def test_nameonly_with_orders_fails(self):
		wb = build_workbook(
			[{"name": "Placeholder Sin Clave"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 3}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "FAIL")
		self.assertTrue(any("sin clave de sucursal" in e.lower() for e in s["structural_errors"]))

	# Regla 3b: nombre sin clave SIN pedido -> ignorar con warning (PASS)
	def test_nameonly_without_orders_passes(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}, {"name": "Placeholder Sin Clave"}],
			[{"plu": PLU_A, "articulo": "A"}],
			{(0, 0): 2},  # solo B1 trae pedido; la placeholder queda vacia
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertTrue(s["warnings"])

	# --- Perfil pedido_grid_v2 (segundo proveedor) ---
	# v2: formato valido -> PASS, perfil y clave de resolucion correctos
	def test_v2_valid_passes(self):
		wb = build_workbook_v2(
			[{"code": BRANCH_1, "name": "B1"}, {"code": BRANCH_2, "name": "B2"}],
			[{"plu": PLU_A, "articulo": "A"}, {"plu": PLU_B, "articulo": "B"}],
			{(0, 0): 5, (1, 1): 3},
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["profile"], "pedido_grid_v2")
		self.assertEqual(s["source_sheet"], "PEDIDO")
		self.assertEqual(s["product_resolution_key"], "clave")
		self.assertEqual(s["branches_with_orders"], 2)
		self.assertEqual(s["total_units"], 8)

	# v2: corta en la primera columna TOTAL; las tablas auxiliares pegadas a la derecha se ignoran
	def test_v2_stops_at_total_ignores_trailing(self):
		wb = build_workbook_v2(
			[{"code": BRANCH_1, "name": "B1"}],
			[{"plu": PLU_A, "articulo": "A"}],
			{(0, 0): 5},
			trailing=[
				("TOTAL", "Gran Total", {0: 999}),  # columna agregada -> borde del grid
				("25", "GARBAGE", {0: 50}),  # tabla auxiliar posterior -> ignorada
			],
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["branches_with_orders"], 1)
		self.assertEqual(s["total_units"], 5)  # 999 y 50 ignorados
		self.assertEqual(s["structural_errors"], [])

	# v2: clave sucia "376 ." se normaliza a "376"
	def test_v2_dirty_code_normalized(self):
		wb = build_workbook_v2(
			[{"code": "376 .", "name": "Sucia"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 4}
		)
		_, s = self._run(wb)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["branches_resolved"], 1)

	# config faltante: proveedor sin customer -> FAIL
	def test_missing_customer_config_fails(self):
		_ensure_provider("Proveedor Sin Customer", customer=None)
		frappe.db.set_value("ACG Order Provider", "Proveedor Sin Customer", "customer", None)
		_, s = self._run(valid_workbook(), provider="Proveedor Sin Customer")
		self.assertEqual(s["result"], "FAIL")
		self.assertTrue(any("customer" in e.lower() for e in s["structural_errors"]))
