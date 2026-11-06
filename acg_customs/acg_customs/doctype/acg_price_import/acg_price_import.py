# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import hashlib
import io

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from acg_customs.acg_customs.price_import import parser


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
		if self.variation_threshold_pct in (None, 0):
			self.variation_threshold_pct = 20

	def validate(self):
		self._process_source_file()
		self._detect_sheets()

	def _detect_sheets(self):
		"""Lista las hojas de precios validas (solo informativo/UX). No elige por su cuenta."""
		content = self._content()
		if content is None:
			return
		try:
			wb = __import__("openpyxl").load_workbook(io.BytesIO(content), data_only=True)
		except Exception:
			return
		sheets = parser.list_price_sheets(wb)
		self.detected_sheets = "\n".join(sheets) if sheets else None
		# Conveniencia: una sola hoja candidata -> prellenar (sigue requiriendo vigencia confirmada).
		if not self.sheet_name and len(sheets) == 1:
			self.sheet_name = sheets[0]

	def _content(self):
		if not self.excel_file:
			return None
		name = frappe.db.get_value("File", {"file_url": self.excel_file})
		if not name:
			return None
		content = frappe.get_doc("File", name).get_content()
		if isinstance(content, str):
			content = content.encode("utf-8")
		return content

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
