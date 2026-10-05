# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ACGOrderProviderUser(Document):
	def validate(self):
		# Un usuario proveedor solo puede pertenecer a UN proveedor.
		# autoname "field:user" ya garantiza unicidad por nombre; esta verificacion
		# es defensa explicita con un mensaje claro.
		existing = frappe.db.get_value(
			"ACG Order Provider User",
			{"user": self.user, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				_("El usuario {0} ya tiene un proveedor asignado ({1}).").format(self.user, existing),
				frappe.ValidationError,
			)
