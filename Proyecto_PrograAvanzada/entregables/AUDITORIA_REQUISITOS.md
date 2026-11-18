# Auditoría de requisitos del proyecto

Verificación: 18-11-2026. Repositorio independiente `Tickia-PrograAvanzada`,
rama `proyecto_progra_avanzada`. Resultado de la comprobación: **cumple**.

La revisión inicial detectó faltantes: normalización geográfica explícita,
importes redundantes, vistas, trigger, funciones de ventana y Repository con
clases. Se implementaron y comprobaron contra MySQL real; la entrega actual
incluye además análisis SQL avanzados.

| Requisito mínimo | Resultado comprobado | Evidencia |
| --- | --- | --- |
| 3FN y 12 tablas | 17 tablas base, todas con PK, 22 FK | [Dependencias funcionales y decisiones de 3FN](NORMALIZACION_3FN.md) |
| Índices en consultas frecuentes | 48 índices incluyendo PK/FK y siete índices específicos adicionales | `sql/05_indices.sql` y EXPLAIN en la auditoría JSON |
| Dos tablas N:M | pedido_detalle y favoritos, ambas con PK compuesta y dos FK | Esquema y pruebas MySQL |
| 10.000 hechos realistas | 111.016 pedidos originales y 247.482 líneas; otros 10.000 pedidos NumPy cargados y verificados en la BD aislada | [Generación](resultados/generacion_numpy.json), `academic/generation.py` |
| Cinco consultas JOIN de tres tablas o más | 10 consultas que cumplen dentro de 13 SQL entregados | [Catálogo de consultas](CONSULTAS_AVANZADAS.md) |
| Dos consultas con funciones de ventana | 5 consultas con RANK, DENSE_RANK, LAG o SUM OVER | `sql/03_consultas.sql` |
| Una subconsulta o CTE | 7 consultas con CTE, incluida una recursiva | `sql/03_consultas.sql` |
| Dos vistas | v_distritos, v_pedidos_importes, v_ventas_vendedor | `sql/04_vistas.sql` |
| Un procedimiento | confirmar_pedido: stock, pedido, detalle, pago y envío atómicos | `sql/02_procedimientos.sql` |
| Un trigger | tr_pedido_validar_estado, BEFORE UPDATE | `sql/06_trigger.sql`; prueba de SQL directo |
| Capa de datos con clases | CatalogRepository y OrderRepository usados en compras | `academic/repositories.py`, `commerce.py` |
| Tres patrones justificados | Builder, Strategy, Decorator, State y Repository | [Justificación e integración](PATRONES.md) |

[Auditoría completa de los objetos reales](resultados/auditoria_requisitos.json).
El archivo identifica la base principal y distingue la evidencia de generación
obtenida en `tickia_universidad_test`. No contiene contraseñas ni tokens.

## Datos y procedencia

Se conservan los 15 CSV suministrados, con 801.519 filas fuente. No se les
atribuye un origen abierto ni una herramienta de generación que no estaba
documentada. Para acreditar el requisito de generación reproducible se añadió
NumPy, semilla 20261118 y versión 2.5.0, con una carga real de 10.000 pedidos,
sus detalles, pagos y envíos en las mismas tablas del modelo dentro de la base
separada de pruebas.

El generador usa clientes recurrentes, popularidad desigual de productos,
carritos multítem, cantidades y tiempos de entrega variables. Respeta precios,
FK y totales; la segunda ejecución es idempotente. El histórico original y
su stock no se sustituyen. La aplicación principal no añade datos de prueba
al arrancar. Las filas NumPy se distinguen por `origen='numpy'`.
`loaded=false` en una repetición significa que esa carga ya existía; la
auditoría consulta su conteo real y no lo interpreta como una carga fallida.

## Evidencia de ejecución

- 27 pruebas académicas correctas: 13 puras y 14 contra MySQL real.
- Regresión backend: 208 pruebas registradas; 35 omitidas en ese comando por
  no configurar PostgreSQL y MySQL de pruebas. Las 14 de MySQL se ejecutaron
  por separado con resultado correcto dentro del verificador académico.
- Frontend: compilación y lint correctos; las 28 pruebas existentes también se
  verifican con `npm.cmd test`.
- Chromium: publicación con variantes y foto, carrito de dos vendedores,
  descuentos, compra, despacho, recepción, reseña, pregunta/respuesta, favoritos,
  reportes y exportación de 45.000 clientes RFM. Móvil y escritorio.
- Instalación limpia: base inicialmente vacía, 17 tablas y 111.016 pedidos
  importados desde los 15 CSV.
- Migración principal: comparación de huellas de las 15 proyecciones originales,
  cuentas, sesiones y SQLite anterior; todas se conservaron. Se guardó un
  respaldo local antes del cambio. [Resultado](resultados/integridad_migracion.json).

La auditoría estructural no sustituye el análisis semántico de 3FN ni prueba
por sí sola el comportamiento del trigger: estos puntos tienen su justificación
y sus pruebas directas respectivas.

## Ampliación sobre el mínimo

El panel contiene 18 reportes. Además de la rúbrica inicial, incorpora ranking
y acumulados, comparación mensual, inactividad adaptada a la frecuencia del
cliente, concentración de ventas por categoría, riesgo de courier con intervalo
de Wilson y afinidad de productos mediante autouniones de canastas.

[Resumen y muestras reales de los análisis avanzados](resultados/analisis_avanzados.json).

| Reporte SQL adicional | Filas resultantes |
| --- | --- |
| ranking_vendedores | 676 |
| ventas_mensuales | 8130 |
| resenas_producto | 8031 |
| favoritos_categoria | 2506 |
| entregas_departamento | 142 |
| clientes_inactivos | 4023 |
| participacion_categorias | 75 |
| riesgo_courier | 128 |
| afinidad_sql | 100 |


Los análisis conservan sus denominadores, criterios y límites interpretativos.
No se confunden ventas con utilidades ni correlaciones con causas de retraso.

## Repetir la comprobación

Desde la raíz, con Docker y las dependencias instaladas:

```powershell
& ".\Pagina Web\backend\venv\Scripts\python.exe" Proyecto_PrograAvanzada/verificar.py
Push-Location "Pagina Web"
& "backend/venv/Scripts/python.exe" -m backend.academic.audit --incluir-pruebas
& "backend/venv/Scripts/python.exe" -m backend.academic.analytics
Pop-Location
```

El verificador usa la base aislada; la auditoría de la aplicación es de solo
lectura. Detalles de configuración en [el manual](../COMO_EJECUTAR.md).
