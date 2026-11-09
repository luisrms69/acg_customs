# Referencia de DocTypes y campos

Referencia de los DocTypes propios de `acg_customs` y de los campos relevantes para
operación y auditoría. (El comportamiento se documenta en el
[Manual de usuario](../usuario/index.md); aquí va la referencia estructural.)

## Importador de precios

### ACG Price Import
Carga semanal de costos; preflight *fail-closed* + apply transaccional de `Item Price`.
Permisos: System Manager, Sales Master Manager.

| Campo | Tipo | Nota |
|---|---|---|
| `customer` | Link Customer | determina `default_price_list` |
| `price_list` | Link Price List | tomada del Customer |
| `sheet_name` | Data | hoja/semana a importar (obligatoria si hay varias) |
| `detected_sheets` | Small Text | hojas candidatas detectadas (read-only) |
| `valid_from` / `valid_upto` | Date | vigencia de la corrida (desde obligatoria) |
| `variation_threshold_pct` | Percent | umbral de variación anormal (default 20) |
| `status` | Select | `Uploaded → Preflight Passed/Failed → Applied` |
| `excel_file` / `file_sha256` | Attach / Data | archivo privado + hash |
| `lines` | Table | comparativo (`ACG Price Import Line`) |

### ACG Price Import Line (child)
Comparativo por código: `code`, `item`, `description`, `previous_rate`, `new_rate`,
`variation_pct`, `abnormal`, `valid_from`, `valid_upto`, `action ∈ {new, changed,
unchanged, unresolved, skipped}`.

### ACG External Code Exclusion
Códigos fuera de catálogo por `(customer, external_code)` + `enabled` + `reason`;
unicidad por `(customer, external_code)`. Alimenta `skipped` en el preflight de precios.
Permisos: System Manager, Sales Master Manager.

## Importador de pedidos

### ACG Order Provider
Perfil de proveedor (`customer` + `company` por sitio). Base de la segregación.

### ACG Order Provider User
Asociación usuario → proveedor. Única fuente para `get_user_provider`. La gestiona
System Manager.

### ACG Order Import
Carga del Excel de pedido; preflight/apply.

| Campo | Tipo | Nota |
|---|---|---|
| `provider` | Link ACG Order Provider | inmutable (`set_only_once`), forzado server-side |
| `order_date` | Date | fecha del pedido → `transaction_date` de las OV y fecha de vigencia exigida |
| `total_tolerance` | Currency | tolerancia de conciliación (default 0.01) |
| `status` | Select | `Uploaded → Preflight Passed/Failed → Applied` |
| `excel_file` / `file_sha256` | Attach / Data | archivo privado + hash |
| `sales_orders` | Table | OV creadas + conciliación (`ACG Order Import Sales Order`) |

### ACG Order Import Sales Order (child)
Auditoría/idempotencia de las OV + conciliación por sucursal:
`external_branch_code`, `address`, `sales_order`, `reconciliation_status ∈ {PASS,
WARNING, SIN VALIDAR}`, `excel_total`, `erp_total`, `reconciliation_diff`.

### ACG Order Branch Mapping
Resuelve `(customer, external_branch_code) → Address Shipping` de forma determinista;
unicidad por `mapping_key`; *fail-closed*. Solo System Manager.

## Dimensión contable

Accounting Dimension nativa `ACG Order Provider` → campo `acg_order_provider` en Sales
Order / Sales Invoice (asegurada idempotente en `after_migrate`).
