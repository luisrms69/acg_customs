# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests del DocType de exclusiones por (customer, external_code). Datos ficticios."""

import frappe
from frappe.tests.utils import FrappeTestCase

from acg_customs.acg_customs.doctype.acg_external_code_exclusion.acg_external_code_exclusion import (
	is_excluded,
)
from acg_customs.acg_customs.doctype.acg_order_import.test_preflight import (
	CUSTOMER,
	_ensure_customer,
	_ensure_role,
)
from acg_customs.acg_customs.doctype.acg_price_import.test_acg_price_import import (
	IMPORTER_USER,
	SMM_USER,
	_ensure_user,
)

DT = "ACG External Code Exclusion"


def _new(customer, code, enabled=1):
	return frappe.get_doc({"doctype": DT, "customer": customer, "external_code": code, "enabled": enabled})


class TestExternalCodeExclusion(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_role()
		_ensure_customer()
		cls.smm = _ensure_user(SMM_USER, "Sales Master Manager")
		cls.importer = _ensure_user(IMPORTER_USER, "ACG Order Importer")

	def setUp(self):
		for n in frappe.get_all(DT, filters={"customer": CUSTOMER}, pluck="name"):
			frappe.delete_doc(DT, n, ignore_permissions=True, force=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	# unicidad (customer, external_code)
	def test_duplicate_fails(self):
		_new(CUSTOMER, "55555").insert(ignore_permissions=True)
		with self.assertRaises(frappe.DuplicateEntryError):
			_new(CUSTOMER, "55555").insert(ignore_permissions=True)

	# mismo codigo, distinto customer -> permitido (no hay colision)
	def test_same_code_other_customer_ok(self):
		_new(CUSTOMER, "55555").insert(ignore_permissions=True)
		group, territory = frappe.db.get_value("Customer", CUSTOMER, ["customer_group", "territory"])
		if not frappe.db.exists("Customer", "ACG Other Cust"):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": "ACG Other Cust",
					"customer_group": group,
					"territory": territory,
				}
			).insert(ignore_permissions=True)
		d = _new("ACG Other Cust", "55555").insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc(DT, d.name, ignore_permissions=True, force=True))
		self.assertTrue(d.name)

	# is_excluded respeta enabled
	def test_is_excluded_enabled_flag(self):
		_new(CUSTOMER, "55555", enabled=1).insert(ignore_permissions=True)
		self.assertTrue(is_excluded(CUSTOMER, "55555"))
		self.assertFalse(is_excluded(CUSTOMER, "99999"))

	def test_is_excluded_disabled(self):
		_new(CUSTOMER, "55555", enabled=0).insert(ignore_permissions=True)
		self.assertFalse(is_excluded(CUSTOMER, "55555"))

	# codigo se normaliza (strip) y is_excluded tolera espacios
	def test_code_stripped(self):
		d = _new(CUSTOMER, "  55555  ").insert(ignore_permissions=True)
		self.assertEqual(d.external_code, "55555")
		self.assertTrue(is_excluded(CUSTOMER, " 55555 "))

	# permisos: SMM puede crear; ACG Order Importer no
	def test_permissions(self):
		frappe.set_user(self.smm)
		try:
			d = _new(CUSTOMER, "55555").insert()
			self.assertTrue(d.name)
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(self.importer)
		try:
			with self.assertRaises(frappe.PermissionError):
				_new(CUSTOMER, "66666").insert()
		finally:
			frappe.set_user("Administrator")
