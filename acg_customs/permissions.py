# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Segregacion server-side por proveedor para el importador de pedidos.

Capas (todas fail-closed):
  1. permission_query_conditions("ACG Order Import") -> filtra la lista por proveedor.
  2. has_permission("ACG Order Import")             -> gate por registro (deny-only).
  3. permission_query_conditions("File")            -> evita fuga de nombres de Excel en File List.
  4. has_permission("File")                         -> bloquea descarga del Excel del otro proveedor.

La asociacion usuario -> proveedor se resuelve EXCLUSIVAMENTE desde el DocType
`ACG Order Provider User` (gestionado solo por System Manager). El valor `provider`
enviado desde el cliente nunca es fuente de verdad.
"""

import frappe

IMPORTER_ROLE = "ACG Order Importer"
ORDER_IMPORT_DT = "ACG Order Import"
PROVIDER_DT = "ACG Order Provider"
PROVIDER_USER_DT = "ACG Order Provider User"


def is_global_user(user: str | None = None) -> bool:
	"""Administrator y System Manager tienen visibilidad global (auditoria)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return "System Manager" in frappe.get_roles(user)


def get_user_provider(user: str | None = None) -> str | None:
	"""Proveedor autorizado del usuario, resuelto SOLO desde ACG Order Provider User.

	Fail-closed: devuelve None salvo que exista EXACTAMENTE una asociacion a un
	proveedor existente y habilitado.
	"""
	user = user or frappe.session.user

	# get_all ignora permisos/condiciones (resolucion interna, no sujeta al caller).
	providers = {p for p in frappe.get_all(PROVIDER_USER_DT, filters={"user": user}, pluck="provider") if p}
	if len(providers) != 1:
		return None

	provider = next(iter(providers))
	if not frappe.db.exists(PROVIDER_DT, provider):
		return None
	if frappe.db.get_value(PROVIDER_DT, provider, "disabled"):
		return None
	return provider


def _doc_value(doc, field):
	if isinstance(doc, dict):
		return doc.get(field)
	return getattr(doc, field, None)


# ----------------------------------------------------------------------
# ACG Order Import
# ----------------------------------------------------------------------
def order_import_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	if is_global_user(user):
		return ""
	provider = get_user_provider(user)
	if not provider:
		return "1=0"  # fail-closed: sin proveedor valido no ve ninguna fila
	return f"`tabACG Order Import`.`provider` = {frappe.db.escape(provider)}"


def order_import_has_permission(doc, ptype=None, user=None, debug=False):
	"""Deny-only: devolver False niega; True = 'no niego' (el DocPerm base aun aplica)."""
	user = user or frappe.session.user
	if is_global_user(user):
		return True
	provider = get_user_provider(user)
	if not provider:
		return False  # fail-closed: sin proveedor valido, nada permitido
	if ptype == "create":
		# En insert, check_permission("create") corre ANTES de before_insert (donde el
		# controller fija/valida provider). Aqui basta con que el usuario tenga un
		# proveedor valido; el controller es la fuente unica de verdad del provider.
		return True
	return _doc_value(doc, "provider") == provider


# ----------------------------------------------------------------------
# File (defensa en profundidad para el Excel privado adjunto)
# ----------------------------------------------------------------------
def file_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	user = user or frappe.session.user
	if is_global_user(user):
		return ""

	tbl = "`tabFile`"
	dt = frappe.db.escape(ORDER_IMPORT_DT)
	provider = get_user_provider(user)

	if not provider:
		# No puede ver NINGUN archivo adjunto a una importacion.
		return f"({tbl}.`attached_to_doctype` IS NULL OR {tbl}.`attached_to_doctype` != {dt})"

	# Solo archivos de importaciones de su propio proveedor.
	return (
		f"({tbl}.`attached_to_doctype` IS NULL "
		f"OR {tbl}.`attached_to_doctype` != {dt} "
		f"OR {tbl}.`attached_to_name` IN "
		f"(SELECT `name` FROM `tabACG Order Import` WHERE `provider` = {frappe.db.escape(provider)}))"
	)


def file_has_permission(doc, ptype=None, user=None, debug=False):
	"""Deny-only para archivos adjuntos a ACG Order Import de otro proveedor."""
	user = user or frappe.session.user
	if is_global_user(user):
		return True

	if _doc_value(doc, "attached_to_doctype") != ORDER_IMPORT_DT:
		return True  # no es nuestro archivo; que decidan core/otros hooks

	attached_name = _doc_value(doc, "attached_to_name")
	provider = get_user_provider(user)
	if not provider or not attached_name:
		return False
	return frappe.db.get_value(ORDER_IMPORT_DT, attached_name, "provider") == provider
