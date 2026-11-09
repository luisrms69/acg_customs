# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Preflight server-side de ACG Order Import.

Valida el Excel contra el perfil estructural, extrae sucursales/productos/cantidades,
resuelve contra ERPNext (Customer configurado) y produce un resumen auditable en
preflight_summary. NO crea Sales Orders. Fail-closed ante cualquier inconsistencia.
Idempotente: no modifica el archivo original y re-ejecutar produce el mismo resultado.
"""

import hashlib
import io

import frappe
from frappe import _
from frappe.utils import getdate

from . import parser, profiles, resolver


def _has_valid_price(item, price_list, on_date):
	"""¿Existe un Item Price en `price_list` cuya vigencia cubra `on_date`?

	Replica el filtro temporal nativo de ERPNext (valid_from/valid_upto, nulos = abiertos),
	PERO sin el fallback al precio mas reciente: si ninguna ventana cubre la fecha -> False.
	"""
	d = getdate(on_date)
	for r in frappe.get_all(
		"Item Price",
		filters={"item_code": item, "price_list": price_list},
		fields=["valid_from", "valid_upto"],
	):
		if (not r.valid_from or getdate(r.valid_from) <= d) and (
			not r.valid_upto or getdate(r.valid_upto) >= d
		):
			return True
	return False


def _load_content(doc):
	if not doc.excel_file:
		return None, None
	file_name = frappe.db.get_value("File", {"file_url": doc.excel_file})
	if not file_name:
		return None, None
	file_doc = frappe.get_doc("File", file_name)
	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode("utf-8")
	return content, hashlib.sha256(content).hexdigest()


def execute_preflight(doc) -> dict:
	"""Ejecuta el preflight y devuelve el resumen estructurado (no persiste)."""
	summary = {
		"profile": None,
		"source_sheet": None,
		"product_resolution_key": None,
		"file_sha256": doc.file_sha256,
		"customer": None,
		"header_row": None,
		# Columnas de sucursal en el archivo (catalogo completo del proveedor), NO el pedido.
		"branch_columns_in_file": 0,
		"branches_duplicated": [],
		# Sucursales REALES del pedido (claves unicas con cantidad > 0).
		"branches_with_orders": 0,
		"product_lines": 0,
		"total_units": 0,
		"products_resolved": 0,
		"products_missing": [],
		"products_ambiguous": [],
		"products_without_price": [],
		"order_date": None,
		"price_list": None,
		"branches_resolved": 0,
		"branches_missing": [],
		"branches_ambiguous": [],
		"structural_errors": [],
		"warnings": [],
		"result": "FAIL",
	}

	errors = summary["structural_errors"]

	# --- Customer configurado (fail-closed si falta) ---
	customer = frappe.db.get_value("ACG Order Provider", doc.provider, "customer") if doc.provider else None
	summary["customer"] = customer
	if not customer:
		errors.append(_("El perfil/proveedor no tiene Customer configurado (ACG Order Provider.customer)."))

	# --- Cargar archivo ---
	content, sha = _load_content(doc)
	if content is None:
		errors.append(_("No se encontro el archivo adjunto."))
		return summary
	if doc.file_sha256 and sha != doc.file_sha256:
		errors.append(_("El contenido del archivo no coincide con file_sha256 (posible alteracion)."))
	summary["file_sha256"] = sha

	try:
		wb = __import__("openpyxl").load_workbook(io.BytesIO(content), data_only=True)
	except Exception as exc:
		errors.append(_("No se pudo abrir el Excel: {0}").format(str(exc)[:200]))
		return summary

	# --- Deteccion de perfil (granular) ---
	spec = profiles.detect_profile(wb)
	if spec is None:
		known_sheets = [p.source_sheet for p in profiles.PROFILES]
		if not any(s in wb.sheetnames for s in known_sheets):
			errors.append(_("Falta la hoja fuente del pedido (ninguna hoja reconocida)."))
		else:
			errors.append(
				_("Formato no reconocido: los encabezados no coinciden con ningun perfil conocido.")
			)
		return summary
	summary["profile"] = spec.key
	summary["source_sheet"] = spec.source_sheet
	summary["product_resolution_key"] = spec.product_resolution_key

	# --- Parseo estructural ---
	parsed = parser.parse_workbook(wb, spec)
	summary["header_row"] = parsed["header_row"]
	# Columnas de sucursal en el archivo (catalogo del proveedor): son sucursales reales,
	# pero incluyen las que NO pidieron esta vez. NO es "el pedido".
	summary["branch_columns_in_file"] = len(parsed["branches"])
	# Una clave puede aparecer en VARIAS columnas del catalogo (p. ej. una columna de respaldo
	# vacia). Eso NO implica suma: solo se advierte si la clave trae pedido en MAS DE UNA columna
	# (ahi SI se suman cantidades y hay que verificar que sea la misma sucursal).
	cols_per_code = {}
	for ln in parsed["lines"]:
		cols_per_code.setdefault(ln["branch_code"], set()).add(ln["col"])
	summed = sorted(c for c, cols in cols_per_code.items() if len(cols) > 1)
	summary["branches_duplicated"] = summed
	if summed:
		summary["warnings"].append(
			_(
				"Sucursal(es) cuyo pedido proviene de MAS de una columna; sus cantidades se suman: "
				"{0}. Verifique que esas columnas correspondan a la misma sucursal."
			).format(", ".join(summed))
		)
	summary["product_lines"] = len(parsed["lines"])
	summary["total_units"] = parsed["total_units"]
	errors.extend(parsed["structural_errors"])
	summary["warnings"].extend(parsed["warnings"])

	# Codigos/PLU con pedido > 0 (solo lo que generaria una OV)
	order_branch_codes = sorted({line["branch_code"] for line in parsed["lines"]})
	order_plus = sorted({line["plu"] for line in parsed["lines"] if line["plu"]})
	summary["branches_with_orders"] = len(order_branch_codes)

	# Lineas sin PLU (producto sin clave) -> no resoluble
	for line in parsed["lines"]:
		if not line["plu"]:
			errors.append(
				_("Linea sin PLU (fila {0}, articulo '{1}'): producto no resoluble.").format(
					line["row"], line["articulo"]
				)
			)

	if not customer:
		# Sin customer no se puede resolver; ya quedo marcado como error -> FAIL.
		summary["result"] = "FAIL"
		return summary

	# --- Resolucion de sucursales (solo las que traen pedido) ---
	art_by_plu = {p["plu"]: p["articulo"] for p in parsed["products"] if p["plu"]}
	resolved_branches = 0
	for code in order_branch_codes:
		res = resolver.resolve_branch(customer, code)
		if res["status"] == "ok":
			resolved_branches += 1
		elif res["status"] == "missing":
			summary["branches_missing"].append({"code": code})
		else:
			summary["branches_ambiguous"].append({"code": code, "candidates": res["candidates"]})
	summary["branches_resolved"] = resolved_branches

	# --- Resolucion de productos (solo los que traen pedido) ---
	resolved_products = 0
	resolved_items = {}  # plu -> item_code (solo los resueltos)
	for plu in order_plus:
		res = resolver.resolve_product(customer, plu)
		if res["status"] == "ok":
			resolved_products += 1
			resolved_items[plu] = res["item"]
		elif res["status"] == "missing":
			summary["products_missing"].append({"plu": plu, "articulo": art_by_plu.get(plu)})
		else:
			summary["products_ambiguous"].append(
				{"plu": plu, "articulo": art_by_plu.get(plu), "candidates": res["candidates"]}
			)
	summary["products_resolved"] = resolved_products

	# --- Fecha del pedido: OBLIGATORIA y manual (no hay default, no se lee del Excel) ---
	order_date = doc.order_date
	summary["order_date"] = str(order_date) if order_date else None
	if not order_date:
		errors.append(_("Capture la 'Fecha del pedido' antes de ejecutar el preflight."))

	# --- Precio explicitamente vigente a la fecha del pedido (sin fallback nativo) ---
	# Solo aplica cuando el Customer tiene lista de precios nativa configurada y hay fecha.
	price_list = frappe.db.get_value("Customer", customer, "default_price_list")
	summary["price_list"] = price_list
	if price_list and order_date:
		for plu, item in sorted(resolved_items.items()):
			if not _has_valid_price(item, price_list, order_date):
				summary["products_without_price"].append(
					{"plu": plu, "item": item, "articulo": art_by_plu.get(plu)}
				)

	# --- Veredicto fail-closed ---
	blocking = (
		errors
		or summary["branches_missing"]
		or summary["branches_ambiguous"]
		or summary["products_missing"]
		or summary["products_ambiguous"]
		or summary["products_without_price"]
	)
	summary["result"] = "FAIL" if blocking else "PASS"
	return summary


def _errors_text(summary) -> str:
	parts = list(summary.get("structural_errors", []))
	for b in summary.get("branches_missing", []):
		parts.append(f"Sucursal no resoluble: clave {b['code']}.")
	for b in summary.get("branches_ambiguous", []):
		parts.append(f"Sucursal ambigua: clave {b['code']} -> {b['candidates']}.")
	for p in summary.get("products_missing", []):
		parts.append(f"Producto no resoluble: PLU {p['plu']} ({p.get('articulo')}).")
	for p in summary.get("products_ambiguous", []):
		parts.append(f"Producto ambiguo: PLU {p['plu']} -> {p['candidates']}.")
	for p in summary.get("products_without_price", []):
		parts.append(
			f"Sin precio vigente a la fecha {summary.get('order_date')}: "
			f"PLU {p['plu']} ({p.get('articulo')}) -> {p['item']}."
		)
	return "\n".join(parts)


@frappe.whitelist()
def run_preflight(order_import: str) -> dict:
	"""Punto de entrada. La segregacion se aplica via check_permission('write'):
	un usuario proveedor solo puede ejecutar preflight sobre sus propias importaciones."""
	doc = frappe.get_doc("ACG Order Import", order_import)
	doc.check_permission("write")

	summary = execute_preflight(doc)

	frappe.db.set_value(
		"ACG Order Import",
		doc.name,
		{
			"preflight_summary": frappe.as_json(summary),
			"status": "Preflight Passed" if summary["result"] == "PASS" else "Preflight Failed",
			"errors": _errors_text(summary) or None,
		},
	)
	return summary
