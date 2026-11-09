# Conciliación de totales de OV

Control que evita facturar Órdenes de Venta cuyos importes no coincidan con el total
declarado por el proveedor en su Excel. Es **posterior** a la creación de la OV
(Opción B): las OV se crean en **borrador** y luego se concilian por sucursal.

## Cómo funciona

1. Al **Generar Sales Orders**, cada OV se crea con el cálculo **nativo** de ERPNext
   (precios, impuestos y total). Las OV quedan en **borrador** (`docstatus = 0`).
2. Por cada sucursal se compara:
   - **Total Excel (referencia):** el importe por sucursal extraído del propio archivo
     del proveedor (lo ubica el *profile* de cada formato; ver abajo).
   - **Total OV (ERPNext):** `Sales Order.grand_total`.
3. Se registra el resultado en la fila de la OV y en un **resumen de conciliación**.

## Veredicto por sucursal

| Condición | Estado | Acción |
|---|---|---|
| diferencia ≤ tolerancia | **PASS** | la OV coincide con el Excel |
| diferencia > tolerancia | **WARNING** | se reporta el importe de la diferencia |
| sin total de referencia o ambiguo | **SIN VALIDAR** | no se inventa un total |

- **Tolerancia** absoluta configurable por importación: campo **Tolerancia de
  conciliación** (`total_tolerance`), valor inicial **$0.01**. No hay tolerancia
  porcentual.
- La conciliación es **independiente por sucursal**: una sucursal puede ser `PASS` y
  otra `WARNING`/`SIN VALIDAR` en el mismo import.

## De dónde sale el "Total Excel"

El *parser* solo **extrae** el número; no calcula precios ni totales. Cada formato
declara dónde está su fila de totales:

- **Perfil `comercial_grid_v1`:** fila de totales **inmediatamente después** del último
  producto, alineada con la columna de cada sucursal.
- **Perfil `pedido_grid_v2`:** fila de totales **inmediatamente antes** del primer
  producto, alineada con la columna de cada sucursal.

Si el formato no expone un total confiable para una sucursal, esa sucursal queda
`SIN VALIDAR` (nunca se estima).

## Control operativo (bloqueo hacia factura)

- Las OV con diferencias (o sin validar) **permanecen en borrador**.
- El bloqueo hacia la factura es **nativo**: una OV en borrador **no se puede facturar**
  en ERPNext. El operador **somete** (y luego factura) **solo** las OV conciliadas
  (`PASS`), tras revisar el resumen.
- No se imponen restricciones globales sobre Sales Order: las OV creadas manualmente,
  fuera del importador, no se ven afectadas.

## Auditoría

Cada fila `ACG Order Import Sales Order` guarda `reconciliation_status`, `excel_total`,
`erp_total` y `reconciliation_diff`, para trazabilidad.
