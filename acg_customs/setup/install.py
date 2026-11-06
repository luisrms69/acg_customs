# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Configuracion idempotente ejecutada en after_migrate.

Asegura infraestructura GENERICA y reutilizable (rol de importador y la Accounting
Dimension de proveedor). Los proveedores (ACG Order Provider) y las asociaciones
usuario->proveedor son datos especificos de cada despliegue y se configuran por sitio
(System Manager); NO se siembran desde el codigo del app.
"""

import frappe

from acg_customs.permissions import IMPORTER_ROLE

# Accounting Dimension nativa que identifica al proveedor en Sales Order / Sales Invoice.
# document_type = DocType usado como fuente de valores (sin hardcodear nombres de proveedor).
PROVIDER_DIMENSION_DOCTYPE = "ACG Order Provider"
PROVIDER_DIMENSION_FIELD = "acg_order_provider"  # scrub("ACG Order Provider")


def after_migrate():
	ensure_importer_role()
	ensure_provider_dimension()


def ensure_importer_role():
	if not frappe.db.exists("Role", IMPORTER_ROLE):
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": IMPORTER_ROLE,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)


def ensure_provider_dimension():
	"""Crea idempotentemente la Accounting Dimension de proveedor y garantiza, de forma
	SINCRONA, el campo nativo en las doctypes contables (en migrate el on_update la encola;
	aqui forzamos la creacion para que el campo exista al terminar)."""
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	name = frappe.db.get_value("Accounting Dimension", {"document_type": PROVIDER_DIMENSION_DOCTYPE})
	if name:
		dim = frappe.get_doc("Accounting Dimension", name)
	else:
		dim = frappe.get_doc(
			{"doctype": "Accounting Dimension", "document_type": PROVIDER_DIMENSION_DOCTYPE}
		).insert(ignore_permissions=True)

	# Idempotente: make_dimension_... solo crea el campo donde falta.
	if not frappe.get_meta("Sales Order", cached=False).has_field(PROVIDER_DIMENSION_FIELD):
		make_dimension_in_accounting_doctypes(doc=dim)
