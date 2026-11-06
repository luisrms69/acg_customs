# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Parser del archivo semanal de precios.

La hoja trae uno o VARIOS bloques de columnas con el mismo encabezado
CODIGO | DESCRIPCION | COSTO (COSTO = precio de venta), colocados lado a lado
(p. ej. A-C y E-G). Se detectan TODOS los bloques en la fila de encabezado y se
leen las filas de cada uno, concatenando los productos. Deteccion por etiquetas
(no hardcodea nombre de hoja ni numero de fila ni numero de bloques)."""

HEADER_LABELS = ("codigo", "descripcion", "costo")  # triplete esperado (normalizado)
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


def _blocks_in_row(ws, r):
	"""Columnas de inicio (col del CODIGO) de cada triplete CODIGO|DESCRIPCION|COSTO
	contiguo en la fila r."""
	cols = []
	max_col = ws.max_column or 1
	for c in range(1, max_col + 1):
		if (
			_norm(ws.cell(row=r, column=c).value) == HEADER_LABELS[0]
			and _norm(ws.cell(row=r, column=c + 1).value) == HEADER_LABELS[1]
			and _norm(ws.cell(row=r, column=c + 2).value) == HEADER_LABELS[2]
		):
			cols.append(c)
	return cols


def find_header(wb):
	"""Devuelve (sheet, header_row, blocks) de la primera hoja/fila cuyo encabezado
	contiene al menos un triplete CODIGO|DESCRIPCION|COSTO; o (None, None, [])."""
	for sn in wb.sheetnames:
		ws = wb[sn]
		limit = min(_SCAN_ROWS, ws.max_row or _SCAN_ROWS)
		for r in range(1, limit + 1):
			blocks = _blocks_in_row(ws, r)
			if blocks:
				return sn, r, blocks
	return None, None, []


def parse_workbook(wb):
	sheet, header_row, blocks = find_header(wb)
	if sheet is None:
		return {
			"sheet": None,
			"header_row": None,
			"blocks": 0,
			"rows": [],
			"structural_errors": ["Estructura no reconocida (se esperaba CODIGO | DESCRIPCION | COSTO)."],
		}

	ws = wb[sheet]
	rows = []
	max_row = ws.max_row or header_row
	# Cada bloque se lee de forma independiente (puede terminar en distinta fila).
	for col_code in blocks:
		col_desc, col_cost = col_code + 1, col_code + 2
		started = False
		for r in range(header_row + 1, max_row + 1):
			code = ws.cell(row=r, column=col_code).value
			desc = ws.cell(row=r, column=col_desc).value
			cost = ws.cell(row=r, column=col_cost).value
			if code in (None, "") and desc in (None, "") and cost in (None, ""):
				if started:
					break  # fin de este bloque
				continue
			started = True
			rows.append(
				{
					"row": r,
					"col": col_code,
					"code": _code_str(code),
					"description": str(desc).strip() if desc not in (None, "") else None,
					"cost": cost,
				}
			)
	return {
		"sheet": sheet,
		"header_row": header_row,
		"blocks": len(blocks),
		"rows": rows,
		"structural_errors": [],
	}
