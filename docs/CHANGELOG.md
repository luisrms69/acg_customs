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

### Dependencias
- `required_apps = ["erpnext"]`.

## [0.0.1] — 2026-09-30

### Added
- Scaffold inicial del app
