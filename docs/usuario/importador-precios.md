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

## Selección de semana (obligatoria, *fail-closed*)

El archivo de precios puede traer **varias hojas** (una por semana).

- **Varias hojas:** el campo **Hoja / semana** (`sheet_name`) es **obligatorio**. Si no
  se elige, el preflight **falla** y lista las hojas candidatas (`detected_sheets`).
  El sistema **nunca** toma la primera hoja por su cuenta.
- **Una sola hoja:** se preselecciona, pero igual debe **confirmarse el periodo de
  vigencia** antes de aplicar.

## Vigencia e histórico

- Campos **Vigente desde** (`valid_from`, obligatorio) y **Vigente hasta** (`valid_upto`,
  opcional; vacío = abierto). Cada corrida escribe esos valores en el `Item Price`.
- **No se sobrescriben** otras ventanas de vigencia: el histórico se conserva. Al
  comprar/facturar, ERPNext elige nativamente el precio cuya vigencia cubre la fecha.
- **Importaciones retroactivas y parciales** son válidas. Si la vigencia nueva se
  **solapa** con otra ventana existente, se emite una **advertencia** (no se destruye
  información).
- **Idempotencia:** reimportar la misma semana (mismo `valid_from`) con el mismo costo
  no duplica `Item Price`; un costo distinto en la misma ventana se marca `changed`.

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
