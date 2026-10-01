# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Tests de segregacion por proveedor e integridad del archivo original.

Demuestran que el aislamiento es server-side (no depende de la UI): se verifica via
has_permission por registro, get_list (permission_query_conditions) y frappe.client.get
(acceso directo tipo API), ademas de la proteccion del File privado adjunto.
"""

import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from acg_customs.permissions import IMPORTER_ROLE, get_user_provider

PROV_GP = "Proveedor Uno"
PROV_GJ = "Proveedor Dos"
USER_GP = "acg_test_prov1@example.com"
USER_GJ = "acg_test_prov2@example.com"
USER_NOPROV = "acg_test_noprov@example.com"


def _ensure_role():
	if not frappe.db.exists("Role", IMPORTER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": IMPORTER_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def _ensure_provider(name):
	if not frappe.db.exists("ACG Order Provider", name):
		frappe.get_doc({"doctype": "ACG Order Provider", "provider_name": name}).insert(
			ignore_permissions=True
		)
	return name


def _ensure_user(email, provider=None):
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
	if provider is not None and not frappe.db.exists("ACG Order Provider User", email):
		frappe.get_doc({"doctype": "ACG Order Provider User", "user": email, "provider": provider}).insert(
			ignore_permissions=True
		)
	return email


def _make_private_excel():
	"""Crea un File privado con contenido unico. Devuelve (file_url, content_bytes)."""
	prev = frappe.session.user
	frappe.set_user("Administrator")
	try:
		content = b"xlsx-fake-" + frappe.generate_hash().encode()
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "orders.xlsx",
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)
		return f.file_url, content
	finally:
		frappe.set_user(prev)


def _create_import(user, file_url, provider=None):
	frappe.set_user(user)
	try:
		doc = frappe.get_doc({"doctype": "ACG Order Import", "excel_file": file_url})
		if provider is not None:
			doc.provider = provider
		doc.insert()
		return doc
	finally:
		frappe.set_user("Administrator")


class TestACGOrderImport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_role()
		cls.prov_gp = _ensure_provider(PROV_GP)
		cls.prov_gj = _ensure_provider(PROV_GJ)
		cls.user_gp = _ensure_user(USER_GP, cls.prov_gp)
		cls.user_gj = _ensure_user(USER_GJ, cls.prov_gj)
		cls.user_noprov = _ensure_user(USER_NOPROV, None)  # rol importador, SIN asociacion

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- helper ---
	def _import_for(self, user, provider=None):
		url, content = _make_private_excel()
		doc = _create_import(user, url, provider=provider)
		return doc, content

	# 1 + 2: cada usuario crea y ve su propia importacion
	def test_gp_creates_and_reads_own(self):
		doc, _ = self._import_for(self.user_gp)
		self.assertEqual(doc.provider, self.prov_gp)
		self.assertTrue(frappe.has_permission("ACG Order Import", "read", doc=doc.name, user=self.user_gp))

	def test_gj_creates_and_reads_own(self):
		doc, _ = self._import_for(self.user_gj)
		self.assertEqual(doc.provider, self.prov_gj)
		self.assertTrue(frappe.has_permission("ACG Order Import", "read", doc=doc.name, user=self.user_gj))

	# 3 + 4: aislamiento cruzado (has_permission por registro)
	def test_gp_cannot_read_gj(self):
		doc_gj, _ = self._import_for(self.user_gj)
		self.assertFalse(
			frappe.has_permission("ACG Order Import", "read", doc=doc_gj.name, user=self.user_gp)
		)

	def test_gj_cannot_read_gp(self):
		doc_gp, _ = self._import_for(self.user_gp)
		self.assertFalse(
			frappe.has_permission("ACG Order Import", "read", doc=doc_gp.name, user=self.user_gj)
		)

	# 5: el aislamiento aplica via get_list y acceso directo tipo API, no solo List View
	def test_isolation_via_server_api(self):
		from frappe.client import get as client_get

		doc_gp, _ = self._import_for(self.user_gp)
		doc_gj, _ = self._import_for(self.user_gj)

		frappe.set_user(self.user_gp)
		names = frappe.get_list("ACG Order Import", pluck="name")
		self.assertIn(doc_gp.name, names)
		self.assertNotIn(doc_gj.name, names)

		# Acceso directo tipo API al documento del otro proveedor -> PermissionError
		with self.assertRaises(frappe.PermissionError):
			client_get("ACG Order Import", doc_gj.name)

	# 6: no se puede falsificar provider al crear
	def test_cannot_spoof_provider_on_create(self):
		url, _ = _make_private_excel()
		frappe.set_user(self.user_gp)
		try:
			doc = frappe.get_doc(
				{
					"doctype": "ACG Order Import",
					"provider": self.prov_gj,  # intento de falsificacion
					"excel_file": url,
				}
			)
			with self.assertRaises(frappe.PermissionError):
				doc.insert()
		finally:
			frappe.set_user("Administrator")

	# 7: no se puede cambiar provider despues (set_only_once)
	def test_cannot_change_provider_after(self):
		doc, _ = self._import_for(self.user_gp)
		frappe.set_user("Administrator")
		doc.reload()
		doc.provider = self.prov_gj
		with self.assertRaises(frappe.CannotChangeConstantError):
			doc.save()

	# 8: el archivo queda privado y adjunto a la importacion
	def test_file_is_private_and_attached(self):
		doc, _ = self._import_for(self.user_gp)
		file_name = frappe.db.get_value(
			"File",
			{"file_url": doc.excel_file, "attached_to_doctype": "ACG Order Import"},
		)
		self.assertTrue(file_name)
		file_doc = frappe.get_doc("File", file_name)
		self.assertTrue(file_doc.is_private)
		self.assertEqual(file_doc.attached_to_name, doc.name)

	# 9: se conserva filename + SHA-256 sobre los bytes originales
	def test_filename_and_sha_preserved(self):
		doc, content = self._import_for(self.user_gp)
		self.assertEqual(doc.file_sha256, hashlib.sha256(content).hexdigest())
		# El filename conservado coincide con el del File real. Frappe puede deduplicar
		# el nombre al almacenar (p. ej. "orders.xlsx" -> "orders<hash>.xlsx"); lo
		# relevante para auditoria es que original_filename apunte al archivo real.
		file_name = frappe.db.get_value(
			"File",
			{"file_url": doc.excel_file, "attached_to_doctype": "ACG Order Import"},
			"file_name",
		)
		self.assertEqual(doc.original_filename, file_name)
		self.assertTrue(doc.original_filename.endswith(".xlsx"))

	# 10: System Manager audita ambos proveedores
	def test_system_manager_audits_both(self):
		doc_gp, _ = self._import_for(self.user_gp)
		doc_gj, _ = self._import_for(self.user_gj)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.has_permission("ACG Order Import", "read", doc=doc_gp.name))
		self.assertTrue(frappe.has_permission("ACG Order Import", "read", doc=doc_gj.name))

	# Extra: fail-closed si no hay asociacion inequivoca
	def test_fail_closed_without_association(self):
		self.assertIsNone(get_user_provider(self.user_noprov))
		url, _ = _make_private_excel()
		frappe.set_user(self.user_noprov)
		try:
			doc = frappe.get_doc({"doctype": "ACG Order Import", "excel_file": url})
			with self.assertRaises(frappe.PermissionError):
				doc.insert()
		finally:
			frappe.set_user("Administrator")

	# Extra: proteccion del File privado cruzado (defensa en profundidad)
	def test_cross_provider_file_download_denied(self):
		doc_gj, _ = self._import_for(self.user_gj)
		file_name = frappe.db.get_value(
			"File",
			{"file_url": doc_gj.excel_file, "attached_to_doctype": "ACG Order Import"},
		)
		self.assertFalse(frappe.has_permission("File", "read", doc=file_name, user=self.user_gp))

	# Extra: el usuario proveedor no puede tocar las asociaciones ni cambiar la suya
	def test_importer_cannot_touch_associations(self):
		# No puede leer el DocType de asociaciones
		self.assertFalse(frappe.has_permission("ACG Order Provider User", "read", user=self.user_gp))

		# No puede crear una asociacion
		frappe.set_user(self.user_gp)
		try:
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(
					{
						"doctype": "ACG Order Provider User",
						"user": USER_NOPROV,
						"provider": self.prov_gp,
					}
				).insert()
		finally:
			frappe.set_user("Administrator")

		# No puede cambiar su propia asociacion (cambiar de proveedor)
		assoc = frappe.get_doc("ACG Order Provider User", self.user_gp)
		frappe.set_user(self.user_gp)
		try:
			assoc.provider = self.prov_gj
			with self.assertRaises(frappe.PermissionError):
				assoc.save()
		finally:
			frappe.set_user("Administrator")
