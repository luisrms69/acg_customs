# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Parser del archivo semanal de precios. Estructura confirmada: una hoja con encabezado
CODIGO | DESCRIPCION | COSTO (COSTO = precio de venta). Deteccion por etiquetas (robusta,
no hardcodea el nombre de la hoja ni el numero de fila)."""

HEADER = {1: "codigo", 2: "descripcion", 3: "costo"}  # col -> etiqueta esperada (normalizada)
COL_CODE, COL_DESC, COL_COST = 1, 2, 3
_SCAN_ROWS = 10


def _norm(v) -> str:
	return str(v).strip().lower() if v is not None else ""


def _code_str(v):
	if v is None or isinstance(v, bool):
		return None
	if isinstance(v, int):
		return str(v)
	if isinstance(v, float):
		return str(int(v)) if v.is_integer() else str(v)
	s = str(v).strip()
	return s or None


def find_header(wb):
	"""Devuelve (sheet, header_row) de la primera hoja cuyo encabezado coincide; o (None, None)."""
	for sn in wb.sheetnames:
		ws = wb[sn]
		limit = min(_SCAN_ROWS, ws.max_row or _SCAN_ROWS)
		for r in range(1, limit + 1):
			if all(_norm(ws.cell(row=r, column=c).value) == expected for c, expected in HEADER.items()):
				return sn, r
	return None, None


def parse_workbook(wb):
	sheet, header_row = find_header(wb)
	if sheet is None:
		return {
			"sheet": None,
			"header_row": None,
			"rows": [],
			"structural_errors": ["Estructura no reconocida (se esperaba CODIGO | DESCRIPCION | COSTO)."],
		}

	ws = wb[sheet]
	rows = []
	started = False
	for r in range(header_row + 1, (ws.max_row or header_row) + 1):
		code = ws.cell(row=r, column=COL_CODE).value
		desc = ws.cell(row=r, column=COL_DESC).value
		cost = ws.cell(row=r, column=COL_COST).value
		if code in (None, "") and (desc in (None, "")) and cost in (None, ""):
			if started:
				break
			continue
		started = True
		rows.append(
			{
				"row": r,
				"code": _code_str(code),
				"description": str(desc).strip() if desc not in (None, "") else None,
				"cost": cost,
			}
		)
	return {"sheet": sheet, "header_row": header_row, "rows": rows, "structural_errors": []}
