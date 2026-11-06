# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Preflight + apply del importador semanal de precios.

- Resuelve CODIGO -> Item por Item Customer Detail.ref_code (reutiliza el resolver de pedidos).
- Seleccion de semana fail-closed: si el libro trae varias hojas, exige `sheet_name` explicito;
  la vigencia (valid_from) debe confirmarse antes de aplicar.
- Preflight fail-closed: estructura, CODIGO/COSTO validos, duplicados conflictivos, Item inexistente/ambiguo.
- Vigencia nativa: cada corrida escribe Item Price con valid_from/valid_upto. NO sobrescribe otras
  ventanas (conserva el historico). Idempotente por ventana (Item, Price List, valid_from).
- Advierte variaciones de precio por encima de un umbral configurable y solapamientos de vigencia.
- Apply transaccional. No crea Items, no toca ICD.
"""

import hashlib
import io

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

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


def _window_rate(item, price_list, valid_from):
	"""Rate del Item Price de la MISMA ventana (item, price_list, valid_from), o None."""
	return frappe.db.get_value(
		ITEM_PRICE_DT,
		{"item_code": item, "price_list": price_list, "valid_from": valid_from},
		"price_list_rate",
	)


def _prior_rate(item, price_list, valid_from):
	"""Rate vigente ANTES de `valid_from`: la ventana con mayor valid_from < D (o sin fecha)."""
	rows = frappe.get_all(
		ITEM_PRICE_DT,
		filters={"item_code": item, "price_list": price_list},
		fields=["price_list_rate", "valid_from"],
		order_by="valid_from desc",
	)
	d = getdate(valid_from)
	for r in rows:
		if r.valid_from is None or getdate(r.valid_from) < d:
			return r.price_list_rate
	return None


def _overlaps(item, price_list, valid_from, valid_upto):
	"""¿Existe otra ventana (distinto valid_from) que se solape con [valid_from, valid_upto]?"""
	d1, d2 = getdate(valid_from), getdate(valid_upto) if valid_upto else None
	for r in frappe.get_all(
		ITEM_PRICE_DT,
		filters={"item_code": item, "price_list": price_list},
		fields=["valid_from", "valid_upto"],
	):
		if r.valid_from is not None and getdate(r.valid_from) == d1:
			continue  # misma ventana (se actualiza, no es solape)
		rf = getdate(r.valid_from) if r.valid_from else None
		ru = getdate(r.valid_upto) if r.valid_upto else None
		# solape de intervalos [rf, ru] con [d1, d2] (None = abierto)
		if (ru is None or d1 <= ru) and (d2 is None or rf is None or rf <= d2):
			return True
	return False


def analyze(doc):
	"""Devuelve (summary, lines) sin escribir Item Price. Deterministico."""
	threshold = flt(doc.variation_threshold_pct) or 20.0
	summary = {
		"customer": doc.customer,
		"price_list": doc.price_list,
		"file_sha256": doc.file_sha256,
		"sheet": None,
		"candidate_sheets": [],
		"header_row": None,
		"valid_from": str(doc.valid_from) if doc.valid_from else None,
		"valid_upto": str(doc.valid_upto) if doc.valid_upto else None,
		"threshold_pct": threshold,
		"total_rows": 0,
		"resolved": 0,
		"unresolved": 0,
		"skipped": 0,
		"new": 0,
		"changed": 0,
		"unchanged": 0,
		"abnormal": 0,
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

	# --- Confirmacion de periodo (vigencia) obligatoria ---
	if not doc.valid_from:
		errors.append(_("Confirme el periodo: 'Vigente desde' (valid_from) es obligatorio."))
	elif doc.valid_upto and getdate(doc.valid_upto) < getdate(doc.valid_from):
		errors.append(_("'Vigente hasta' no puede ser anterior a 'Vigente desde'."))

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

	parsed = parser.parse_workbook(wb, doc.sheet_name or None)
	summary["sheet"] = parsed["sheet"]
	summary["candidate_sheets"] = parsed["candidate_sheets"]
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

		# Comparativo POR VENTANA (no sobrescribe otras vigencias):
		# - misma ventana (mismo valid_from) ya existe -> changed/unchanged;
		# - no existe esa ventana -> new (y 'previous' = precio vigente anterior, para la variacion).
		same = _window_rate(item, doc.price_list, doc.valid_from)
		if same is not None:
			prev = same
			if abs(float(same) - fcost) > 1e-9:
				action = "changed"
				summary["changed"] += 1
			else:
				action = "unchanged"
				summary["unchanged"] += 1
		else:
			prev = _prior_rate(item, doc.price_list, doc.valid_from)
			action = "new"
			summary["new"] += 1

		variation = None
		abnormal = 0
		if prev not in (None, 0):
			variation = (fcost - float(prev)) / float(prev) * 100.0
			if abs(variation) > threshold:
				abnormal = 1
				summary["abnormal"] += 1
				warnings.append(
					_("CODIGO {0} ({1}): variacion {2:.1f}% supera el umbral {3:.0f}% ({4} -> {5}).").format(
						code, item, variation, threshold, prev, fcost
					)
				)

		# Solapamiento de vigencia con otra ventana distinta -> aviso (no destructivo).
		if action == "new" and _overlaps(item, doc.price_list, doc.valid_from, doc.valid_upto):
			warnings.append(
				_("CODIGO {0} ({1}): la vigencia se solapa con otra ventana existente.").format(code, item)
			)

		lines.append(
			{
				"code": code,
				"item": item,
				"description": desc,
				"previous_rate": prev,
				"new_rate": fcost,
				"variation_pct": variation,
				"abnormal": abnormal,
				"valid_from": doc.valid_from,
				"valid_upto": doc.valid_upto,
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
				# Nueva VENTANA de vigencia. No toca otras ventanas -> conserva el historico.
				frappe.get_doc(
					{
						"doctype": ITEM_PRICE_DT,
						"item_code": ln["item"],
						"price_list": doc.price_list,
						"price_list_rate": ln["new_rate"],
						"valid_from": doc.valid_from,
						"valid_upto": doc.valid_upto,
					}
				).insert(ignore_permissions=True)
				applied_new += 1
			elif ln["action"] == "changed":
				# Correccion de la MISMA ventana (mismo valid_from); no crea una ventana nueva.
				name = frappe.db.get_value(
					ITEM_PRICE_DT,
					{"item_code": ln["item"], "price_list": doc.price_list, "valid_from": doc.valid_from},
					"name",
				)
				frappe.db.set_value(
					ITEM_PRICE_DT, name, {"price_list_rate": ln["new_rate"], "valid_upto": doc.valid_upto}
				)
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
