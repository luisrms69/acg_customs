# Changelog — acg_customs

## [0.2.0] — 2026-11-08

### Added
- Importador de precios multi-bloque: el parser lee **todos** los bloques de columnas
  `CODIGO | DESCRIPCION | COSTO` de la hoja (antes solo el primero, dejando sin
  actualizar ~la mitad del catálogo).
- Un archivo = una semana (*fail-closed*) en `ACG Price Import`: si el libro trae **más de
  una hoja de precios** → **ARCHIVO INCORRECTO** (FAIL). No hay selección de hoja. Se exige
  confirmar la vigencia del periodo (`valid_from`). Ver ADR-0001.
- Vigencia nativa de precios con **modelo temporal** (crear / extender / cerrar): al aplicar,
  precio nuevo → crea ventana; precio sin cambios → **conserva y extiende** (no duplica);
  precio modificado → **cierra** la ventana anterior y crea una nueva. Recorte para no
  solapar; retroactivas y parciales; reimport idéntico idempotente. Ver ADR-0003.
- Detección de variación anormal: `variation_threshold_pct` (default 20%) → advertencia y
  flag `abnormal` por línea. Comparativo enriquecido (`variation_pct`, `valid_from`,
  `valid_upto` en `ACG Price Import Line`).
- `ACG Order Import.order_date` (fecha del pedido) → `transaction_date` de las OV.
- Preflight de OV con **precio vigente por fecha**: exige `Item Price` cuya vigencia cubra
  `order_date`; sin cobertura → FAIL, **sin aceptar el fallback nativo** de ERPNext.
- Conciliación de totales de OV (Opción B): las OV se crean en borrador y se comparan, por
  sucursal, contra el total del Excel (`total_tolerance` default $0.01) →
  `PASS`/`WARNING`/`SIN VALIDAR`. Extracción del total por `profile`
  (`total_row_position`: `comercial_grid_v1` after-products, `pedido_grid_v2`
  before-products). Campos de conciliación en `ACG Order Import Sales Order`. Ver ADR-0002.
- Documentación MkDocs del app (usuario, arquitectura, referencia, ADR) alineada al
  estándar de `frappe-infrastructure`.

### Changed
- `price_import/parser.py`: extracción multi-hoja/multi-bloque como función pura.
- `price_import/service.py`: comparativo por ventana de vigencia + variación + solapes.
- `order_import/apply.py`: `transaction_date = order_date`; conciliación posterior; OV en
  borrador.
- `CLAUDE.md`: se retira la documentación del app (DocTypes) — ahora vive en `docs/`;
  CLAUDE.md queda con instrucciones y baseline.

## [0.1.0] — 2026-10-30

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
- GUI minima de `ACG Order Import`: botones de preflight / crear Sales Orders, indicadores de
  estado en la lista y panel HTML con el resumen de preflight.
- Dimension contable de proveedor: Accounting Dimension nativa `ACG Order Provider` que crea el
  campo `acg_order_provider` en Sales Order / Sales Invoice (asegurada idempotente en
  `after_migrate`); las Sales Orders generadas quedan etiquetadas por proveedor.
- Pricing nativo en Sales Orders: la OV toma `selling_price_list` desde
  `Customer.default_price_list` (Price List nativa) en vez de forzar `rate=0`; fail-closed ante
  precio faltante (rollback transaccional).
- Importador semanal de precios: DocType `ACG Price Import` y su tabla hija `ACG Price Import Line`.
  Preflight fail-closed (estructura, CODIGO/COSTO validos, duplicados conflictivos, Item
  inexistente/ambiguo) con resolucion `CODIGO -> Item` por `Item Customer Detail.ref_code`; apply
  transaccional que hace upsert de un `Item Price` vigente por `(Item, Price List)`, con comparativo
  `previous/new/action` para auditoria, idempotencia por estado + SHA-256, archivo adjunto privado y
  permisos `System Manager` + `Sales Master Manager`. GUI minima (preflight / aplicar precios, panel
  HTML, indicadores).
- DocType `ACG External Code Exclusion` (`customer` + `external_code` + `enabled` + `reason`;
  unicidad por `(customer, external_code)`; permisos `System Manager` + `Sales Master Manager`;
  datos por sitio, no fixtures). El preflight de precios marca como `skipped` los codigos no
  resueltos que tengan exclusion activa (no son error, no provocan FAIL, suman `summary.skipped` y
  conservan datos para auditoria); el resto de no resueltos sigue en FAIL sin ocultar otros errores.

### Changed
- `ACG Order Provider`: campos `customer` y `company` (config por sitio).
- `ACG Order Import.status`: estado inicial `Uploaded` (antes `Draft`) y nuevo estado `Applied`;
  campo `preflight_report_html` para el panel de resultado.
- `ACG Order Import Sales Order`: campos `external_branch_code` y `address` (auditoria/idempotencia).
- `order_import/apply.py`: fija `selling_price_list` desde el Customer y retira el `rate=0` forzado.
- `ACG Price Import Line.action`: amplia opciones con `skipped`.

### Dependencias
- `required_apps = ["erpnext"]`. La facturacion con addenda del cliente es un paso posterior que vive
  en `facturacion_mexico` (dependencia de despliegue del sitio, no de codigo); por eso NO se declara
  como `required_app`.

## [0.0.1] — 2026-09-30

### Added
- Scaffold inicial del app
