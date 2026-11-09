# Importador de precios

DocType: **ACG Price Import**. Carga el Excel semanal de costos y actualiza los
`Item Price` de la Price List del Customer, conservando el histórico por fechas.

## Flujo

1. Crear un **ACG Price Import**, adjuntar el Excel (se guarda como archivo privado
   con SHA-256) y elegir el Customer (su `default_price_list` determina la lista).
2. Indicar la **semana/hoja** y el **periodo de vigencia** (ver abajo).
3. Correr **Preflight** (botón). El resultado es `Preflight Passed` o `Preflight Failed`
   con el detalle por código y un comparativo por línea.
4. Si pasó, **Aplicar precios**. Se crean/actualizan los `Item Price` con la vigencia
   indicada. El estado pasa a `Applied`.

## Un archivo = una semana (*fail-closed*)

El archivo de precios debe traer **una sola hoja de precios** (la semana a importar).

- **Más de una hoja de precios → ARCHIVO INCORRECTO:** el preflight **falla** e indica
  cuántas hojas trae. **No se selecciona** ni se elige automáticamente ninguna: debes subir
  el archivo de la semana correspondiente. (Esto evita aplicar precios de otra semana.)
- **Una sola hoja:** se usa esa, pero igual debes **confirmar el periodo de vigencia**
  (`Vigente desde` / `Vigente hasta`) antes de aplicar.

## Vigencia e histórico

Campos **Vigente desde** (`valid_from`, obligatorio) y **Vigente hasta** (`valid_upto`,
opcional; vacío = abierto). Al **aplicar**, el sistema no duplica ni destruye el histórico;
compara cada producto contra su **precio vigente anterior**:

| Situación | Acción sobre `Item Price` |
|---|---|
| **Precio nuevo** (sin precio previo) | Crea una ventana `[desde, hasta]`. |
| **Precio sin cambios** (= al vigente anterior) | **Conserva** el registro existente y **extiende** su vigencia (no crea otro). |
| **Precio modificado** (≠ al vigente anterior) | **Cierra** la ventana anterior (hasta el día previo) y **crea** una nueva. |
| **Producto ausente del archivo** | No se modifica su precio. |

- Al facturar, ERPNext elige nativamente el precio cuya vigencia cubre la fecha del pedido.
- **Retroactivas y parciales** soportadas; la vigencia se **recorta** para no solaparse con
  la ventana siguiente (sin ambigüedad).
- **Idempotencia:** reimportar la misma semana con el mismo costo **no crea registros** ni
  altera precios históricos.

## Variaciones anormales

- **Umbral de variación (%)** (`variation_threshold_pct`, default **20%**).
- Una variación de precio mayor al umbral respecto al precio previo **no bloquea**,
  pero genera **advertencia** y marca la línea (`abnormal`), para revisión del operador.

## Comparativo (vista previa)

Cada línea (`ACG Price Import Line`) muestra: código, item, `previous_rate`,
`new_rate`, `variation_pct`, `abnormal`, `valid_from`/`valid_upto` y la `action`:

| action | significado |
|---|---|
| `new` | ventana de vigencia nueva para el item |
| `changed` | misma ventana, costo distinto |
| `unchanged` | misma ventana, mismo costo |
| `unresolved` | código no resuelto (no existe exclusión) → **FAIL** |
| `skipped` | código fuera de catálogo con exclusión activa → no aplica, no falla |

## Códigos fuera de catálogo

DocType **ACG External Code Exclusion** (`customer` + `external_code` + `enabled`).
Un código no resoluble con exclusión activa se marca `skipped` (no es error). El resto
de no resueltos mantiene el **FAIL** (la exclusión no oculta otros errores).

## Permisos

System Manager y Sales Master Manager.
