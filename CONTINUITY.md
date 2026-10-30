# CONTINUITY.md — acg_customs

**Fecha:** 2026-10-30
**Rama activa:** `feat/order-import-infrastructure`
**Tarea actual:** Primer PR del app (v0.1.0) hacia `version-16` con todo el bloque de importación.

---

## Recuperación rápida

Estoy trabajando en:
Cierre del primer bloque funcional de `acg_customs` y su publicación: importador de pedidos,
importador de precios y exclusiones, ya commiteado.

Plan que estoy siguiendo:
Flujo `/ship pr` sobre el repo `luisrms69/acg_customs` (remoto `upstream`, `version-16` protegida
por el ruleset estándar).

Objetivo inmediato:
Crear el PR `feat/order-import-infrastructure → version-16` (v0.1.0) y, tras CI, endurecer el ruleset
con `required_status_checks` (Paso 9e del scaffold).

Criterio de avance:
PR abierto, CI corriendo, y los datos maestros pendientes resueltos antes del merge.

---

## Estado actual

### Ya cerrado
- Código: importador de pedidos (infra, GUI, branch mapping, Sales Orders), dimensión contable de
  proveedor, pricing nativo, `ACG Price Import` + `ACG Price Import Line`, `ACG External Code Exclusion`
  + soporte `skipped`.
- Tests: 70/70 OK (`--lightmode`); ruff limpio; prettier aplicado.
- Repo `luisrms69/acg_customs` creado; remoto `upstream` HTTPS; `version-16` + feature publicadas;
  default branch `version-16`; ruleset `version-16-protection` activo (9b).

### En progreso
- `/ship pr`: bump a 0.1.0, CHANGELOG, docs y CONTINUITY listos; falta push de estos commits + crear PR.

### Pendiente inmediato
1. Push de los commits de release/doc + `gh pr create` hacia `version-16`.
2. Tras primer CI: Paso 9e (`required_status_checks` reales: `Server`, `Frappe Linter`, `Vulnerable Dependency Check`).
3. Datos maestros pendientes (bloquean el flujo de precios, no el código): ver notas privadas del cliente.

### No repetir
- No reintentar el PRIMER push del árbol a repo público desde el agente: lo bloquea el auto-mode classifier;
  ese push lo ejecuta el operador. Los pushes incrementales posteriores sí funcionan.
- No genericizar "CNAP" / `it@buzola.mx`: son del vendor (ver memoria), no datos de cliente.

---

## Decisiones vigentes
- Quedan algunos códigos del archivo de precios pendientes de dato maestro (nombre/UOM) y un conjunto
  marcado fuera de catálogo gestionado vía `ACG External Code Exclusion` (datos por-sitio, no fixtures).
  Los valores concretos (códigos, productos, correcciones de ref_code) viven **fuera del repo** (notas
  privadas / sitio del cliente), nunca en este repositorio público.

---

## Archivos relevantes ahora

### Leer primero
- `docs/CHANGELOG.md` — alcance de v0.1.0.
- `acg_customs/acg_customs/price_import/service.py` — preflight/apply + exclusión/skipped.

### Probablemente editar
- (tras merge) ruleset vía `gh api` para el Paso 9e.

### No tocar
- Datos reales del sitio de desarrollo; `one_offs/` (gitignored).

---

## Riesgos / cuidados
- El preflight real del archivo de precios sigue en FAIL **solo** por los datos maestros pendientes (esperado).
- Despliegue/DNS del dominio de producción está fuera de alcance de este PR (vhost/cert aún no provisionados).

---

## Información faltante
- Confirmación del cliente sobre los datos maestros pendientes (nombre/UOM) para cerrar el flujo de
  precios (apply + E2E final). Esa información se mantiene fuera del repo.
