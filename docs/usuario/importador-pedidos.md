# Importador de pedidos

DocType: **ACG Order Import**. Carga el Excel del pedido del proveedor y genera una
**Orden de Venta (OV) por sucursal**, con el precio vigente a la fecha del pedido.

## Flujo

1. Crear un **ACG Order Import**, adjuntar el Excel (archivo privado + SHA-256) y
   elegir el **Proveedor** (`ACG Order Provider`), que determina Customer y Company.
2. Indicar la **Fecha del pedido** (`order_date`, default hoy).
3. Correr **Preflight**: valida estructura, resuelve sucursales y productos, y verifica
   el **precio vigente a la fecha** (ver abajo). Resultado `Preflight Passed`/`Failed`.
4. **Generar Sales Orders**: una OV por sucursal con cantidad > 0. Las OV quedan en
   **borrador** y se concilian (ver [Conciliación de OV](conciliacion-ov.md)).

## Fecha del pedido y precio vigente

- La **Fecha del pedido** (`order_date`) se captura **en el formulario** (por defecto hoy);
  **no se lee del Excel**. Ajústala a la fecha real del pedido antes del preflight.
- La `order_date` fija la `transaction_date` de las OV. ERPNext selecciona el `Item Price`
  cuya vigencia cubre esa fecha.
- **Preflight de precio por fecha (*fail-closed*):** cuando el Customer tiene
  `default_price_list`, el preflight exige que **cada producto resuelto** tenga un
  `Item Price` cuya vigencia (`valid_from`/`valid_upto`, nulos = abiertos) **cubra la
  fecha del pedido**. Si ninguna ventana la cubre, el preflight **falla** y lista los
  productos sin precio vigente.
- **No se acepta el fallback nativo** de ERPNext (tomar el precio más reciente cuando
  ninguna ventana cubre la fecha): eso evitaría aplicar un precio de otra semana.

## Resolución *fail-closed*

- **Sucursal:** `ACG Order Branch Mapping` resuelve `(customer, external_branch_code) →
  Address Shipping` de forma determinista. Sucursal faltante/ambigua → FAIL.
- **Producto:** se resuelve por `Item Customer Detail.ref_code`. Producto
  inexistente/ambiguo → FAIL (el sistema no inventa el producto).
- Columnas sin clave de sucursal con pedido, cantidades no numéricas, etc. → FAIL.

El resumen del preflight distingue **«Sucursales con pedido»** (las reales de esta corrida,
clave única con cantidad > 0) de **«Columnas de sucursal en el archivo»** (el catálogo completo
del proveedor; no es el pedido). Una misma clave puede aparecer en varias columnas del catálogo
(p. ej. una columna de respaldo vacía); **eso no genera aviso**. Solo se **advierte** cuando una
clave trae pedido en **más de una columna** (ahí sí se **suman** cantidades y conviene verificar
que correspondan a la misma sucursal).

## Creación de las OV

- Una OV por sucursal; Customer/Company del proveedor; Shipping Address del branch
  mapping; cantidad original del Excel. El **rate** lo resuelve el pricing nativo desde
  la Price List (no se hardcodea). Ninguna línea puede quedar en `rate = 0`.
- Idempotente por `(import, external_branch_code)` y transaccional (todo o nada).
- Cada OV se etiqueta con la **dimensión contable de proveedor** (`acg_order_provider`).

## Segregación por proveedor

Un usuario-proveedor solo ve y opera sus propias importaciones (segregación
*fail-closed* server-side). Las asociaciones usuario→proveedor las gestiona System
Manager vía `ACG Order Provider User`.
