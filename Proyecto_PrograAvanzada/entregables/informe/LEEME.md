# Informe y entrega académica

* [Informe Word editable](Informe_Tickia.docx): primera hoja completamente vacía
  para la carátula; índice nativo actualizado desde la segunda hoja.
* [Copia PDF](Informe_Tickia.pdf): 96 páginas y 38 figuras de evidencia.
* [Redacción editable](Informe_Tickia.md): desarrollo, scripts y código incluidos.
* [Cuaderno ejecutado](Analisis_Tickia.ipynb) y [HTML](Analisis_Tickia.html):
  diecinueve celdas de código ejecutadas sin errores.
* [Estructura SQL consolidada](SQL_estructura_objetos.sql): tablas, índices,
  vistas, procedimiento y trigger. Las trece consultas están en
  [03_consultas.sql](../../sql/03_consultas.sql).
* [Herramientas de elaboración](../../informe_tools/README.md).

La entrega completa se genera como
`Proyecto_PrograAvanzada/entregables/Entrega_Tickia_PrograAvanzada.zip` y se
comparte por separado del repositorio, por su tamaño. Incluye Word/PDF, código
Python y frontend, quince CSV, scripts SQL, cuaderno, resultados CSV,
diagramas/capturas y el respaldo completo con **801.586 filas**.

El respaldo tiene **17 tablas, 22 FK, 3 vistas, 1 procedimiento y 1 trigger**.
Conserva los **111.016 pedidos originales y una compra ficticia de S/278,67**.
No incluye cuentas personales del desarrollador ni sus credenciales MySQL.
La restauración, el arranque desde una extracción nueva, el acceso y el pedido
fueron comprobados. La prueba de reinicio conserva la base ya cargada.

Los datos NumPy se verificaron en la base separada de pruebas; el generador y
su evidencia están en las fuentes. Los reportes históricos filtran la fuente
original, sin incluir la compra de demostración.

El `README_ENTREGA.md` del ZIP explica instalación, acceso y reproducción.
El lanzador de entrega utiliza MySQL 3308, API 8002 y web 5175, con un proyecto
Docker propio; la instalación habitual del repositorio continúa en 3307/8001/5174.
Pagos y despachos son simulaciones académicas.
