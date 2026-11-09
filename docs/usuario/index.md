# Manual de usuario

Guías operativas de `acg_customs`. Cada flujo es *fail-closed*: ante cualquier
inconsistencia, el sistema se detiene y reporta en lugar de generar documentos
incorrectos.

## Flujos

- [Importador de precios](importador-precios.md) — carga del Excel semanal de costos (una
  hoja por archivo), vigencia e histórico, y detección de variaciones.
- [Importador de pedidos](importador-pedidos.md) — carga del pedido del proveedor y
  generación de Órdenes de Venta por sucursal con precio vigente a la fecha.
- [Conciliación de totales de OV](conciliacion-ov.md) — verificación posterior del
  total de cada OV contra el total del Excel del proveedor.

## Orden operativo semanal

1. **Importar precios** de la semana (vigencia desde/hasta) y aplicarlos.
2. **Importar el pedido** indicando la fecha del pedido; correr el preflight.
3. **Generar las OV** (quedan en borrador) y revisar el **resumen de conciliación**.
4. Someter a facturación únicamente las OV conciliadas (`PASS`).
