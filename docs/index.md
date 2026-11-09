# acg_customs

Personalizaciones de ERPNext/Frappe para clientes CNAP. El app automatiza el ciclo
semanal de **precios** y **pedidos** de un proveedor de productos frescos hacia un
retailer, apoyándose en mecanismos nativos de ERPNext (Price List, Item Price,
Sales Order) y agregando controles *fail-closed* y auditables.

## Qué resuelve

- **Importación de precios** desde un Excel semanal, con selección explícita de la
  semana, vigencias nativas (`Item Price.valid_from`/`valid_upto`) y detección de
  variaciones anormales.
- **Importación de pedidos** desde el Excel del proveedor, generando una Orden de
  Venta (OV) por sucursal con el precio vigente a la fecha del pedido.
- **Conciliación de totales de OV** contra el total declarado por el proveedor en su
  Excel, por sucursal, dejando las OV en borrador hasta que el operador las revise.

## Por dónde empezar

- [Manual de usuario](usuario/index.md) — cómo operar cada flujo.
- [Arquitectura](tecnico/arquitectura.md) — módulos, flujos y DocTypes.
- [Referencia de DocTypes y campos](referencia/doctypes.md).
- [Decisiones de arquitectura (ADR)](adr/index.md).
- [Changelog](CHANGELOG.md).

## Base técnica

- Frappe 16.x / ERPNext 16.x (`required_apps = ["erpnext"]`).
- Toda la lógica de precios, impuestos y totales se delega a ERPNext nativo; el app
  solo **extrae** datos del Excel y **orquesta/valida** el flujo.
