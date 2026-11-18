# Consultas SQL y análisis avanzados

Las **13 consultas ejecutables** están identificadas con `-- name:` en
[`03_consultas.sql`](../sql/03_consultas.sql). El panel **Análisis** combina esos
reportes SQL con seis transformaciones Pandas; el diagnóstico SQL de apoyo se
entrega en el archivo, mientras el panel utiliza el diagnóstico Pandas.
En total, el panel ofrece **18 reportes exportables**.

| Consulta | Técnica | Pregunta que responde |
| --- | --- | --- |
| categorias | WITH RECURSIVE | ¿Cuál es la ruta y profundidad de cada categoría? |
| ventas_distrito | JOIN de seis fuentes, GROUP BY | ¿Qué vende cada vendedor en cada distrito? |
| stock | JOIN de tres tablas | ¿Qué variantes están agotadas o tienen stock crítico? |
| diagnostico_sql | CTE y agregaciones independientes | ¿Qué vendedores combinan mala reputación y retrasos? |
| resenas_producto | JOIN de cuatro tablas | ¿Cuántas reseñas y estrellas recibe cada producto/categoría? |
| favoritos_categoria | JOIN de cuatro tablas y COUNT DISTINCT | ¿Qué categorías y vendedores generan interés? |
| entregas_departamento | JOIN de cinco fuentes | ¿Cuánto demora cada courier por departamento? |
| ranking_vendedores | RANK, SUM OVER | ¿Quién lidera y cuánto acumulan los vendedores ordenados por venta? |
| ventas_mensuales | CTE, LAG, SUM OVER particionado | ¿Cómo cambia la venta respecto al mes observado anterior? |
| clientes_inactivos | LAG, CTE encadenadas, DENSE_RANK | ¿Qué clientes recurrentes exceden su cadencia de compra? |
| participacion_categorias | DENSE_RANK y ventanas globales/acumuladas | ¿Qué categorías concentran las ventas? |
| riesgo_courier | CTE, STDDEV_POP, Wilson y ranking particionado | ¿Cómo varía el riesgo de retraso dentro de cada departamento? |
| afinidad_sql | Autounión de canastas, CTE y métricas de asociación | ¿Qué pares se compran juntos con mayor frecuencia? |

`v_distritos` es una proyección de tres tablas normalizadas. Por eso las seis
fuentes de ventas_distrito expanden a más tablas físicas. No se presenta una
vista como si fuera una única tabla base al explicar el modelo.

## Interpretación de las métricas

RANK y DENSE_RANK conservan los empates según ventas. Los acumulados agregan
el ID al orden y usan `ROWS UNBOUNDED PRECEDING` para evitar resultados ambiguos.
LAG se particiona por vendedor o cliente: no mezcla sus historiales. En ventas
mensuales compara observaciones existentes, sin inventar meses sin operaciones.

La inactividad requiere al menos tres pedidos y una recencia superior a
`MAX(30 días, 2 × intervalo medio entre compras)`. La fecha de referencia es
el día posterior a la última compra del conjunto, no la fecha de ejecución.
La prioridad se ordena por valor monetario histórico; no predice una baja con certeza.

Participación divide ventas de categoría entre ventas de todas las categorías.
La participación acumulada final es 100%. Se habla de ventas brutas, no de
utilidades: el dataset no incluye costos de adquisición.

Riesgo de courier exige al menos 30 envíos válidos con promesa conocida por
courier/departamento. Se presentan media, dispersión, tasa tardía y un intervalo
aproximado de Wilson al 95% (z=1,96). El intervalo presupone observaciones
independientes; envíos de un mismo pedido o factores compartidos pueden limitar
esa interpretación. El ranking compara couriers dentro del mismo departamento,
sin afirmar que estos causen todas las demoras.

Afinidad deduplica cada producto por pedido antes de la autounión. Muestra hasta
100 parejas con cinco o más pedidos conjuntos: soporte, confianza A→B y B→A,
y lift. Ninguna pareja incluye un producto consigo mismo ni cuenta sus tallas
como productos distintos. El reporte Pandas de co-compras conserva la salida
completa, sin el límite de 100 de esta consulta SQL.

## Vistas, índices y control en la base

- `v_distritos`: reconstrucción geográfica a partir de tres catálogos.
- `v_pedidos_importes`: cabecera, importes calculados y destino reconstruido.
- `v_ventas_vendedor`: ventas históricas por vendedor, reutilizadas en el ranking.
- `confirmar_pedido`: transacción de stock, pedido, detalle, pago y envío.
- `tr_pedido_validar_estado`: rechaza transiciones ilegales incluso desde SQL directo.

`05_indices.sql` añade índices para historial por usuario/fecha, histórico por
origen/estado/fecha, precio, categoría/precio, stock, reseñas por usuario/producto
y reputación. Se conservan índices de PK/FK y email. La auditoría exporta EXPLAIN
para stock e historial; un B-tree no se presenta como acelerador de búsquedas
de texto con LOCATE.

Pruebas reales verifican límites de partición de LAG, acumulados, porcentajes,
intervalos y denominadores. Los reportes SQL del histórico excluyen pedidos
web y generados; stock muestra el inventario actual.

Referencias: [ventanas MySQL](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html),
[vistas MySQL](https://dev.mysql.com/doc/refman/8.4/en/create-view.html),
[triggers MySQL](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html),
[intervalo de Wilson, NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
