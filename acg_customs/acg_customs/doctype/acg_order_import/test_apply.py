# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests de creacion de Sales Orders desde ACG Order Import (perfil v1), con datos
ficticios. Una OV por sucursal; idempotente; transaccional (rollback); segregado."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from acg_customs.acg_customs.doctype.acg_order_import.test_preflight import (
	BRANCH_1,
	BRANCH_2,
	CUSTOMER,
	ITEM_A,
	ITEM_B,
	PLU_A,
	PLU_B,
	PROVIDER,
	PROVIDER2,
	USER,
	USER2,
	_ensure_address,
	_ensure_customer,
	_ensure_item,
	_ensure_mapping,
	_ensure_provider,
	_ensure_role,
	_ensure_user,
	_make_import,
	build_workbook,
)
from acg_customs.acg_customs.order_import import apply, preflight
from acg_customs.setup.install import PROVIDER_DIMENSION_FIELD, ensure_provider_dimension

COMPANY = "_Test Company"
PRICE_LIST = "ACG Test Price List"
RATE_A = 10.0
RATE_B = 20.0
PLU_NP, ITEM_NP = "9100", "PF-ITEM-NOPRICE"  # resuelve por ICD pero SIN Item Price


def _ensure_price_list(name):
	if not frappe.db.exists("Price List", name):
		currency = frappe.get_cached_value("Company", COMPANY, "default_currency")
		frappe.get_doc(
			{"doctype": "Price List", "price_list_name": name, "selling": 1, "currency": currency}
		).insert(ignore_permissions=True)
	return name


def _ensure_item_price(item_code, rate, price_list=PRICE_LIST):
	if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)


def _wb_one():
	return build_workbook([{"code": BRANCH_1, "name": "B1"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 5})


def _wb_two():
	# B1: A=5 ; B2: A=2, B=3
	return build_workbook(
		[{"code": BRANCH_1, "name": "B1"}, {"code": BRANCH_2, "name": "B2"}],
		[{"plu": PLU_A, "articulo": "A"}, {"plu": PLU_B, "articulo": "B"}],
		{(0, 0): 5, (0, 1): 2, (1, 1): 3},
	)


class TestApply(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_role()
		_ensure_customer()
		cls.addr_b1 = _ensure_address("Suc B1 Test")
		cls.addr_b2 = _ensure_address("Suc B2 Test")
		_ensure_mapping(CUSTOMER, BRANCH_1, cls.addr_b1, enabled=1)
		_ensure_mapping(CUSTOMER, BRANCH_2, cls.addr_b2, enabled=1)
		_ensure_item(ITEM_A, PLU_A)
		_ensure_item(ITEM_B, PLU_B)
		_ensure_item(ITEM_NP, PLU_NP)  # resuelve por ICD pero sin Item Price
		# Price List + asociacion nativa al Customer + Item Prices (sinteticos)
		_ensure_price_list(PRICE_LIST)
		frappe.db.set_value("Customer", CUSTOMER, "default_price_list", PRICE_LIST)
		_ensure_item_price(ITEM_A, RATE_A)
		_ensure_item_price(ITEM_B, RATE_B)
		# ITEM_NP a proposito SIN Item Price
		_ensure_provider(PROVIDER, customer=CUSTOMER)
		_ensure_provider(PROVIDER2, customer=CUSTOMER)
		frappe.db.set_value("ACG Order Provider", PROVIDER, "company", COMPANY)
		frappe.db.set_value("ACG Order Provider", PROVIDER2, "company", COMPANY)
		ensure_provider_dimension()  # Accounting Dimension de proveedor (campo en Sales Order)
		cls.user = _ensure_user(USER, PROVIDER)
		cls.user2 = _ensure_user(USER2, PROVIDER2)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _passed_import(self, wb, provider=PROVIDER):
		doc = _make_import(provider, wb)
		preflight.run_preflight(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Preflight Passed")
		return doc

	def _so_branch_map(self, doc):
		doc.reload()
		return {r.external_branch_code: r.sales_order for r in doc.sales_orders}

	# 1 sucursal -> 1 OV, con Customer/Company/Shipping/Item/qty correctos
	def test_one_branch_one_so(self):
		doc = self._passed_import(_wb_one())
		res = apply.create_sales_orders(doc.name)
		self.assertEqual(len(res["created"]), 1)
		doc.reload()
		self.assertEqual(doc.status, "Applied")
		self.assertEqual(len(doc.sales_orders), 1)

		row = doc.sales_orders[0]
		self.assertEqual(row.external_branch_code, BRANCH_1)
		self.assertEqual(row.address, self.addr_b1)
		so = frappe.get_doc("Sales Order", row.sales_order)
		self.assertEqual(so.customer, CUSTOMER)
		self.assertEqual(so.company, COMPANY)
		self.assertEqual(so.shipping_address_name, self.addr_b1)
		self.assertEqual(len(so.items), 1)
		self.assertEqual(so.items[0].item_code, ITEM_A)
		self.assertEqual(so.items[0].qty, 5)
		# Rate obtenido por pricing nativo desde la Price List (no rate=0)
		self.assertEqual(so.items[0].rate, RATE_A)
		self.assertEqual(so.items[0].amount, RATE_A * 5)
		# Accounting Dimension de proveedor poblada en la OV
		self.assertEqual(so.get(PROVIDER_DIMENSION_FIELD), PROVIDER)

	# varias sucursales -> varias OVs, lineas correctas por sucursal
	def test_multiple_branches(self):
		doc = self._passed_import(_wb_two())
		res = apply.create_sales_orders(doc.name)
		self.assertEqual(len(res["created"]), 2)
		mapping = self._so_branch_map(doc)
		self.assertEqual(set(mapping), {BRANCH_1, BRANCH_2})

		so1 = frappe.get_doc("Sales Order", mapping[BRANCH_1])
		self.assertEqual({(i.item_code, i.qty) for i in so1.items}, {(ITEM_A, 5)})
		self.assertEqual(so1.shipping_address_name, self.addr_b1)

		so2 = frappe.get_doc("Sales Order", mapping[BRANCH_2])
		self.assertEqual({(i.item_code, i.qty) for i in so2.items}, {(ITEM_A, 2), (ITEM_B, 3)})
		self.assertEqual(so2.shipping_address_name, self.addr_b2)

	# auditabilidad import -> SO
	def test_import_to_so_auditable(self):
		doc = self._passed_import(_wb_two())
		apply.create_sales_orders(doc.name)
		doc.reload()
		for row in doc.sales_orders:
			self.assertTrue(row.external_branch_code)
			self.assertTrue(row.address)
			self.assertTrue(frappe.db.exists("Sales Order", row.sales_order))

	# preflight FAIL no permite crear
	def test_preflight_fail_blocks(self):
		wb = build_workbook(
			[{"code": "55555", "name": "SinMapping"}], [{"plu": PLU_A, "articulo": "A"}], {(0, 0): 2}
		)
		doc = _make_import(PROVIDER, wb)
		preflight.run_preflight(doc.name)
		doc.reload()
		self.assertEqual(doc.status, "Preflight Failed")
		with self.assertRaises(frappe.ValidationError):
			apply.create_sales_orders(doc.name)
		doc.reload()
		self.assertEqual(len(doc.sales_orders), 0)

	# reejecucion no duplica OVs
	def test_rerun_is_idempotent(self):
		doc = self._passed_import(_wb_two())
		first = apply.create_sales_orders(doc.name)
		self.assertEqual(len(first["created"]), 2)
		second = apply.create_sales_orders(doc.name)
		self.assertTrue(second["idempotent"])
		self.assertEqual(second["created"], [])
		doc.reload()
		self.assertEqual(len(doc.sales_orders), 2)  # sin duplicados

	# error intermedio -> rollback del conjunto (ninguna OV, status sin Applied)
	def test_rollback_on_error(self):
		doc = self._passed_import(_wb_two())
		before = frappe.db.count("Sales Order")
		calls = {"n": 0}
		original = apply._create_sales_order

		def flaky(*args, **kwargs):
			calls["n"] += 1
			if calls["n"] >= 2:
				raise frappe.ValidationError("fallo simulado en la 2a sucursal")
			return original(*args, **kwargs)

		with patch.object(apply, "_create_sales_order", side_effect=flaky):
			with self.assertRaises(frappe.ValidationError):
				apply.create_sales_orders(doc.name)

		doc.reload()
		self.assertNotEqual(doc.status, "Applied")
		self.assertEqual(len(doc.sales_orders), 0)
		self.assertEqual(frappe.db.count("Sales Order"), before)  # rollback total

	# Accounting Dimension de proveedor presente en TODAS las OVs generadas
	def test_provider_dimension_on_all_sales_orders(self):
		self.assertTrue(frappe.get_meta("Sales Order").has_field(PROVIDER_DIMENSION_FIELD))
		doc = self._passed_import(_wb_two())
		apply.create_sales_orders(doc.name)
		doc.reload()
		for row in doc.sales_orders:
			so = frappe.get_doc("Sales Order", row.sales_order)
			self.assertEqual(so.get(PROVIDER_DIMENSION_FIELD), PROVIDER)

	# Precios por sucursal correctos (pricing nativo, varias lineas)
	def test_rates_from_price_list(self):
		doc = self._passed_import(_wb_two())
		apply.create_sales_orders(doc.name)
		mapping = self._so_branch_map(doc)
		so2 = frappe.get_doc("Sales Order", mapping[BRANCH_2])  # A=2, B=3
		rates = {i.item_code: i.rate for i in so2.items}
		self.assertEqual(rates[ITEM_A], RATE_A)
		self.assertEqual(rates[ITEM_B], RATE_B)
		self.assertEqual(so2.grand_total, RATE_A * 2 + RATE_B * 3)

	# Fail-closed por precio faltante: Item resoluble pero SIN Item Price -> no se crean OVs
	def test_missing_price_fails_closed(self):
		wb = build_workbook(
			[{"code": BRANCH_1, "name": "B1"}], [{"plu": PLU_NP, "articulo": "SIN PRECIO"}], {(0, 0): 4}
		)
		doc = self._passed_import(wb)  # preflight PASS (resuelve por ICD)
		before = frappe.db.count("Sales Order")
		with self.assertRaises(frappe.ValidationError):
			apply.create_sales_orders(doc.name)
		doc.reload()
		self.assertNotEqual(doc.status, "Applied")
		self.assertEqual(len(doc.sales_orders), 0)
		self.assertEqual(frappe.db.count("Sales Order"), before)  # rollback total

	# proveedor cruzado no puede aplicar importacion ajena
	def test_cross_provider_cannot_apply(self):
		doc = self._passed_import(_wb_one())  # pertenece a PROVIDER
		frappe.set_user(self.user2)
		try:
			with self.assertRaises(frappe.PermissionError):
				apply.create_sales_orders(doc.name)
		finally:
			frappe.set_user("Administrator")
