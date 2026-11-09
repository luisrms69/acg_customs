# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Extraccion estructural de la hoja fuente del perfil comercial_grid_v1.

NO resuelve contra ERPNext (eso vive en resolver.py); solo lee el workbook y produce
una estructura determinista: sucursales (con clave), productos (con PLU) y lineas
producto x sucursal con cantidad > 0, mas errores/warnings estructurales.
"""

import re

from . import profiles

_LEADING_INT = re.compile(r"^\s*(\d+)")


def _is_total_column(value) -> bool:
	"""Columna agregada: la fila de clave contiene 'TOTAL' (TOTAL1, TOTAL, TOTAL 4...).
	Son columnas de subtotal del propio pedido (su fila de clave contiene TOTAL), no sucursales."""
	return value is not None and "total" in str(value).strip().lower()


def _as_branch_code(value):
	"""Clave de sucursal como str de entero positivo, o None.

	Normalizacion unica permitida: si el valor empieza inequivocamente por un numero,
	se extrae el entero inicial (p. ej. '376 .' -> '376'). Sin fuzzy ni otras heuristicas.
	"""
	if value is None or isinstance(value, bool):
		return None
	if isinstance(value, int):
		return str(value) if value > 0 else None
	if isinstance(value, float):
		return str(int(value)) if value > 0 and value.is_integer() else None
	m = _LEADING_INT.match(str(value).strip())
	if m:
		n = int(m.group(1))
		return str(n) if n > 0 else None
	return None


def _key_str(value):
	"""Normaliza una clave de producto (PLU) a str. Enteros -> sin decimales."""
	if value is None:
		return None
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return str(value)
	if isinstance(value, float):
		return str(int(value)) if value.is_integer() else str(value)
	s = str(value).strip()
	return s or None


def _as_quantity(value):
	"""Clasifica una celda de cantidad.

	Devuelve (kind, qty): kind in {"empty","number","invalid"}.
	- vacio / None -> ("empty", 0)
	- numerico -> ("number", float)
	- texto no numerico -> ("invalid", raw)
	"""
	if value is None or (isinstance(value, str) and value.strip() == ""):
		return ("empty", 0)
	if isinstance(value, bool):
		return ("invalid", value)
	if isinstance(value, (int, float)):
		return ("number", float(value))
	s = str(value).strip()
	try:
		return ("number", float(s))
	except ValueError:
		return ("invalid", s)


def _extract_branch_totals(ws, spec, products, branches):
	"""EXTRAE (no calcula) el total monetario de referencia por sucursal.

	El total vive en una fila alineada con la columna de cada sucursal, cuya posicion
	la define el perfil (total_row_position). El parser solo LEE el numero de esa celda;
	no suma, no aplica precios ni impuestos. Devuelve {code: {amount, cell, reliable}}.
	"""
	totals = {}
	if not getattr(spec, "total_row_position", None) or not products:
		return totals
	first_row = products[0]["row"]
	last_row = products[-1]["row"]
	if spec.total_row_position == "after_products":
		total_row = last_row + 1
	elif spec.total_row_position == "before_products":
		total_row = first_row - 1
	else:
		return totals
	if total_row < 1:
		return totals
	for b in branches:
		v = ws.cell(row=total_row, column=b["col"]).value
		cell = f"r{total_row}c{b['col']}"
		if isinstance(v, (int, float)) and not isinstance(v, bool):
			totals[b["code"]] = {"amount": float(v), "cell": cell, "reliable": True}
		else:
			totals[b["code"]] = {"amount": None, "cell": cell, "reliable": False}
	return totals


def parse_workbook(wb, spec):
	"""Parsea el workbook segun el ProfileSpec detectado.

	Devuelve dict con: header_row, branches, products, lines, structural_errors,
	warnings, total_units, branch_totals.
	"""
	ws = wb[spec.source_sheet]
	header_row = profiles.find_header_row(ws, spec)
	if header_row is None:
		return {
			"header_row": None,
			"branches": [],
			"products": [],
			"lines": [],
			"structural_errors": ["No se encontro la fila de encabezado del perfil."],
			"warnings": [],
			"total_units": 0,
		}

	code_row = header_row + spec.code_row_offset
	name_row = header_row + spec.name_row_offset
	max_col = ws.max_column or spec.first_branch_col

	structural_errors = []
	warnings = []

	# --- Sucursales ---
	# Clasificacion de columnas (desde la primera col de sucursal):
	#   - fila de clave o de nombre contiene 'TOTAL' -> columna AGREGADA:
	#       * si el perfil lo indica (stop_at_total_column) marca el borde derecho del
	#         grid -> cortar (las tablas auxiliares pegadas a la derecha se ignoran);
	#       * si no, ignorar solo esa columna y continuar.
	#   - sin nombre                       -> auxiliar/agregado sin rotulo: ignorar.
	#   - nombre + clave entera valida     -> sucursal resoluble.
	#   - nombre sin clave valida          -> sin clave (warning si 0 pedidos; FAIL si trae pedidos).
	branches = []  # {col, code, name}
	unkeyed_branches = []  # columnas con nombre pero sin clave valida
	for c in range(spec.first_branch_col, max_col + 1):
		code_cell = ws.cell(row=code_row, column=c).value
		name = ws.cell(row=name_row, column=c).value
		if _is_total_column(code_cell) or _is_total_column(name):
			if spec.stop_at_total_column:
				break  # borde derecho del grid
			continue  # columna agregada aislada -> ignorar
		if name is None or str(name).strip() == "":
			continue  # columnas sin nombre (totales, vacias) -> ignorar
		code = _as_branch_code(code_cell)
		if code is None:
			unkeyed_branches.append({"col": c, "name": str(name).strip()})
			continue
		branches.append({"col": c, "code": code, "name": str(name).strip()})

	branch_by_col = {b["col"]: b for b in branches}

	# --- Productos ---
	products = []  # {row, plu, articulo}
	started = False
	for r in range(header_row + 1, (ws.max_row or header_row) + 1):
		articulo = ws.cell(row=r, column=spec.articulo_col).value
		if articulo is None or str(articulo).strip() == "":
			if started:
				break
			continue
		started = True
		products.append(
			{
				"row": r,
				"plu": _key_str(ws.cell(row=r, column=spec.clave_col).value),
				"articulo": str(articulo).strip(),
			}
		)

	# --- Lineas producto x sucursal (solo cantidades > 0) + datos inesperados ---
	lines = []  # {row, col, plu, articulo, branch_code, qty}
	total_units = 0.0
	for p in products:
		r = p["row"]
		# Celdas en columnas de sucursal resoluble
		for b in branches:
			kind, qty = _as_quantity(ws.cell(row=r, column=b["col"]).value)
			if kind == "invalid":
				structural_errors.append(
					f"Cantidad no numerica en fila {r}, sucursal {b['code']} ({b['name']}): {qty!r}."
				)
			elif kind == "number" and qty > 0:
				lines.append(
					{
						"row": r,
						"col": b["col"],
						"plu": p["plu"],
						"articulo": p["articulo"],
						"branch_code": b["code"],
						"qty": qty,
					}
				)
				total_units += qty
		# Datos en columnas con nombre de sucursal pero SIN clave -> no se pueden asignar.
		for ub in unkeyed_branches:
			kind, qty = _as_quantity(ws.cell(row=r, column=ub["col"]).value)
			if kind == "number" and qty > 0:
				structural_errors.append(
					f"Pedido en columna sin clave de sucursal ({ub['name']}, col {ub['col']}), "
					f"fila {r}: no se puede resolver la sucursal."
				)
			elif kind == "invalid":
				warnings.append(
					f"Dato inesperado en columna sin clave ({ub['name']}, col {ub['col']}), fila {r}."
				)

	if unkeyed_branches:
		warnings.append(
			f"{len(unkeyed_branches)} columna(s) con nombre de sucursal pero con la celda de clave VACIA: "
			f"se ignoran y no generan Sales Order. Si alguna trae pedido (cantidad), esa cantidad se "
			f"reporta como error aparte y no se asigna a ninguna sucursal. Revisar si falta la clave."
		)

	branch_totals = _extract_branch_totals(ws, spec, products, branches)

	return {
		"header_row": header_row,
		"branches": branches,
		"products": products,
		"lines": lines,
		"structural_errors": structural_errors,
		"warnings": warnings,
		"total_units": total_units,
		"branch_by_col": branch_by_col,
		"branch_totals": branch_totals,
	}
