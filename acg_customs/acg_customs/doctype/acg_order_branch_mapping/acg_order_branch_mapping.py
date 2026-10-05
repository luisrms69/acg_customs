# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

KEY_SEP = "::"


class ACGOrderBranchMapping(Document):
	def validate(self):
		self._set_mapping_key()
		self._validate_address_integrity()

	def _set_mapping_key(self):
		code = (self.external_branch_code or "").strip()
		self.external_branch_code = code
		if not self.customer or not code:
			frappe.throw(_("Customer y External Branch Code son obligatorios."), frappe.MandatoryError)
		self.mapping_key = f"{self.customer}{KEY_SEP}{code}"
		# Unicidad explicita (ademas del unique a nivel DB en mapping_key).
		dup = frappe.db.get_value(
			"ACG Order Branch Mapping",
			{"mapping_key": self.mapping_key, "name": ["!=", self.name]},
		)
		if dup:
			frappe.throw(
				_("Ya existe un mapeo para el Customer {0} y la clave {1} ({2}).").format(
					self.customer, code, dup
				),
				frappe.ValidationError,
			)

	def _validate_address_integrity(self):
		address_type = frappe.db.get_value("Address", self.address, "address_type")
		if address_type != "Shipping":
			frappe.throw(
				_("El Address {0} debe ser de tipo Shipping.").format(self.address),
				frappe.ValidationError,
			)
		linked = frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": self.address,
				"link_doctype": "Customer",
				"link_name": self.customer,
			},
		)
		if not linked:
			frappe.throw(
				_("El Address {0} no esta ligado al Customer {1}.").format(self.address, self.customer),
				frappe.ValidationError,
			)
