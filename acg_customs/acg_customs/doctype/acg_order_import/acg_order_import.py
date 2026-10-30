# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from acg_customs.permissions import get_user_provider, is_global_user

ORIGINAL_FILE_FIELD = "excel_file"


class ACGOrderImport(Document):
	def before_insert(self):
		self._set_provider_on_create()
		self.uploaded_by = frappe.session.user
		self.uploaded_on = now_datetime()
		self.status = self.status or "Uploaded"

	def validate(self):
		self._process_source_file()

	def on_update(self):
		self._bind_source_file()

	def _bind_source_file(self):
		"""Liga explicitamente el File privado a este documento (attached_to_*).

		No depender del auto-attach del core (su momento/comportamiento varia entre
		versiones de Frappe): la segregacion del File privado (descarga cruzada denegada)
		requiere que el archivo quede adjunto a ESTE ACG Order Import. Idempotente."""
		file_doc = self._resolve_file_doc()
		if not file_doc:
			return
		if (
			file_doc.attached_to_doctype != self.doctype
			or file_doc.attached_to_name != self.name
			or not file_doc.is_private
		):
			frappe.db.set_value(
				"File",
				file_doc.name,
				{
					"attached_to_doctype": self.doctype,
					"attached_to_name": self.name,
					"attached_to_field": ORIGINAL_FILE_FIELD,
					"is_private": 1,
				},
			)

	# ------------------------------------------------------------------
	# Segregacion de proveedor (server-side, fail-closed)
	# ------------------------------------------------------------------
	def _set_provider_on_create(self):
		"""Determina/valida el proveedor server-side. El valor recibido del cliente
		nunca es fuente de verdad para un usuario proveedor. Inmutabilidad posterior
		la garantiza set_only_once sobre el campo `provider`."""
		user = frappe.session.user

		if is_global_user(user):
			# System Manager / Administrator: auditoria global y creacion on-behalf.
			# Debe especificar un proveedor valido explicitamente (fail-closed).
			if not self.provider:
				frappe.throw(
					_("Debe especificar un proveedor para la importacion."),
					frappe.ValidationError,
				)
			if not frappe.db.exists("ACG Order Provider", self.provider):
				frappe.throw(_("Proveedor invalido."), frappe.ValidationError)
			return

		authorized = get_user_provider(user)
		if not authorized:
			frappe.throw(
				_("No se pudo determinar un proveedor autorizado para el usuario. Importacion no permitida."),
				frappe.PermissionError,
			)
		if self.provider and self.provider != authorized:
			frappe.throw(
				_("No puede crear importaciones para otro proveedor."),
				frappe.PermissionError,
			)
		self.provider = authorized

	# ------------------------------------------------------------------
	# Archivo origen: privado, SHA-256 sobre bytes originales, inmutable
	# ------------------------------------------------------------------
	def _process_source_file(self):
		if not self.get(ORIGINAL_FILE_FIELD):
			frappe.throw(_("Debe adjuntar el archivo Excel original."), frappe.MandatoryError)

		file_doc = self._resolve_file_doc()
		if not file_doc:
			frappe.throw(_("No se encontro el archivo adjunto."), frappe.ValidationError)

		if not file_doc.is_private:
			frappe.throw(
				_("El archivo Excel debe guardarse como archivo privado."),
				frappe.ValidationError,
			)

		content = file_doc.get_content()
		if isinstance(content, str):
			content = content.encode("utf-8")
		digest = hashlib.sha256(content).hexdigest()

		# No reemplazar silenciosamente el archivo original.
		if self.file_sha256 and self.file_sha256 != digest:
			frappe.throw(
				_("El archivo original no puede reemplazarse silenciosamente."),
				frappe.ValidationError,
			)

		self.file_sha256 = digest
		if not self.original_filename:
			self.original_filename = file_doc.file_name

	def _resolve_file_doc(self):
		name = frappe.db.get_value("File", {"file_url": self.get(ORIGINAL_FILE_FIELD)})
		return frappe.get_doc("File", name) if name else None
