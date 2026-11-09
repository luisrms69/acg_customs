# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Preflight + apply del importador semanal de precios.

- Resuelve CODIGO -> Item por Item Customer Detail.ref_code (reutiliza el resolver de pedidos).
- UNA sola hoja por archivo (fail-closed): si el libro trae mas de una hoja de precios ->
  ARCHIVO INCORRECTO. La vigencia (valid_from) debe confirmarse antes de aplicar.
- Preflight fail-closed: estructura, CODIGO/COSTO validos, duplicados conflictivos, Item inexistente/ambiguo.
- Vigencia nativa (Item Price.valid_from/valid_upto), modelo temporal que NO duplica ni destruye historico:
    * precio NUEVO (sin precio previo)     -> crear ventana.
    * precio SIN CAMBIOS (= ventana previa) -> conservar el registro y EXTENDER su vigencia.
    * precio MODIFICADO (!= ventana previa) -> CERRAR la ventana previa y crear una nueva.
  Soporta importaciones retroactivas y parciales; evita solapamientos recortando a la ventana siguiente.
- Advierte variaciones por encima de un umbral configurable. Apply transaccional. No crea Items, no toca ICD.
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
_EPS = 1e-9


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


# --- Ventanas de vigencia (Item Price) ------------------------------------------------


def _windows(item, price_list):
	"""Todas las ventanas (Item Price) de (item, price_list)."""
	return frappe.get_all(
		ITEM_PRICE_DT,
		filters={"item_code": item, "price_list": price_list},
		fields=["name", "price_list_rate", "valid_from", "valid_upto"],
	)


def _prev_window(windows, d):
	"""Ventana vigente en/antes de la fecha d: la de mayor valid_from <= d
	(valid_from nulo = la mas antigua). None si no hay ninguna aplicable."""
	best = None
	for w in windows:
		vf = getdate(w.valid_from) if w.valid_from else None
		if vf is not None and vf > d:
			continue
		if best is None:
			best = w
			continue
		bvf = getdate(best.valid_from) if best.valid_from else None
		if bvf is None or (vf is not None and vf > bvf):
			best = w
	return best


def _next_window(windows, d):
	"""Ventana inmediatamente posterior a d: la de menor valid_from > d. None si no hay."""
	best = None
	for w in windows:
		vf = getdate(w.valid_from) if w.valid_from else None
		if vf is None or vf <= d:
			continue
		if best is None or vf < getdate(best.valid_from):
			best = w
	return best


def _classify(windows, d, fcost):
	"""(action, previous_rate) comparando contra la ventana previa."""
	prev = _prev_window(windows, d)
	if prev is None:
		return "new", None
	if abs(flt(prev.price_list_rate) - fcost) <= _EPS:
		return "unchanged", prev.price_list_rate
	return "changed", prev.price_list_rate


# --- Analyze (preflight, sin escribir) ------------------------------------------------


def analyze(doc):
	"""Devuelve (summary, lines) sin escribir Item Price. Deterministico."""
	threshold = flt(doc.variation_threshold_pct) or 20.0
	summary = {
		"customer": doc.customer,
		"price_list": doc.price_list,
		"file_sha256": doc.file_sha256,
		"sheet": None,
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

	parsed = parser.parse_workbook(wb)  # exige UNA sola hoja de precios
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
			if abs(by_code[code][0] - fcost) > _EPS:
				errors.append(_("CODIGO {0}: duplicado con costos distintos.").format(code))
			else:
				warnings.append(_("CODIGO {0}: duplicado con mismo costo (colapsado).").format(code))
			continue
		by_code[code] = (fcost, r["description"])

	d = getdate(doc.valid_from) if doc.valid_from else None

	# Resolucion + comparativo por ventana de vigencia
	lines = []
	for code in sorted(by_code):
		fcost, desc = by_code[code]
		res = resolver.resolve_product(doc.customer, code)
		if res["status"] != "ok":
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

		action, prev = ("new", None) if d is None else _classify(_windows(item, doc.price_list), d, fcost)
		summary[action] += 1

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
def sheet_info(file_url: str) -> dict:
	"""Cuenta las hojas de precios de un archivo adjunto. La GUI lo llama al ADJUNTAR
	para rechazar de inmediato los libros con mas de una hoja (sin esperar a guardar)."""
	if not frappe.has_permission("ACG Price Import", "create"):
		frappe.throw(_("Sin permiso."), frappe.PermissionError)
	name = frappe.db.get_value("File", {"file_url": file_url})
	if not name:
		return {"sheets": 0, "names": []}
	content = frappe.get_doc("File", name).get_content()
	if isinstance(content, str):
		content = content.encode("utf-8")
	try:
		wb = __import__("openpyxl").load_workbook(io.BytesIO(content), data_only=True)
	except Exception:
		return {"sheets": 0, "names": []}
	names = parser.list_price_sheets(wb)
	return {"sheets": len(names), "names": names}


@frappe.whitelist()
def run_preflight(price_import: str) -> dict:
	doc = frappe.get_doc("ACG Price Import", price_import)
	doc.check_permission("write")
	summary, lines = analyze(doc)
	_persist(doc, summary, lines, "Preflight Passed" if summary["result"] == "PASS" else "Preflight Failed")
	return summary


def _apply_line(item, price_list, rate, d, u, counters):
	"""Aplica UNA linea segun el modelo temporal. No destruye historico."""
	windows = _windows(item, price_list)
	prev = _prev_window(windows, d)
	nxt = _next_window(windows, d)

	# Recorte: la vigencia no debe pisar la ventana siguiente.
	capped_u = getdate(u) if u else None
	if nxt and nxt.valid_from:
		limit = add_days(getdate(nxt.valid_from), -1)
		if capped_u is None or capped_u > limit:
			capped_u = limit

	def _insert():
		frappe.get_doc(
			{
				"doctype": ITEM_PRICE_DT,
				"item_code": item,
				"price_list": price_list,
				"price_list_rate": rate,
				"valid_from": d,
				"valid_upto": capped_u,
			}
		).insert(ignore_permissions=True)

	if prev is None:
		_insert()  # precio NUEVO
		counters["new"] += 1
		return

	same_from = prev.valid_from is not None and getdate(prev.valid_from) == d
	if abs(flt(prev.price_list_rate) - rate) <= _EPS:
		# SIN CAMBIOS -> conservar registro, EXTENDER vigencia si amplia cobertura (no duplicar).
		if prev.valid_upto is not None and (capped_u is None or capped_u > getdate(prev.valid_upto)):
			frappe.db.set_value(ITEM_PRICE_DT, prev.name, "valid_upto", capped_u)
			counters["extended"] += 1
		counters["unchanged"] += 1
		return

	# MODIFICADO
	if same_from:
		# misma ventana (mismo valid_from): corregir rate/vigencia, no crear otra.
		frappe.db.set_value(ITEM_PRICE_DT, prev.name, {"price_list_rate": rate, "valid_upto": capped_u})
	else:
		# cerrar la ventana previa justo antes de D y crear la nueva.
		if prev.valid_upto is None or getdate(prev.valid_upto) >= d:
			frappe.db.set_value(ITEM_PRICE_DT, prev.name, "valid_upto", add_days(d, -1))
		_insert()
	counters["changed"] += 1


@frappe.whitelist()
def apply_prices(price_import: str) -> dict:
	doc = frappe.get_doc("ACG Price Import", price_import)
	doc.check_permission("write")

	if doc.status == "Applied":
		return {
			"status": "Applied",
			"idempotent": True,
			"new": 0,
			"changed": 0,
			"unchanged": 0,
			"extended": 0,
		}
	if doc.status != "Preflight Passed":
		frappe.throw(
			_("La importacion debe estar en 'Preflight Passed' para aplicar precios."), frappe.ValidationError
		)

	summary, lines = analyze(doc)  # fresco
	if summary["result"] != "PASS":
		frappe.throw(_("El preflight no esta en PASS; no se aplican precios."), frappe.ValidationError)

	d = getdate(doc.valid_from)
	counters = {"new": 0, "changed": 0, "unchanged": 0, "extended": 0}
	savepoint = "acg_price_apply"
	frappe.db.savepoint(savepoint)
	try:
		for ln in lines:
			# Una linea omitida/no resuelta nunca crea/modifica Item Price.
			if ln["action"] in ("skipped", "unresolved"):
				continue
			_apply_line(ln["item"], doc.price_list, flt(ln["new_rate"]), d, doc.valid_upto, counters)
		_persist(doc, summary, lines, "Applied")
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	return {"status": "Applied", "idempotent": False, **counters}
