# Arquitectura técnica — acg_customs

> Describe el estado implementado del sistema. Se actualiza cuando cambia la
> arquitectura real. Para decisiones puntuales ver [ADR](../adr/index.md).

## Resumen

`acg_customs` automatiza el ciclo semanal de precios y pedidos de un proveedor de
productos frescos hacia un retailer, sobre Frappe 16 / ERPNext 16. **Principio rector:**
toda la lógica de precios, impuestos y totales se delega a ERPNext nativo (Price List,
`Item Price`, Sales Order); el app se limita a **extraer** datos del Excel y a
**orquestar/validar** el flujo de forma *fail-closed* y auditable.

## Módulos principales

| Módulo | Responsabilidad | Archivos / DocTypes clave |
|---|---|---|
| Importador de precios | Parseo del Excel semanal, preflight, apply de `Item Price` con vigencia | `price_import/{parser.py,service.py}`, `ACG Price Import`, `ACG Price Import Line` |
| Exclusiones | Códigos fuera de catálogo por cliente | `ACG External Code Exclusion` |
| Importador de pedidos | Parseo del pedido, preflight (incl. precio por fecha), creación de OV y conciliación | `order_import/{profiles.py,parser.py,preflight.py,apply.py,resolver.py}`, `ACG Order Import`, `ACG Order Import Sales Order` |
| Perfiles de proveedor | Identidad/segregación y mapeo de sucursales | `ACG Order Provider`, `ACG Order Provider User`, `ACG Order Branch Mapping` |
| Dimensión contable | Etiqueta de proveedor en documentos de venta | Accounting Dimension `ACG Order Provider` → `acg_order_provider` |

## Flujos principales

| Flujo | Entrada | Proceso | Salida |
|---|---|---|---|
| Precios | Excel semanal | parser (extracción) → preflight *fail-closed* → apply (upsert `Item Price` con `valid_from`/`valid_upto`) | `Item Price` versionados por vigencia |
| Pedidos | Excel de pedido + `order_date` | profile+parser → preflight (sucursal/producto/**precio vigente por fecha**) → crear OV (borrador) | OV por sucursal |
| Conciliación | OV creadas + total Excel | comparación por sucursal `grand_total` vs total Excel con tolerancia | `PASS`/`WARNING`/`SIN VALIDAR` por OV |

## Parser — límite de responsabilidad

Los parsers (`price_import/parser.py`, `order_import/parser.py`) **solo extraen** datos
del workbook (hojas, bloques, filas, celdas de total). No calculan precios, impuestos ni
totales, y no eligen hoja/semana por su cuenta. Las decisiones de negocio viven en
`service.py` / `preflight.py` / `apply.py` y en ERPNext nativo.

## Selección de precio por fecha

La OV se crea con `transaction_date = order_date`. ERPNext (`get_price_list_rate`)
selecciona el `Item Price` cuya vigencia cubre esa fecha (`valid_from desc`). El app
**rechaza el fallback nativo** (tomar el precio más reciente cuando ninguna ventana
cubre la fecha): el preflight exige cobertura temporal explícita. Ver
[ADR-0001](../adr/0001-vigencia-nativa-item-price.md).

## Conciliación de totales (Opción B)

Posterior a la creación de OV en borrador: se compara el total de referencia del Excel
(extraído por el *profile* de cada formato) contra `Sales Order.grand_total`. No se
simula la OV en el preflight. Ver [ADR-0002](../adr/0002-conciliacion-ov-opcion-b.md).

## Perfiles de importación de pedidos

Detección por **estructura** (nunca por nombre comercial). Cada `ProfileSpec`
(`order_import/profiles.py`) describe el layout producto × sucursal y la **posición de la
fila de totales** (`total_row_position`):

| Perfil | Hoja | Totales por sucursal |
|---|---|---|
| `comercial_grid_v1` | `PEDIDO COMERCIAL` | fila después del último producto (`after_products`) |
| `pedido_grid_v2` | `PEDIDO` | fila antes del primer producto (`before_products`) |

## Segregación y seguridad

Segregación por proveedor *fail-closed* server-side (query conditions + `has_permission`
sobre `ACG Order Import` y `File`). El `provider` es inmutable (`set_only_once`) y se
fuerza server-side (anti-spoofing). El archivo original se conserva como Private File con
SHA-256.

## Referencia de DocTypes

Ver [Referencia de DocTypes y campos](../referencia/doctypes.md).
