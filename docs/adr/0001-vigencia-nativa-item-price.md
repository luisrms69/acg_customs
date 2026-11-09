# ADR-0001: Vigencia nativa de precios vía `Item Price.valid_from`/`valid_upto`

**Fecha:** 2026-11-06
**Status:** Activo

## Contexto

El importador semanal de precios aplicaba un **único** `Item Price` por `(Item, Price
List)`, sobrescribiéndolo en cada corrida. Esto impedía conservar el histórico por
fechas y provocó un defecto real: con un libro de varias semanas, el parser tomaba la
primera hoja (enero) y aplicaba precios de un periodo equivocado a pedidos de octubre,
detectable solo auditando contra los CFDI reales.

Además, la Orden de Venta se creaba sin fecha de referencia, y ERPNext, al no encontrar
una ventana de vigencia que cubriera la fecha, **cae al precio más reciente** (fallback),
lo que podía aplicar silenciosamente un precio de otra semana.

## Decisión

1. **Usar la vigencia nativa de ERPNext**: cada corrida de precios escribe
   `Item Price.valid_from`/`valid_upto`. No se sobrescriben otras ventanas → el histórico
   se conserva. La selección del precio por fecha la hace ERPNext (`get_price_list_rate`).
2. **Un archivo = una semana (*fail-closed*)**: el archivo debe traer **una sola hoja de
   precios**. Si trae más de una → **ARCHIVO INCORRECTO** (FAIL). **No** se selecciona ni se
   elige automáticamente ninguna hoja. El parser permanece como extracción pura.
   *(Supersede la decisión inicial de "seleccionar la semana" — ver nota de revisión abajo.)*
3. **Fecha del pedido**: `ACG Order Import.order_date` fija la `transaction_date` de las
   OV, y el preflight exige que cada producto resuelto tenga un `Item Price` cuya vigencia
   cubra esa fecha. **Se rechaza el fallback nativo**: sin cobertura temporal → FAIL.

El **modelo de escritura** de las ventanas de `Item Price` (crear / extender / cerrar) se
detalla en [ADR-0003](0003-modelo-temporal-item-price.md).

## Consecuencias

- Histórico de precios por fechas disponible y auditable.
- Importaciones retroactivas y parciales soportadas (ver ADR-0003).
- Un pedido cuya semana de precios no se importó **se bloquea** en el preflight, en vez de
  facturarse con un precio incorrecto.

## Nota de revisión (2026-11-08)

La decisión 2 cambió: se **eliminó la selección de hoja** (`sheet_name`/`detected_sheets`).
Un libro con más de una hoja de precios ahora se **rechaza** como archivo incorrecto. Motivo:
la selección por texto libre era frágil para el operador y propensa a error; exigir un archivo
de una sola semana es más simple y seguro.

## Alternativa descartada

Mantener un único `Item Price` sobrescrito y confiar en el fallback nativo. Descartada:
pierde el histórico y aplica precios de la semana equivocada sin aviso.
