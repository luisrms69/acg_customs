# CONTINUITY.md — acg_customs

**Fecha:** 2026-11-08
**Rama activa:** `feat/price-import-multibloque`
**Tarea actual:** PR `0.2.0` hacia `version-16` preparado; detenido en el gate `pr-ready` esperando autorización para push + creación del PR.

---

## Recuperación rápida

Estoy trabajando en:
Cierre de la rama con tres funcionalidades (parser multi-bloque, vigencia/selección de
semana/preflight por fecha, conciliación de OV opción B) + adopción de la documentación
MkDocs del estándar. Todo commiteado; falta solo publicar el PR.

Plan que estoy siguiendo:
`/ship pr` (gate `pr-ready`). Documentación en `docs/` (ver `docs/index.md`); decisiones
en ADR-0001 y ADR-0002.

Objetivo inmediato:
Esperar la autorización del usuario en `pr-ready` para `push + PR`. No publicar sin ella.

Criterio de avance:
PR abierto hacia `version-16` con CI en verde; versión `0.2.0`.

---

## Estado actual

### Ya cerrado
- `4f4482a` parser de precios multi-bloque.
- `60ae8fd` selección de semana, vigencia nativa (`Item Price.valid_from/upto`), `order_date` y preflight de precio por fecha.
- `3a4675b` conciliación de totales de OV (opción B) + documentación MkDocs + corrección de `CLAUDE.md`.
- Bump de versión `0.1.0 → 0.2.0`. Suite 91/91 en verde; `mkdocs build --strict` en verde.

### En progreso
- `/ship pr`: PR preparado, **detenido en `pr-ready`** (sin push ni PR hasta autorización).

### Pendiente inmediato
1. Autorizar en `pr-ready` → push + creación del PR hacia `version-16`.
2. Tras merge: `/sync-check` + `/ship release` (tag + GitHub Release `v0.2.0`).

### No repetir
- No documentar el app en `CLAUDE.md` (solo instrucciones + baseline; la doc del app vive en `docs/`).
- No editar `CLAUDE.md` por iniciativa propia.
- No encadenar features en una rama larga: cerrar cada una con su PR.
- No afirmar estado sin verificarlo contra `git`/evidencia.

---

## Decisiones vigentes
- Precios por vigencia nativa; preflight de OV sin fallback nativo (ADR-0001).
- Conciliación de OV posterior a la creación (opción B), OV en borrador (ADR-0002).
- Parser = solo extracción; precios/impuestos/totales = ERPNext nativo.

---

## Archivos relevantes ahora

### Leer primero
- `docs/index.md`, `docs/adr/0001-*.md`, `docs/adr/0002-*.md`.

### Probablemente editar
- Ninguno (rama lista para PR).

### No tocar
- PR #1 / release v0.1.0; `one_offs/` (gitignored); datos de `acg-v16.dev`.

---

## Riesgos / cuidados
- Vigencias solapadas: se advierten, no hay auto-cierre de la ventana previa (deuda conocida, ADR-0001).
- `acg-v16.dev` tiene datos de prueba acumulados (OVs/FVs/Item Prices) de las validaciones.

---

## Información faltante
- Decisión de UX para auto-cierre de ventana de vigencia anterior (follow-up post-PR).
