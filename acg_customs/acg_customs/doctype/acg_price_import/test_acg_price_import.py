# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del importador semanal de precios (ACG Price Import), datos ficticios.
Resolucion CODIGO -> Item por Item Customer Detail.ref_code. Sin nombres reales."""

import io
from unittest.mock import patch

import frappe
import openpyxl
from frappe.tests.utils import FrappeTestCase

from acg_customs.acg_customs.doctype.acg_order_import.test_preflight import (
	CUSTOMER,
	ITEM_A,
	ITEM_B,
	PLU_A,
	PLU_B,
	PLU_DUP,
	_ensure_customer,
	_ensure_item,
	_ensure_role,
)
from acg_customs.acg_customs.price_import import service

PRICE_LIST = "ACG Price Test List"
SMM_USER = "acg_price_smm@example.com"
IMPORTER_USER = "acg_price_importer@example.com"


def build_price_wb(rows, *, header=("CODIGO", "DESCRIPCION", "COSTO"), sheet="Hoja1"):
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = sheet
	for c, h in enumerate(header, start=1):
		ws.cell(row=1, column=c, value=h)
	for i, (code, desc, cost) in enumerate(rows, start=2):
		if code is not None:
			ws.cell(row=i, column=1, value=code)
		if desc is not None:
			ws.cell(row=i, column=2, value=desc)
		if cost is not None:
			ws.cell(row=i, column=3, value=cost)
	bio = io.BytesIO()
	wb.save(bio)
	return bio.getvalue()


def build_two_block_wb(left_rows, right_rows, *, sheet="Hoja1"):
	"""Hoja con DOS bloques CODIGO|DESCRIPCION|COSTO lado a lado: A-C y E-G
	(col 4 vacia de separacion), como el archivo real del cliente."""
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = sheet
	for base in (1, 5):  # A y E
		ws.cell(row=1, column=base, value="CODIGO")
		ws.cell(row=1, column=base + 1, value="DESCRIPCION")
		ws.cell(row=1, column=base + 2, value="COSTO")
	for i, (code, desc, cost) in enumerate(left_rows, start=2):
		ws.cell(row=i, column=1, value=code)
		ws.cell(row=i, column=2, value=desc)
		ws.cell(row=i, column=3, value=cost)
	for i, (code, desc, cost) in enumerate(right_rows, start=2):
		ws.cell(row=i, column=5, value=code)
		ws.cell(row=i, column=6, value=desc)
		ws.cell(row=i, column=7, value=cost)
	bio = io.BytesIO()
	wb.save(bio)
	return bio.getvalue()


def _ensure_price_list():
	if not frappe.db.exists("Price List", PRICE_LIST):
		frappe.get_doc(
			{"doctype": "Price List", "price_list_name": PRICE_LIST, "selling": 1, "currency": "MXN"}
		).insert(ignore_permissions=True)


def _ensure_user(email, role):
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
	frappe.get_doc("User", email).add_roles(role)
	return email


def _make_import(wb_bytes):
	prev = frappe.session.user
	frappe.set_user("Administrator")
	try:
		f = frappe.get_doc(
			{"doctype": "File", "file_name": "costos.xlsx", "is_private": 1, "content": wb_bytes}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc({"doctype": "ACG Price Import", "customer": CUSTOMER, "excel_file": f.file_url})
		doc.insert(ignore_permissions=True)
		return doc
	finally:
		frappe.set_user(prev)


class TestPriceImport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_role()
		_ensure_customer()
		_ensure_price_list()
		frappe.db.set_value("Customer", CUSTOMER, "default_price_list", PRICE_LIST)
		_ensure_item(ITEM_A, PLU_A)
		_ensure_item(ITEM_B, PLU_B)
		_ensure_item("PF-DUP-1", PLU_DUP)
		_ensure_item("PF-DUP-2", PLU_DUP)  # mismo ref_code -> ambiguo
		cls.smm = _ensure_user(SMM_USER, "Sales Master Manager")
		cls.importer = _ensure_user(IMPORTER_USER, "ACG Order Importer")

	def setUp(self):
		# aislar Item Prices y exclusiones entre tests
		for n in frappe.get_all("Item Price", filters={"price_list": PRICE_LIST}, pluck="name"):
			frappe.delete_doc("Item Price", n, ignore_permissions=True, force=True)
		for n in frappe.get_all("ACG External Code Exclusion", filters={"customer": CUSTOMER}, pluck="name"):
			frappe.delete_doc("ACG External Code Exclusion", n, ignore_permissions=True, force=True)

	def _exclude(self, code, enabled=1):
		return frappe.get_doc(
			{
				"doctype": "ACG External Code Exclusion",
				"customer": CUSTOMER,
				"external_code": code,
				"enabled": enabled,
				"reason": "Fuera de catalogo (test)",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _pf(self, wb):
		doc = _make_import(wb)
		s = service.run_preflight(doc.name)
		doc.reload()
		return doc, s

	# 1. archivo valido -> PASS, acciones new
	def test_valid_passes(self):
		doc, s = self._pf(build_price_wb([(PLU_A, "ART A", 10.0), (PLU_B, "ART B", 20.0)]))
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(doc.status, "Preflight Passed")
		self.assertEqual(s["resolved"], 2)
		self.assertEqual(s["new"], 2)
		self.assertEqual({ln.action for ln in doc.lines}, {"new"})

	# 2. estructura invalida -> FAIL
	def test_bad_structure_fails(self):
		wb = build_price_wb([("x", "y", 1)], header=("A", "B", "C"))
		_, s = self._pf(wb)
		self.assertEqual(s["result"], "FAIL")

	# 3. CODIGO vacio -> FAIL
	def test_empty_code_fails(self):
		_, s = self._pf(build_price_wb([(None, "Sin codigo", 5.0)]))
		self.assertEqual(s["result"], "FAIL")

	# 4. COSTO invalido / <=0 -> FAIL
	def test_invalid_cost_fails(self):
		_, s = self._pf(build_price_wb([(PLU_A, "A", "ABC")]))
		self.assertEqual(s["result"], "FAIL")
		_, s2 = self._pf(build_price_wb([(PLU_A, "A", 0)]))
		self.assertEqual(s2["result"], "FAIL")
		_, s3 = self._pf(build_price_wb([(PLU_A, "A", -5)]))
		self.assertEqual(s3["result"], "FAIL")

	# 5a. duplicado conflictivo -> FAIL
	def test_duplicate_conflict_fails(self):
		_, s = self._pf(build_price_wb([(PLU_A, "A", 10.0), (PLU_A, "A", 11.0)]))
		self.assertEqual(s["result"], "FAIL")

	# 5b. duplicado mismo costo -> PASS (colapsado, warning)
	def test_duplicate_same_cost_passes(self):
		_, s = self._pf(build_price_wb([(PLU_A, "A", 10.0), (PLU_A, "A", 10.0)]))
		self.assertEqual(s["result"], "PASS")
		self.assertTrue(s["warnings"])
		self.assertEqual(s["resolved"], 1)

	# 6. Item inexistente -> FAIL
	def test_item_missing_fails(self):
		_, s = self._pf(build_price_wb([("999999", "Fantasma", 5.0)]))
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual(s["unresolved"], 1)

	# 7. Item ambiguo -> FAIL
	def test_item_ambiguous_fails(self):
		_, s = self._pf(build_price_wb([(PLU_DUP, "Dup", 5.0)]))
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual(s["unresolved"], 1)

	# 8. new / changed / unchanged + apply crea/actualiza Item Price
	def test_new_changed_unchanged(self):
		doc, _ = self._pf(build_price_wb([(PLU_A, "A", 10.0)]))
		r = service.apply_prices(doc.name)
		self.assertEqual(r["new"], 1)
		self.assertEqual(
			frappe.db.get_value(
				"Item Price", {"item_code": ITEM_A, "price_list": PRICE_LIST}, "price_list_rate"
			),
			10.0,
		)
		# changed
		doc2, _s2 = self._pf(build_price_wb([(PLU_A, "A", 12.0)]))
		self.assertEqual({ln.action for ln in doc2.lines}, {"changed"})
		self.assertEqual(doc2.lines[0].previous_rate, 10.0)
		r2 = service.apply_prices(doc2.name)
		self.assertEqual(r2["changed"], 1)
		self.assertEqual(
			frappe.db.get_value(
				"Item Price", {"item_code": ITEM_A, "price_list": PRICE_LIST}, "price_list_rate"
			),
			12.0,
		)
		# unchanged
		doc3, _ = self._pf(build_price_wb([(PLU_A, "A", 12.0)]))
		self.assertEqual({ln.action for ln in doc3.lines}, {"unchanged"})
		r3 = service.apply_prices(doc3.name)
		self.assertEqual((r3["new"], r3["changed"]), (0, 0))

	# 9. rollback total ante error
	def test_rollback_on_error(self):
		doc, _ = self._pf(build_price_wb([(PLU_A, "A", 10.0), (PLU_B, "B", 20.0)]))
		before = frappe.db.count("Item Price", {"price_list": PRICE_LIST})
		with patch.object(service, "_persist", side_effect=frappe.ValidationError("boom")):
			with self.assertRaises(frappe.ValidationError):
				service.apply_prices(doc.name)
		self.assertEqual(frappe.db.count("Item Price", {"price_list": PRICE_LIST}), before)
		doc.reload()
		self.assertNotEqual(doc.status, "Applied")

	# 10. idempotencia: re-aplicar -> noop
	def test_idempotent(self):
		doc, _ = self._pf(build_price_wb([(PLU_A, "A", 10.0)]))
		service.apply_prices(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Applied")
		r2 = service.apply_prices(doc.name)
		self.assertTrue(r2["idempotent"])
		self.assertEqual(frappe.db.count("Item Price", {"item_code": ITEM_A, "price_list": PRICE_LIST}), 1)

	# 11. permisos: Sales Master Manager puede; ACG Order Importer no
	def test_permissions(self):
		doc = _make_import(build_price_wb([(PLU_A, "A", 10.0)]))
		frappe.set_user(self.smm)
		try:
			s = service.run_preflight(doc.name)  # no debe lanzar
			self.assertIn(s["result"], ("PASS", "FAIL"))
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(self.importer)
		try:
			with self.assertRaises(frappe.PermissionError):
				service.run_preflight(doc.name)
		finally:
			frappe.set_user("Administrator")

	# 12. exclusion activa -> skipped y el preflight NO falla por ese codigo
	def test_excluded_code_skipped_passes(self):
		self._exclude("888888")
		doc, s = self._pf(build_price_wb([(PLU_A, "A", 10.0), ("888888", "Fuera", 9.9)]))
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["skipped"], 1)
		self.assertEqual(s["resolved"], 1)
		actions = {ln.code: ln.action for ln in doc.lines}
		self.assertEqual(actions["888888"], "skipped")
		self.assertEqual(actions[PLU_A], "new")
		# la linea omitida conserva code/description/new_rate
		skipped = next(ln for ln in doc.lines if ln.code == "888888")
		self.assertEqual(skipped.description, "Fuera")
		self.assertEqual(skipped.new_rate, 9.9)
		self.assertIsNone(skipped.item)

	# 13. codigo excluido nunca crea Item Price
	def test_excluded_never_creates_item_price(self):
		self._exclude("888888")
		doc, _ = self._pf(build_price_wb([(PLU_A, "A", 10.0), ("888888", "Fuera", 9.9)]))
		service.apply_prices(doc.name)
		self.assertEqual(frappe.db.count("Item Price", {"price_list": PRICE_LIST}), 1)
		self.assertEqual(
			frappe.db.get_value(
				"Item Price", {"item_code": ITEM_A, "price_list": PRICE_LIST}, "price_list_rate"
			),
			10.0,
		)

	# 14. no resuelto SIN exclusion -> sigue FAIL
	def test_unresolved_without_exclusion_fails(self):
		_, s = self._pf(build_price_wb([("888888", "Fuera", 9.9)]))
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual(s["unresolved"], 1)
		self.assertEqual(s["skipped"], 0)

	# 15. exclusion DESHABILITADA -> sigue FAIL
	def test_disabled_exclusion_fails(self):
		self._exclude("888888", enabled=0)
		_, s = self._pf(build_price_wb([("888888", "Fuera", 9.9)]))
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual(s["unresolved"], 1)
		self.assertEqual(s["skipped"], 0)

	# 16. exclusion no oculta OTROS errores reales
	def test_exclusion_does_not_hide_other_errors(self):
		self._exclude("888888")
		_, s = self._pf(build_price_wb([("888888", "Fuera", 9.9), ("777777", "Otro", 5.0)]))
		self.assertEqual(s["result"], "FAIL")
		self.assertEqual(s["skipped"], 1)
		self.assertEqual(s["unresolved"], 1)

	# 17. summary siempre incluye skipped
	def test_summary_has_skipped_key(self):
		_, s = self._pf(build_price_wb([(PLU_A, "A", 10.0)]))
		self.assertIn("skipped", s)
		self.assertEqual(s["skipped"], 0)

	# 18. PARSER: hoja con DOS bloques de columnas (A-C y E-G) lee AMBOS
	def test_parser_lee_dos_bloques(self):
		from acg_customs.acg_customs.price_import import parser

		wb_bytes = build_two_block_wb(
			left_rows=[("1001", "IZQ UNO", 10.0), ("1002", "IZQ DOS", 20.0)],
			right_rows=[("2001", "DER UNO", 30.0), ("2002", "DER DOS", 40.0)],
		)
		wb = openpyxl.load_workbook(io.BytesIO(wb_bytes), data_only=True)
		p = parser.parse_workbook(wb)
		self.assertEqual(p["blocks"], 2)
		codes = {r["code"] for r in p["rows"]}
		# los 2 del bloque izquierdo Y los 2 del derecho
		self.assertEqual(codes, {"1001", "1002", "2001", "2002"})

	# 19. INTEGRACION: preflight resuelve productos de AMBOS bloques
	def test_preflight_resuelve_ambos_bloques(self):
		# PLU_A en bloque izquierdo, PLU_B en bloque derecho
		doc, s = self._pf(
			build_two_block_wb(
				left_rows=[(PLU_A, "ART A", 11.0)],
				right_rows=[(PLU_B, "ART B", 22.0)],
			)
		)
		self.assertEqual(s["result"], "PASS")
		self.assertEqual(s["resolved"], 2)
		by_item = {ln.item: ln.new_rate for ln in doc.lines}
		self.assertEqual(by_item.get(ITEM_A), 11.0)
		self.assertEqual(by_item.get(ITEM_B), 22.0)
