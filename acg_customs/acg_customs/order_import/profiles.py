# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Perfiles de importacion identificados por ESTRUCTURA del Excel (nunca por nombre
comercial). Cada perfil describe el layout de una cuadricula producto x sucursal:

- comercial_grid_v1: hoja 'PEDIDO COMERCIAL'. Encabezado con J='PLU CIT' .. N='ARTICULO';
  clave de sucursal 2 filas sobre el encabezado; sucursales desde la col O.
- pedido_grid_v2: hoja 'PEDIDO'. Encabezado con D='TIENDAS', E='CLAVE' (producto en E, nombre
  de articulo en F); clave de sucursal 1 fila sobre el encabezado; sucursales desde la col G.
  Trae tablas auxiliares pegadas a la derecha, por lo que el grid se corta en la primera
  columna agregada (TOTAL).

La resolucion de producto es la misma para ambos: la clave de producto se busca contra
Item Customer Detail.ref_code (verificado en BD). 'product_resolution_key' es solo etiqueta.
"""

_HEADER_SCAN_ROWS = 20


class ProfileSpec:
	def __init__(
		self,
		key,
		source_sheet,
		header_anchor,
		clave_col,
		articulo_col,
		first_branch_col,
		code_row_offset,
		name_row_offset,
		product_resolution_key,
		stop_at_total_column=False,
		total_row_position=None,
	):
		self.key = key
		self.source_sheet = source_sheet
		self.header_anchor = header_anchor  # {col: etiqueta normalizada esperada}
		self.clave_col = clave_col
		self.articulo_col = articulo_col
		self.first_branch_col = first_branch_col
		self.code_row_offset = code_row_offset
		self.name_row_offset = name_row_offset
		self.product_resolution_key = product_resolution_key
		self.stop_at_total_column = stop_at_total_column
		# Donde esta la fila de TOTAL monetario por sucursal (alineada con la columna
		# de cada sucursal). Solo indica DONDE leer el dato; el parser no calcula nada.
		#   "after_products"  -> fila inmediatamente despues del ultimo producto.
		#   "before_products" -> fila inmediatamente antes del primer producto.
		#   None              -> el formato no expone un total de referencia.
		self.total_row_position = total_row_position


PROFILES = [
	ProfileSpec(
		key="comercial_grid_v1",
		source_sheet="PEDIDO COMERCIAL",
		header_anchor={10: "plu cit", 14: "articulo"},
		clave_col=10,  # J = PLU CIT
		articulo_col=14,  # N = ARTICULO
		first_branch_col=15,  # O
		code_row_offset=-2,
		name_row_offset=0,
		product_resolution_key="plu_cit",
		stop_at_total_column=False,
		total_row_position="after_products",  # total por sucursal debajo del ultimo producto
	),
	ProfileSpec(
		key="pedido_grid_v2",
		source_sheet="PEDIDO",
		header_anchor={4: "tiendas", 5: "clave"},
		clave_col=5,  # E = CLAVE
		articulo_col=6,  # F = ARTICULO (sin etiqueta, solo datos)
		first_branch_col=7,  # G
		code_row_offset=-1,
		name_row_offset=0,
		product_resolution_key="clave",
		stop_at_total_column=True,
		total_row_position="before_products",  # total por sucursal arriba del primer producto
	),
]


def normalize(value) -> str:
	return str(value).strip().lower() if value is not None else ""


def find_header_row(ws, spec, max_scan: int = _HEADER_SCAN_ROWS):
	"""Fila de encabezado = aquella donde TODAS las columnas ancla coinciden (robusto,
	no hardcodea el numero de fila)."""
	limit = min(max_scan, ws.max_row or max_scan)
	for r in range(1, limit + 1):
		if all(
			normalize(ws.cell(row=r, column=col).value) == expected
			for col, expected in spec.header_anchor.items()
		):
			return r
	return None


def detect_profile(wb) -> ProfileSpec | None:
	"""Devuelve el ProfileSpec cuyo layout coincide INEQUIVOCAMENTE con el workbook; si
	ninguno, None."""
	for spec in PROFILES:
		if spec.source_sheet not in wb.sheetnames:
			continue
		if find_header_row(wb[spec.source_sheet], spec) is not None:
			return spec
	return None
