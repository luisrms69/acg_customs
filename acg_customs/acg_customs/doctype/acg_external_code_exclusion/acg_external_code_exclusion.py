# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ACGExternalCodeExclusion(Document):
	def validate(self):
		self.external_code = (self.external_code or "").strip()
		if not self.external_code:
			frappe.throw(_("El codigo externo es obligatorio."), frappe.MandatoryError)
		dup = frappe.db.exists(
			"ACG External Code Exclusion",
			{
				"customer": self.customer,
				"external_code": self.external_code,
				"name": ["!=", self.name],
			},
		)
		if dup:
			frappe.throw(
				_("Ya existe una exclusion para {0} / codigo {1} ({2}).").format(
					self.customer, self.external_code, dup
				),
				frappe.DuplicateEntryError,
			)


def is_excluded(customer: str, external_code: str) -> bool:
	"""True si existe una exclusion ACTIVA para (customer, external_code)."""
	if not customer or external_code is None:
		return False
	return bool(
		frappe.db.exists(
			"ACG External Code Exclusion",
			{"customer": customer, "external_code": str(external_code).strip(), "enabled": 1},
		)
	)
