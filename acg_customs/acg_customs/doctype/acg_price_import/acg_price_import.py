# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ACGPriceImport(Document):
	def before_insert(self):
		if not self.price_list:
			self.price_list = frappe.db.get_value("Customer", self.customer, "default_price_list")
		if not self.price_list:
			frappe.throw(
				_("El Customer {0} no tiene lista de precios (default_price_list) configurada.").format(
					self.customer
				),
				frappe.ValidationError,
			)
		self.uploaded_by = frappe.session.user
		self.uploaded_on = now_datetime()
		self.status = self.status or "Uploaded"

	def validate(self):
		self._process_source_file()

	def _process_source_file(self):
		if not self.excel_file:
			frappe.throw(_("Debe adjuntar el archivo de precios."), frappe.MandatoryError)
		name = frappe.db.get_value("File", {"file_url": self.excel_file})
		file_doc = frappe.get_doc("File", name) if name else None
		if not file_doc:
			frappe.throw(_("No se encontro el archivo adjunto."), frappe.ValidationError)
		if not file_doc.is_private:
			frappe.throw(_("El archivo debe guardarse como archivo privado."), frappe.ValidationError)
		content = file_doc.get_content()
		if isinstance(content, str):
			content = content.encode("utf-8")
		digest = hashlib.sha256(content).hexdigest()
		if self.file_sha256 and self.file_sha256 != digest:
			frappe.throw(
				_("El archivo original no puede reemplazarse silenciosamente."), frappe.ValidationError
			)
		self.file_sha256 = digest
		if not self.original_filename:
			self.original_filename = file_doc.file_name
