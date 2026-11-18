# Proyecto de Programación Avanzada

Entrega actual: MySQL 8.4, 17 tablas en 3FN, 22 FK, tres vistas y un trigger. Conserva la interfaz Tickia y funciona sin Supabase.

Los 13 CSV iniciales se completaron con `10_pagos.csv` y `15_favoritos.csv`,
encontrados en `P4_marketplace/`. Los 15 suman 801.519 registros; se conservan
IDs, nulos, fechas y relaciones.

La entrada principal es `backend.academic.main:app`, iniciada por
`Proyecto_PrograAvanzada/iniciar.py`. Cuentas, productos, pedidos y comunidad
usan las mismas 17 tablas MySQL. Columnas adicionales permiten autenticación,
idempotencia y distinguir histórico de actividad web; las vistas reconstruyen
los importes y la geografía sin duplicarlos en tablas base.

Cuatro repositorios (CatalogRepository, OrderRepository, ProductRepository y
AnalyticsRepository) encapsulan el SQL de catálogo, compras y análisis.
Se entregan 13 consultas SQL, con ventanas, CTE y análisis de afinidad,
inactividad, concentración de ventas y riesgo de retraso. La generación NumPy
reproducible carga 10.000 pedidos en la base aislada de pruebas.

Builder, Strategy, Decorator y State participan en cotización y compra.
`confirmar_pedido` confirma la compra y descuenta stock atómicamente. Pandas
consulta MySQL y ofrece 18 reportes con exportación completa.

La versión SQLite queda como respaldo explícito `--legacy-sqlite`.
La migración inicial lee sus cuentas y compras sin modificar el archivo.
Pagos y envíos siguen siendo simulados.

- [Manual](../../Proyecto_PrograAvanzada/COMO_EJECUTAR.md).
- [Matriz de cumplimiento](../../Proyecto_PrograAvanzada/entregables/MATRIZ_CUMPLIMIENTO.md).
- [Informe de análisis](../../Proyecto_PrograAvanzada/entregables/INFORME_ANALISIS.md).
- [Plan](../../tasks/plan.md).

Publicar solo en `desmonteix/Tickia-PrograAvanzada`, rama
`proyecto_progra_avanzada`, sin fusionar con las ramas principales originales.
