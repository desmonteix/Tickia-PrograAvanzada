# Normalización del modelo hasta 3FN

Modelo actual: **17 tablas base, 22 FK y 3 vistas**. Los 15 CSV originales
permanecen intactos; los catálogos de provincias y departamentos se obtienen
del CSV de distritos. La ampliación conserva sus IDs y valores.

## Primera y segunda forma normal

Cada tabla tiene una PK y cada celda representa un valor de su dominio.
Los ítems, pagos, envíos, reseñas y favoritos son filas independientes, no
listas dentro de la tabla pedidos. El destino se expresa mediante una FK.
El JSON que recibe la interfaz se construye en una vista de lectura.

Las dos tablas puente tienen claves compuestas:

- `pedido_detalle(id_pedido, id_variante)`: cantidad y precio acordado dependen
  de toda la combinación. El precio histórico puede variar entre pedidos;
  no equivale al precio actual de productos y no depende solo de la variante.
- `favoritos(id_usuario, id_producto)`: la fecha corresponde al favorito de
  ese usuario sobre ese producto, no a una sola de las dos entidades.

Las demás PK son simples: no presentan dependencias de una parte de la clave.

## Dependencias funcionales de las tablas base

La siguiente tabla resume las dependencias del dominio. Los IDs de entidades
referenciadas determinan sus datos descriptivos en su propia tabla.

| Relación | Clave y atributos dependientes |
| --- | --- |
| departamentos | id_departamento → nombre; nombre es clave alternativa |
| provincias | id_provincia → id_departamento, nombre; (id_departamento, nombre) es clave alternativa |
| distritos | id_distrito → id_provincia, nombre |
| usuarios | id_usuario → id_distrito, nombre, email, registro y atributos de cuenta |
| vendedores | id_vendedor → id_usuario, razón social, reputación registrada |
| categorias | id_categoria → id_padre, nombre |
| productos | id_producto → id_vendedor, id_categoria, título, precio actual, descripción, imagen |
| variantes | id_variante → id_producto, talla, color, stock |
| cupones | id_cupon → código, porcentaje, vencimiento |
| pedidos | id_pedido → comprador, cupón, fecha, estado, total acordado, distrito de entrega |
| pedido_detalle | (id_pedido, id_variante) → cantidad, precio unitario acordado |
| pagos | id_pago → id_pedido, método, monto, estado y fecha del pago |
| couriers | id_courier → nombre, costo base, estrategia |
| envios | id_envio → pedido, courier, fechas y costo del envío |
| resenas | id_resena → producto, usuario, estrellas, comentario, fecha |
| preguntas | id_pregunta → producto, usuario, pregunta, respuesta, fecha |
| favoritos | (id_usuario, id_producto) → fecha |

No se asume que nombres de provincias o distritos sean únicos nacionalmente.
La identidad de provincia se contextualiza por departamento. Un email del
histórico tampoco se considera una clave: el conjunto tiene cinco repetidos.

## Dependencias transitivas eliminadas

Antes, distritos almacenaba provincia y departamento como texto. Ahora:

```mermaid
flowchart LR
    D[Distrito] --> P[Provincia]
    P --> R[Departamento]
```

`distritos` conserva únicamente `id_provincia`; `provincias` conserva únicamente
`id_departamento`. Sus nombres se reconstruyen con `v_distritos`.

Se retiraron de pedidos `subtotal`, `descuento`, `costo_envio` y `destino`.
`v_pedidos_importes` calcula subtotal desde detalle, costo desde envíos y descuento
como diferencia frente al total acordado. Así no se mantienen variables
independientes que puedan contradecirse por la igualdad entre importes.
La antigua ubicación JSON se traslada a `id_distrito_entrega`, con FK.

El total acordado sí se conserva: es un hecho comercial histórico. No se
recalcula con el precio vigente del producto ni con un cupón que podría cambiar.
Los pagos y envíos admiten varios registros por pedido y representan sus propios
hechos, no atributos transitivos del comprador o del courier.

En el CSV histórico, el total del pedido excluye envío; los pedidos web y NumPy
incluyen la tarifa. La vista respeta esa diferencia explícita por `origen`.

## Representaciones físicas y vistas

`auth_email` es una columna generada por MySQL para implementar la unicidad
condicional de cuentas con contraseña. No es un dato de negocio editable ni
un segundo origen del email. Es una representación técnica del índice; el
análisis lógico de 3FN trata email como atributo único de la cuenta.

Las vistas pueden reunir datos de varias relaciones y calcular agregados:
no son tablas base adicionales ni requieren volver a guardar esos resultados.
La reputación registrada del vendedor y las estrellas calculadas de las reseñas
se muestran como medidas distintas; no se presupone que un texto de reseña
identifique un pedido o determine sus fechas de envío.

## Migración y comprobación

`academic/schema_upgrade.py` respalda los valores trasladados en `.local/pre-3fn-*.json`,
reconstruye todos los distritos y verifica los importes web antes de retirar
columnas redundantes. Se preservan cuentas, contraseñas, IDs, stock y pedidos.
Una incoherencia detiene el traslado correspondiente en lugar de inventar datos.

Las pruebas comprueban los 65 distritos contra el CSV, las claves compuestas,
las 22 FK, la compra, sus importes y la migración de la versión anterior.
También se verificó una instalación desde una base vacía con los 15 CSV.

La 3FN se justifica con las dependencias del dominio, no solo contando tablas.
La auditoría automática comprueba sus condiciones estructurales; esta revisión
explica la semántica de los atributos y las claves.

Referencia conceptual: [normalización de bases de datos, Microsoft](https://learn.microsoft.com/en-us/previous-versions/troubleshoot/microsoft-365/microsoft-365-apps/access/database-normalization-description).
