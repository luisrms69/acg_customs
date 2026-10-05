# Changelog — acg_customs

## [Unreleased]

### Added
- Infraestructura comun del importador de pedidos: DocTypes `ACG Order Provider`,
  `ACG Order Provider User`, `ACG Order Import` y su tabla hija `ACG Order Import Sales Order`.
- Segregacion por proveedor server-side y fail-closed (4 capas: `permission_query_conditions`
  y `has_permission` para `ACG Order Import` y `File`); asociacion usuario->proveedor resuelta
  solo desde `ACG Order Provider User` (gestionada por System Manager).
- Archivo Excel original conservado como Private File con SHA-256 y nombre; `provider` inmutable
  (`set_only_once`) y forzado server-side (anti-spoofing).
- `after_migrate` asegura el rol generico `ACG Order Importer` (sin sembrar proveedores reales).
- DocType `ACG Order Branch Mapping` (solo System Manager): resuelve de forma determinista
  `(customer, external_branch_code) -> Address Shipping` ligado al Customer; unicidad por
  `mapping_key`; fail-closed si falta/deshabilitado/incoherente. Sin Custom Field en Address
  ni parseo de `address_title`.
- Parser + preflight server-side del importador (`order_import/`): deteccion de perfil por
  estructura (registro multi-perfil), extraccion de sucursales/productos/cantidades, y
  resolucion fail-closed de sucursal (branch mapping) y producto (`Item Customer Detail.ref_code`).
  Resumen auditable en `preflight_summary` (JSON) con veredicto PASS/FAIL. No crea Sales Orders.
  - Perfil `comercial_grid_v1` (hoja `PEDIDO COMERCIAL`) y perfil `pedido_grid_v2` (hoja `PEDIDO`,
    corte del grid en la primera columna agregada `TOTAL`).
  - Reglas de columnas: columnas `TOTAL` = agregados ignorados; claves "sucias" normalizadas al
    entero inicial; columna con nombre sin clave y con pedido -> FAIL.
- Creacion de Sales Orders (`order_import/apply.py`): una OV por sucursal con qty>0 desde un
  import en `Preflight Passed`; Customer/Company desde `ACG Order Provider`; Shipping Address desde
  el branch mapping; qty = cantidad original. Idempotente por `(import, external_branch_code)`,
  transaccional (savepoint + rollback, fail-closed) y segregado (`check_permission`). Cada OV se
  registra en `ACG Order Import Sales Order`.

### Changed
- `ACG Order Provider`: campos `customer` y `company` (config por sitio).
- `ACG Order Import.status`: nuevo estado `Applied`.
- `ACG Order Import Sales Order`: campos `external_branch_code` y `address` (auditoria/idempotencia).

### Dependencias
- `required_apps = ["erpnext"]`. La facturacion con addenda del cliente es un paso posterior que vive
  en `facturacion_mexico` (dependencia de despliegue del sitio, no de codigo); por eso NO se declara
  como `required_app`.

## [0.0.1] — 2026-09-30

### Added
- Scaffold inicial del app
