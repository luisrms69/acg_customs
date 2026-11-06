# CLAUDE.md — acg_customs

> **Reglas de operación Claude Code** (commits, PRs, base de datos, flujo de trabajo, prohibiciones git):
> Ver `/home/erpnext/Developer/frappe-infrastructure/.claude/CLAUDE.md`

---

## Estado del proyecto

- **App nueva:** creada en frappe-bench-v16 (esqueleto inicial)
- **Bench activo:** `/home/erpnext/frappe-bench-v16`
- **Branch protegida:** `version-16` (nunca commitear directamente — estándar Frappe)
- **Versión:** 0.0.1 (desarrollo inicial)
- **En producción:** No

---

## Sites de desarrollo y prueba

| Site | Bench | Propósito | Notas |
|---|---|---|---|
| `<dev-site>` | frappe-bench-v16 | Desarrollo activo | Features, migrate, export-fixtures |
| `test-acg_customs.localhost` | frappe-bench-v16 | Tests unitarios | Solo para `bench run-tests` — nunca modificar manualmente |

> **Pendiente de infraestructura:** el site de desarrollo (`<dev-site>`) y su puerto aún no existen.
> Se crean fuera de este esqueleto (Pasos 3/4/10 de `/scaffold-frappe-app`: `bench new-site`,
> `install-app`, registro en `frappe-multisite`). Sustituir `<dev-site>` y `<port>` por los valores
> reales al operar.

**Reglas de uso:**
- `bench migrate` → siempre con `--site`. Nunca sin site en bench compartido.
- `bench run-tests` → siempre `test-acg_customs.localhost` — nunca en el site de desarrollo.
- `bench export-fixtures` → `<dev-site>`

**Apps en test-acg_customs.localhost:** frappe, erpnext, acg_customs

## Entorno
Ver contexto global en `frappe-infrastructure/.claude/CLAUDE.md`.

**Comandos frecuentes (bench v16):**
```bash
bench --site <dev-site> migrate
bench --site <dev-site> export-fixtures --app acg_customs
bench --site <dev-site> run-tests --app acg_customs
bench build --app acg_customs
```
**NUNCA:** `bench migrate` sin `--site` — afecta todos los sites del bench compartido

---

## Qué hace esta app

Personalizaciones para ERPNext/Frappe clientes CNAP

---

## DocTypes principales

**Importador de pedidos**
- `ACG Order Provider` — perfil de proveedor (Customer + Company por sitio). Base de la segregación.
- `ACG Order Provider User` — asociación usuario→proveedor (única fuente para `get_user_provider`).
- `ACG Order Import` — carga del Excel de pedido; preflight/apply; estados `Uploaded → Preflight Passed/Failed → Applied`. Campo `order_date` (fecha del pedido): fija la `transaction_date` de las OV y la fecha contra la que el preflight exige precio vigente.
- `ACG Order Import Sales Order` (child) — auditoría/idempotencia de las OV creadas por import.
- `ACG Order Branch Mapping` — `(customer, external_branch_code) → Address Shipping`, determinista y fail-closed.
- **Preflight de OV — precio vigente por fecha:** cuando el Customer tiene `default_price_list`, el preflight exige que cada producto resuelto tenga un `Item Price` cuya vigencia cubra `order_date` (nulos = abiertos). Si ninguna ventana cubre la fecha → FAIL (NO se acepta el fallback nativo de ERPNext al precio más reciente).

**Importador de precios**
- `ACG Price Import` — carga semanal de costos; preflight fail-closed + apply transaccional de `Item Price`; permisos System Manager + Sales Master Manager.
  - **Selección de semana (fail-closed):** si el libro trae varias hojas de precios, exige `sheet_name` explícito (nunca elige la primera); una sola hoja requiere confirmar el periodo. `detected_sheets` lista las hojas candidatas.
  - **Vigencia nativa:** cada corrida escribe `Item Price.valid_from`/`valid_upto` (campos `valid_from`/`valid_upto` del doc). NO sobrescribe otras ventanas → conserva el histórico. Idempotente por ventana `(Item, Price List, valid_from)`. Soporta importaciones retroactivas y parciales; advierte solapamientos.
  - **Variación anormal:** `variation_threshold_pct` (default 20%); una variación mayor genera advertencia y marca la línea (`abnormal`), sin bloquear.
- `ACG Price Import Line` (child) — comparativo por código: `action ∈ {new, changed, unchanged, unresolved, skipped}`, más `previous_rate`/`new_rate`/`variation_pct`/`abnormal`/`valid_from`/`valid_upto`.
- `ACG External Code Exclusion` — códigos fuera de catálogo por `(customer, external_code)`; alimenta `skipped` en el preflight de precios.

**Dimensión contable**
- Accounting Dimension nativa `ACG Order Provider` → campo `acg_order_provider` en Sales Order / Sales Invoice (asegurada en `after_migrate`).

---

## Fixtures

*(pendiente — declarar en hooks.py al crear Custom Fields, Roles, Workspaces)*

---

## Dependencias

**Apps requeridas:** erpnext (`required_apps = ["erpnext"]` en `hooks.py`; CI alineado).
**Apps en frappe-bench-v16:** frappe, erpnext, acg_customs (y otras del bench)
**Dependencias externas:** Ninguna

---

## Tests

```bash
bench --site test-acg_customs.localhost run-tests --app acg_customs
```

**Sin cobertura inicial.** Documentar tests aquí cuando se implementen.
**Site de tests dedicado:** `test-acg_customs.localhost` — nunca correr tests en el site de desarrollo.

---

## REGLAS GIT — ACG_CUSTOMS

### Antes de cada commit

- Correr linters en archivos modificados:
  ```bash
  ruff format <archivos .py modificados>
  npx prettier@2.7.1 --write <archivos .js modificados>
  ```

### Antes de cada PR

- [ ] Linters pasados
- [ ] Fixtures exportados si hubo cambios de Custom Fields, Roles, Workspaces
- [ ] Patch creado si hay cambios de esquema — **requiere autorización explícita**
- [ ] `bench --site <dev-site> migrate` limpio
- [ ] Ver checklist global en `frappe-infrastructure/CONTRIBUTING.md`

### PROHIBICIÓN ABSOLUTA — NUNCA TRABAJAR EN version-16

**`version-16` es la rama protegida de acg_customs. Es el estándar Frappe upstream.**

Nota: otros repos Buzola usan `main` o `develop` por razones históricas.
Los apps nuevos del ecosistema usan `version-16` alineado con frappe/erpnext/hrms.

- **Nunca implementar cambios estando en `version-16`.**
- **Nunca crear commits estando en `version-16`.**
- **Nunca hacer push directo a `version-16`.** Todo cambio entra por PR.
- Todo cambio (incluso documental) debe iniciar en una **rama de trabajo** creada desde `version-16`
  limpio y sincronizado. Convención de prefijos: `feat/ fix/ docs/ chore/ refactor/ hotfix/`
  (ver `CONTRIBUTING.md`).
- `/ship commit` y `/ship push` deben **rechazar** si la rama es `version-16`.
- `/ship pr` debe exigir rama distinta de `version-16` (PR hacia `version-16` como base).

**Única excepción de bootstrap:** el primer commit + primer push a `version-16` (crear el repo remoto
vacío). Esa excepción **termina en cuanto se crea y valida el ruleset** de la rama protegida. Después
de eso, ni un cambio documental va directo a `version-16`.

### Reglas específicas del proyecto

- PRs siempre a `version-16`
- Site de desarrollo: `<dev-site>`
- Site de tests: `test-acg_customs.localhost`
