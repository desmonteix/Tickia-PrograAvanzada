# Informe de análisis del marketplace

Entrega: 18-11-2026. Resultados obtenidos con Pandas 3.1.1 sobre MySQL 8.4,
sin muestreo. Las fuentes originales contienen **801.519 filas en 15 CSV**.
[Conteos y hashes de las fuentes](resultados/fuentes.json) y
[metadatos de la ejecución](resultados/resultados.json).

## Población y método

Se analizan 45.000 clientes, 700 vendedores y 98.871 pedidos del histórico con
estado pagado, enviado o entregado. Se excluyen pendientes y cancelados.
Hay 40.071 reseñas y 96.288 entregas con fechas válidas. Las compras web no
contaminan el histórico: se filtra `origen='dataset'`.

Las ventas por vendedor son brutas de artículos: cantidad × precio unitario,
antes de cupones y sin envío. RFM usa el total de cada pedido válido. No se
suman totales de pedido después de cruzarlos con líneas, porque duplicaría dinero.
Ventas, reseñas y envíos se agregan por separado antes de unir los resultados.

## Segmentación RFM

Referencia: **01-10-2026**, día siguiente a la última compra del conjunto.
R = días desde la última compra; F = pedidos distintos; M = total comprado.
Los puntajes 1–5 usan rangos percentiles con empates promediados; menor recencia
produce mayor R. Los clientes sin compras permanecen con F/M y puntajes cero.

Reglas, en orden: sin compras; campeones si R+F+M ≥ 13; en riesgo si R ≤ 2 y
F ≥ 3; leales si F ≥ 4; nuevos si R ≥ 4 y F ≤ 2; el resto, ocasionales.
Son segmentos educativos, no una clasificación universal de clientes.

| Segmento | Clientes |
| --- | --- |
| Sin compras | 20714 |
| Ocasionales | 10680 |
| Campeones | 4962 |
| Leales | 3075 |
| En riesgo | 2796 |
| Nuevos | 2773 |

## Cohortes y retención

La cohorte es el mes de primera compra. El mes cero siempre tiene 100%.
Cada cliente cuenta una vez por mes, aunque haga varios pedidos. Los meses
observados sin retorno se incluyen con cero; los meses futuros se excluyen.
El gráfico combina cohortes con ponderación por su base de clientes.

Se obtuvieron 561 celdas de retención para 33 cohortes, desde 2024-01 hasta 2026-09.

| Mes desde primera compra | Clientes que regresan | Base expuesta | Retención ponderada (%) |
| --- | --- | --- | --- |
| 0 | 24286 | 24286 | 100.0 |
| 1 | 5180 | 23270 | 22.26 |
| 3 | 2380 | 20999 | 11.33 |
| 6 | 2165 | 17819 | 12.15 |

## Productos que se compran juntos

Se deduplican productos dentro de cada pedido: dos tallas del mismo producto
no constituyen una pareja. Soporte = pedidos con ambos / pedidos con artículos;
confianza A→B = pedidos con ambos / pedidos con A; lift compara esa confianza
con la probabilidad marginal de B. Las letras se ordenan por ID de producto.

Primeras cinco parejas por cantidad de pedidos conjuntos:

| Producto A | Producto B | Pedidos | Soporte (%) | Confianza A→B (%) | Lift |
| --- | --- | --- | --- | --- | --- |
| Coches de bebé Huggies Edición Especial | Biberones Babysec Max | 563 | 0.5694 | 24.5 | 22.1012 |
| Peluches Infanti X | Bloques de construcción Mattel Lite | 215 | 0.2175 | 25.84 | 30.3439 |
| Calefactores Miray Classic | Lavadoras Bosch Ultra | 175 | 0.177 | 24.37 | 70.6689 |
| Bloques de construcción Mattel Lite | Juegos de mesa Lego Classic | 162 | 0.1638 | 19.24 | 31.2873 |
| Alimento para gato Cat Chow Sport | Pañales Infanti Sport | 142 | 0.1436 | 27.84 | 97.9672 |

## Entrega por courier y departamento

Días de entrega = recepción menos despacho. Se excluyen fechas ausentes y
recepciones anteriores al despacho. Recibir el mismo día prometido es puntual;
la tasa de retraso solo divide entre promesas conocidas. El departamento histórico
proviene del domicilio del usuario, porque no existe otra dirección histórica.
El CSV conserva todos los cruces courier/departamento.

Cinco cruces con mayor cantidad de envíos válidos:

| Courier | Departamento | Envíos | Días medios | Promesas conocidas | Retraso (%) |
| --- | --- | --- | --- | --- | --- |
| Chazki | Lima | 18061 | 1.27 | 18061 | 12.01 |
| Olva Courier | Lima | 13069 | 2.34 | 13069 | 36.88 |
| Urbano Express | Lima | 12579 | 2.33 | 12579 | 36.66 |
| 99minutos | Lima | 12241 | 1.27 | 12241 | 12.24 |
| Savar Express | Lima | 8917 | 2.33 | 8917 | 35.91 |

## Ventas, reseñas y reputación: diagnóstico

Se consideran vendedores con al menos 10 pedidos y calificación conocida.
Ventas altas = cuartil superior de sus ventas brutas: **S/42.644,91 o más**.
Mala reputación = estrellas promedio < 3,5. Retrasos relevantes = al menos
25% de los pedidos con promesa conocida llegaron tarde.

**14 vendedores cumplen los tres criterios**. Tabla completa:

| ID | Vendedor | Ventas brutas (S/) | Pedidos | Estrellas | Reseñas | Retraso (%) |
| --- | --- | --- | --- | --- | --- | --- |
| 58 | Grupo Rímac S.A.C. 57 | 2,021,369.35 | 660 | 2.99 | 262 | 94.84 |
| 386 | Negocios Titicaca S.A.C. | 1,206,974.27 | 3687 | 2.88 | 1476 | 95.06 |
| 697 | Negocios Moche S.A.C. | 426,429.31 | 145 | 2.66 | 62 | 96.53 |
| 29 | Negocios Cóndor S.A.C. | 319,195.22 | 373 | 2.79 | 143 | 97.24 |
| 175 | Grupo Misti S.A. 174 | 280,499.17 | 320 | 2.75 | 122 | 94.9 |
| 161 | Comercial Norte S.A.C. 160 | 256,926.04 | 170 | 2.97 | 72 | 94.48 |
| 559 | Negocios del Sur S.A.C. 558 | 183,569.71 | 484 | 2.74 | 196 | 94.48 |
| 114 | Distribuidora Moche S.A. 113 | 162,727.45 | 79 | 3.1 | 31 | 96.1 |
| 611 | Negocios Titicaca S.A. | 160,276.11 | 247 | 2.76 | 101 | 96.27 |
| 264 | Grupo Lima Center E.I.R.L. | 83,781.20 | 312 | 2.8 | 115 | 95.29 |
| 330 | Tienda Pacífico E.I.R.L. 329 | 80,116.59 | 178 | 3.0 | 71 | 95.32 |
| 189 | Distribuidora Sol S.A.C. | 65,162.08 | 177 | 3.11 | 74 | 94.12 |
| 530 | Corporación del Sur S.A.C. 529 | 61,116.73 | 25 | 2.91 | 11 | 100.0 |
| 14 | Inversiones Huascarán E.I.R.L. 13 | 55,338.67 | 79 | 2.29 | 35 | 89.74 |

[CSV completo del diagnóstico](resultados/diagnostico.csv).
La correlación de Pearson entre estrellas promedio y porcentaje tardío es
**−0,751**, calculada sobre **393 vendedores** elegibles con ambas medidas.
La tabla de vendedores incluye número de reseñas, ventas, unidades y pedidos;
el gráfico permite comparar ventas en escala logarítmica con estrellas.

La asociación es fuerte, pero no demuestra causalidad. Las reseñas identifican
producto y usuario, no pedido; un pedido puede reunir varios vendedores. Su
retraso se asocia a cada vendedor participante una sola vez por pedido, sin
atribuirle responsabilidad exclusiva. No se afirma que una reseña concreta
sea causada por una entrega específica.

## Reproducción y límites

En **Análisis**, seleccionar cualquiera de los nueve reportes y descargar el CSV
completo. Por CLI: `python -m backend.academic.analytics` desde `Pagina Web/`
con el entorno del backend y MySQL iniciado. El manual contiene el comando completo.
Se regeneran RFM, cohortes, co-compras, entregas, vendedores, diagnóstico,
ventas/distrito, stock crítico y árbol de categorías.

Los resultados corresponden al dataset sintético suministrado. El inventario
crítico es actual y cambia con las compras; los otros análisis del histórico
se mantienen al operar la aplicación. Los unitarios prueban denominadores,
deduplicación, meses sin exposición, fechas y ausencia de multiplicación de ventas.
