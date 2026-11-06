# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Resolucion de sucursales y productos contra ERPNext, acotada al Customer configurado.

Reglas (fail-closed):
- Sucursal: match EXACTO en ACG Order Branch Mapping por (customer, external_branch_code)
  con enabled=1. Ademas el Address mapeado debe seguir siendo Shipping y estar ligado al
  Customer (defensa en profundidad). Exactamente 1 -> ok; 0/deshabilitado/incoherente ->
  missing; >1 -> ambiguo. Sin fuzzy, sin parsear address_title, sin crear Addresses.
- Producto: match por Item Customer Detail.ref_code == PLU para ese Customer. Exactamente
  1 Item -> ok; 0 -> missing; >1 -> ambiguo. Sin inventar/crear Items, sin fuzzy.
"""

import frappe


def _address_is_valid(address: str, customer: str) -> bool:
	"""El Address mapeado debe seguir siendo Shipping y ligado al Customer."""
	if not address:
		return False
	if frappe.db.get_value("Address", address, "address_type") != "Shipping":
		return False
	return bool(
		frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": address,
				"link_doctype": "Customer",
				"link_name": customer,
			},
		)
	)


def resolve_branch(customer: str, code: str) -> dict:
	mappings = frappe.get_all(
		"ACG Order Branch Mapping",
		filters={"customer": customer, "external_branch_code": code, "enabled": 1},
		fields=["name", "address"],
	)
	# Defensa en profundidad: descartar mapeos cuyo Address ya no sea coherente.
	valid = [m for m in mappings if _address_is_valid(m.address, customer)]
	addresses = sorted({m.address for m in valid})
	if len(addresses) == 1:
		return {"status": "ok", "address": addresses[0], "candidates": addresses}
	if not addresses:
		return {"status": "missing", "address": None, "candidates": []}
	return {"status": "ambiguous", "address": None, "candidates": addresses}


def resolve_product(customer: str, plu: str) -> dict:
	if plu is None:
		return {"status": "missing", "item": None, "candidates": []}
	items = frappe.get_all(
		"Item Customer Detail",
		filters={"customer_name": customer, "ref_code": plu},
		pluck="parent",
	)
	items = sorted(set(items))
	if len(items) == 1:
		return {"status": "ok", "item": items[0], "candidates": items}
	if not items:
		return {"status": "missing", "item": None, "candidates": []}
	return {"status": "ambiguous", "item": None, "candidates": items}
