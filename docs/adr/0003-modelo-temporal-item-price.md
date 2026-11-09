# ADR-0003: Modelo temporal de `Item Price` (crear / extender / cerrar)

**Fecha:** 2026-11-08
**Status:** Activo

## Contexto

La primera versión del apply de precios escribía una ventana `Item Price` por corrida y por
producto. Con imports semanales, esto creaba una ventana **nueva por cada semana aunque el
precio no cambiara**, inflando el histórico con registros redundantes y dificultando la
auditoría. Además, al cambiar un precio no se cerraba la ventana anterior, dejando
solapamientos que solo se resolvían por el orden nativo `valid_from desc`.

Se requiere un manejo temporal que **no duplique** registros cuando el precio no cambia,
que **no destruya** el histórico, y que **cierre** correctamente la vigencia anterior cuando
el precio cambia, soportando importaciones **retroactivas** y **parciales**.

## Decisión

Al aplicar, por cada producto (con costo `R`, vigencia `[D, U]`) se compara contra su
**ventana previa** (la de mayor `valid_from ≤ D`):

| Situación | Acción |
|---|---|
| **Sin ventana previa** (precio nuevo) | Crear `Item Price [D, U]`. |
| **Ventana previa con el mismo costo** | **Conservar** el registro y **extender** su `valid_upto` (no se crea otro). |
| **Ventana previa con costo distinto, mismo `valid_from`** | Corregir en sitio (misma ventana). |
| **Ventana previa con costo distinto, `valid_from` anterior** | **Cerrar** la previa (`valid_upto = D − 1`) y **crear** `[D, U]`. |
| **Producto ausente del archivo** | No se toca. |

Reglas transversales:

- La vigencia `U` se **recorta** a `(valid_from de la ventana siguiente) − 1` para no
  solaparse (sin ambigüedad).
- Nunca se modifica el **costo** de una ventana histórica (solo se cierra su fecha fin).
- El parser **no** participa de esto: solo extrae datos.

## Consecuencias

- El histórico no acumula ventanas redundantes: semanas consecutivas con el mismo precio
  quedan como **una sola** ventana extendida.
- Los cambios de precio quedan registrados como ventanas contiguas sin solape.
- Reimportar una semana idéntica es **idempotente** (no crea ni altera registros).
- Retroactivas y parciales funcionan por construcción (se ancla en la ventana previa/siguiente).
- El `apply` devuelve contadores `new` / `changed` / `unchanged` / `extended` para auditoría.

## Alternativa descartada

Crear siempre una ventana por corrida (incluso sin cambio de precio) y resolver solapes solo
con `valid_from desc`. Descartada: duplica el histórico y deja ventanas abiertas solapadas.
