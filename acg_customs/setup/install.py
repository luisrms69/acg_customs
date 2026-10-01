# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Configuracion idempotente ejecutada en after_migrate.

Asegura unicamente infraestructura GENERICA y reutilizable (el rol de importador).
Los proveedores (ACG Order Provider) y las asociaciones usuario->proveedor
(ACG Order Provider User) son datos especificos de cada despliegue y se configuran
por sitio (System Manager); NO se siembran desde el codigo del app.
"""

import frappe

from acg_customs.permissions import IMPORTER_ROLE


def after_migrate():
	ensure_importer_role()


def ensure_importer_role():
	if not frappe.db.exists("Role", IMPORTER_ROLE):
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": IMPORTER_ROLE,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)
