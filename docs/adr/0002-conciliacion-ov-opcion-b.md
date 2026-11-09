# ADR-0002: Conciliación de totales de OV posterior a la creación (Opción B)

**Fecha:** 2026-11-08
**Status:** Activo

## Contexto

Se requiere evitar que se facturen Órdenes de Venta cuyos importes no coincidan con el
total declarado por el proveedor en su Excel, por sucursal. Se evaluaron dos enfoques:

- **Opción A — anticipada en preflight:** reconstruir en memoria la Sales Order (sin
  insertarla) para calcular el total previsto y compararlo antes de crear la OV.
- **Opción B — posterior a la creación:** crear la OV con el flujo nativo (en borrador) y
  comparar su `grand_total` real contra el total del Excel.

## Decisión

Adoptar la **Opción B**. La conciliación ocurre **después** de crear las OV, que quedan
en **borrador** (`docstatus = 0`). Por sucursal se compara el **total de referencia del
Excel** (extraído por el *profile* de cada formato; el parser solo lee el número) contra
`Sales Order.grand_total`:

| Condición | Resultado |
|---|---|
| diferencia ≤ `total_tolerance` (default $0.01) | **PASS** |
| diferencia > tolerancia | **WARNING** (con el importe de la diferencia) |
| total ausente/ambiguo | **SIN VALIDAR** (no se inventan totales) |

El bloqueo hacia la factura es **nativo**: una OV en borrador no se puede facturar en
ERPNext. El operador somete solo las OV `PASS`. No se añaden restricciones globales sobre
Sales Order (las OV manuales no se afectan). El detalle se persiste por fila para
auditoría.

## Consecuencias

- Cero duplicación de la lógica de precios/impuestos: el total previsto **es** el de la
  OV real (mismo motor nativo).
- La tolerancia es **absoluta y configurable** (sin tolerancia porcentual por defecto).
- El control es claro para el operador (resumen `PASS`/`WARNING`/`SIN VALIDAR`) y no
  impone política global al resto de Sales Orders.
- Conciliación **independiente por sucursal** dentro de un mismo import.

## Alternativa descartada

**Opción A (simulación en preflight).** Descartada por decisión del equipo: duplica el
armado de la OV antes de tiempo, acopla el preflight al cálculo de totales e impuestos, y
el "previsto" podría divergir del documento real. La Opción B compara contra el total
efectivamente calculado por ERPNext.
