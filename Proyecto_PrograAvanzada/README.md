# Dataset — P4_marketplace

Archivos CSV (UTF-8, separador coma, encabezado en la primera fila, NULL = celda vacía, booleanos 0/1).
El prefijo numérico indica el **orden de carga** que respeta las llaves foráneas.

| # | Archivo | Filas | Columnas |
|---|---|---|---|
| 01 | `01_distritos.csv` | 65 | id_distrito, nombre, provincia, departamento |
| 02 | `02_usuarios.csv` | 45,000 | id_usuario, id_distrito, nombre, email, fecha_registro |
| 03 | `03_vendedores.csv` | 700 | id_vendedor, id_usuario, razon_social, reputacion |
| 04 | `04_categorias.csv` | 110 | id_categoria, id_padre, nombre |
| 05 | `05_productos.csv` | 9,337 | id_producto, id_vendedor, id_categoria, titulo, precio |
| 06 | `06_variantes.csv` | 19,806 | id_variante, id_producto, talla, color, stock |
| 07 | `07_cupones.csv` | 350 | id_cupon, codigo, descuento_pct, vence |
| 08 | `08_pedidos.csv` | 111,016 | id_pedido, id_usuario, id_cupon, fecha, estado, total |
| 09 | `09_pedido_detalle.csv` | 247,482 | id_pedido, id_variante, cantidad, precio_unit |
| 10 | `10_pagos.csv` | 111,528 | id_pago, id_pedido, metodo, monto, estado |
| 11 | `11_couriers.csv` | 8 | id_courier, nombre, costo_base |
| 12 | `12_envios.csv` | 98,076 | id_envio, id_pedido, id_courier, fecha_envio, fecha_entrega, fecha_estimada, costo_envio |
| 13 | `13_resenas.csv` | 40,071 | id_resena, id_producto, id_usuario, estrellas, comentario, fecha |
| 14 | `14_preguntas.csv` | 38,000 | id_pregunta, id_producto, id_usuario, texto, respuesta, fecha |
| 15 | `15_favoritos.csv` | 79,970 | id_usuario, id_producto, fecha |

**Total de registros:** 801,519

## Columnas añadidas al modelo de referencia
- `envios.fecha_estimada` (fecha prometida) y `envios.costo_envio` — para medir entregas tardías y la Strategy de costo de envío.
- `resenas.fecha`, `preguntas.fecha` — para series de tiempo.
- `pagos.estado` toma: aprobado, rechazado, reembolsado, pendiente.

## Patrones sembrados (para que el análisis encuentre algo)
- Categorías en 3 niveles (raíz → sub → hoja): ideal para `WITH RECURSIVE`.
- Pocos vendedores concentran la mayoría de ventas (Pareto); ~9% de vendedores (incluyendo algunos grandes) despachan tarde → más retraso y menos estrellas.
- Couriers con tiempos distintos; provincias (Loreto, Ucayali, Madre de Dios, Puno…) demoran más.
- Clientes recurrentes (distribución gamma) → buena segmentación RFM; picos en mayo, julio, noviembre y diciembre.
- Co-compras: cada producto tiene un "complemento" del mismo vendedor que aparece junto en ~40% de los ítems adicionales.
- ~7% de variantes con stock crítico (0–3).
- `pedidos.total` = Σ(cantidad × precio_unit) × (1 − descuento del cupón).


## Carga en MySQL (ejemplo)
```sql
SET GLOBAL local_infile = 1;
LOAD DATA LOCAL INFILE '01_tabla.csv' INTO TABLE tabla
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
```
Con pandas + SQLAlchemy: `pd.read_csv(f).to_sql(tabla, engine, if_exists='append', index=False, chunksize=5000)`
