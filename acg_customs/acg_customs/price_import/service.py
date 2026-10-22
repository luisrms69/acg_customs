# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Preflight + apply del importador semanal de precios.

- Resuelve CODIGO -> Item por Item Customer Detail.ref_code (reutiliza el resolver de pedidos).
- Preflight fail-closed: estructura, CODIGO/COSTO validos, duplicados conflictivos, Item inexistente/ambiguo.
- Apply transaccional: upsert de UN Item Price vigente por (Item, Price List); registra comparativo
  (previous/new/action) en la child table. Idempotente (status + SHA-256). No crea Items, no toca ICD.
"""

import hashlib
import io

import frappe
from frappe import _

from acg_customs.acg_customs.doctype.acg_external_code_exclusion.acg_external_code_exclusion import (
	is_excluded,
)
from acg_customs.acg_customs.order_import import resolver
from acg_customs.acg_customs.price_import import parser

ITEM_PRICE_DT = "Item Price"


def _load_content(doc):
	if not doc.excel_file:
		return None, None
	name = frappe.db.get_value("File", {"file_url": doc.excel_file})
	if not name:
		return None, None
	content = frappe.get_doc("File", name).get_content()
	if isinstance(content, str):
		content = content.encode("utf-8")
	return content, hashlib.sha256(content).hexdigest()


def _valid_cost(v):
	if v is None or isinstance(v, bool):
		return (False, 0.0)
	if isinstance(v, (int, float)):
		return (True, float(v))
	try:
		return (True, float(str(v).strip()))
	except ValueError:
		return (False, 0.0)


def analyze(doc):
	"""Devuelve (summary, lines) sin escribir Item Price. Deterministico."""
	summary = {
		"customer": doc.customer,
		"price_list": doc.price_list,
		"file_sha256": doc.file_sha256,
		"sheet": None,
		"header_row": None,
		"total_rows": 0,
		"resolved": 0,
		"unresolved": 0,
		"skipped": 0,
		"new": 0,
		"changed": 0,
		"unchanged": 0,
		"errors": [],
		"warnings": [],
		"result": "FAIL",
	}
	errors = summary["errors"]
	warnings = summary["warnings"]

	if not doc.customer:
		errors.append(_("Sin Customer."))
	if not doc.price_list:
		errors.append(_("Sin Price List."))

	content, sha = _load_content(doc)
	if content is None:
		errors.append(_("No se encontro el archivo adjunto."))
		return summary, []
	if doc.file_sha256 and sha != doc.file_sha256:
		errors.append(_("El contenido no coincide con file_sha256 (posible alteracion)."))
	summary["file_sha256"] = sha

	# Aviso idempotencia: mismo archivo ya aplicado en otro import.
	dup = frappe.get_all(
		"ACG Price Import",
		filters={"file_sha256": sha, "status": "Applied", "name": ["!=", doc.name]},
		pluck="name",
	)
	if dup:
		warnings.append(_("Mismo archivo (SHA) ya aplicado en: {0}.").format(", ".join(dup)))

	try:
		wb = __import__("openpyxl").load_workbook(io.BytesIO(content), data_only=True)
	except Exception as exc:
		errors.append(_("No se pudo abrir el Excel: {0}").format(str(exc)[:200]))
		return summary, []

	parsed = parser.parse_workbook(wb)
	summary["sheet"] = parsed["sheet"]
	summary["header_row"] = parsed["header_row"]
	errors.extend(parsed["structural_errors"])
	if parsed["structural_errors"]:
		return summary, []

	rows = parsed["rows"]
	summary["total_rows"] = len(rows)

	# Validacion + dedupe por CODIGO
	by_code = {}
	for r in rows:
		code = r["code"]
		if not code:
			errors.append(_("Fila {0}: CODIGO vacio.").format(r["row"]))
			continue
		ok, fcost = _valid_cost(r["cost"])
		if not ok:
			errors.append(
				_("CODIGO {0} (fila {1}): COSTO no numerico ({2!r}).").format(code, r["row"], r["cost"])
			)
			continue
		if fcost <= 0:
			errors.append(_("CODIGO {0} (fila {1}): COSTO <= 0.").format(code, r["row"]))
			continue
		if code in by_code:
			if abs(by_code[code][0] - fcost) > 1e-9:
				errors.append(_("CODIGO {0}: duplicado con costos distintos.").format(code))
			else:
				warnings.append(_("CODIGO {0}: duplicado con mismo costo (colapsado).").format(code))
			continue
		by_code[code] = (fcost, r["description"])

	# Resolucion + comparativo
	lines = []
	for code in sorted(by_code):
		fcost, desc = by_code[code]
		res = resolver.resolve_product(doc.customer, code)
		if res["status"] != "ok":
			# Fuera de catalogo confirmado -> skipped (no es error, no provoca FAIL).
			if is_excluded(doc.customer, code):
				summary["skipped"] += 1
				warnings.append(_("CODIGO {0}: omitido (fuera de catalogo).").format(code))
				lines.append(
					{
						"code": code,
						"item": None,
						"description": desc,
						"previous_rate": None,
						"new_rate": fcost,
						"action": "skipped",
					}
				)
				continue
			summary["unresolved"] += 1
			msg = "Item inexistente" if res["status"] == "missing" else f"Item ambiguo ({res['candidates']})"
			errors.append(_("CODIGO {0}: {1}.").format(code, msg))
			lines.append(
				{
					"code": code,
					"item": None,
					"description": desc,
					"previous_rate": None,
					"new_rate": fcost,
					"action": "unresolved",
				}
			)
			continue
		item = res["item"]
		summary["resolved"] += 1
		prev = frappe.db.get_value(
			ITEM_PRICE_DT, {"item_code": item, "price_list": doc.price_list}, "price_list_rate"
		)
		if prev is None:
			action = "new"
			summary["new"] += 1
		elif abs(float(prev) - fcost) > 1e-9:
			action = "changed"
			summary["changed"] += 1
		else:
			action = "unchanged"
			summary["unchanged"] += 1
		lines.append(
			{
				"code": code,
				"item": item,
				"description": desc,
				"previous_rate": prev,
				"new_rate": fcost,
				"action": action,
			}
		)

	summary["result"] = "FAIL" if errors else "PASS"
	return summary, lines


def _persist(doc, summary, lines, status):
	doc.set("lines", [])
	for ln in lines:
		doc.append("lines", ln)
	doc.preflight_summary = frappe.as_json(summary)
	doc.status = status
	doc.errors = "\n".join(summary.get("errors", [])) or None
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def run_preflight(price_import: str) -> dict:
	doc = frappe.get_doc("ACG Price Import", price_import)
	doc.check_permission("write")
	summary, lines = analyze(doc)
	_persist(doc, summary, lines, "Preflight Passed" if summary["result"] == "PASS" else "Preflight Failed")
	return summary


@frappe.whitelist()
def apply_prices(price_import: str) -> dict:
	doc = frappe.get_doc("ACG Price Import", price_import)
	doc.check_permission("write")

	if doc.status == "Applied":
		return {"status": "Applied", "idempotent": True, "new": 0, "changed": 0}
	if doc.status != "Preflight Passed":
		frappe.throw(
			_("La importacion debe estar en 'Preflight Passed' para aplicar precios."), frappe.ValidationError
		)

	summary, lines = analyze(doc)  # fresco
	if summary["result"] != "PASS":
		frappe.throw(_("El preflight no esta en PASS; no se aplican precios."), frappe.ValidationError)

	savepoint = "acg_price_apply"
	frappe.db.savepoint(savepoint)
	try:
		applied_new = applied_changed = 0
		for ln in lines:
			# Garantia explicita: una linea omitida (fuera de catalogo) nunca crea/modifica Item Price.
			if ln["action"] == "skipped":
				continue
			if ln["action"] == "new":
				frappe.get_doc(
					{
						"doctype": ITEM_PRICE_DT,
						"item_code": ln["item"],
						"price_list": doc.price_list,
						"price_list_rate": ln["new_rate"],
					}
				).insert(ignore_permissions=True)
				applied_new += 1
			elif ln["action"] == "changed":
				name = frappe.db.get_value(
					ITEM_PRICE_DT, {"item_code": ln["item"], "price_list": doc.price_list}, "name"
				)
				frappe.db.set_value(ITEM_PRICE_DT, name, "price_list_rate", ln["new_rate"])
				applied_changed += 1
		_persist(doc, summary, lines, "Applied")
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	return {
		"status": "Applied",
		"idempotent": False,
		"new": applied_new,
		"changed": applied_changed,
		"unchanged": summary["unchanged"],
	}
