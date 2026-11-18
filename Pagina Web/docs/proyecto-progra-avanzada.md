# Proyecto de Programación Avanzada

Entrega actual: MySQL 8.4, 15 tablas, 18 relaciones entre tablas y una
autorrelación de categorías. Conserva la interfaz Tickia y funciona sin Supabase.

Los 13 CSV iniciales se completaron con `10_pagos.csv` y `15_favoritos.csv`,
encontrados en `P4_marketplace/`. Los 15 suman 801.519 registros; se conservan
IDs, nulos, fechas y relaciones.

La entrada principal es `backend.academic.main:app`, iniciada por
`Proyecto_PrograAvanzada/iniciar.py`. Cuentas, productos, pedidos y comunidad
usan las mismas 15 tablas MySQL. Columnas adicionales permiten autenticación,
idempotencia, desglose monetario y distinguir histórico de actividad web.

Builder, Strategy, Decorator y State participan en cotización y compra.
`confirmar_pedido` confirma la compra y descuenta stock atómicamente. Pandas
consulta MySQL y ofrece nueve reportes con exportación completa.

La versión SQLite queda como respaldo explícito `--legacy-sqlite`.
La migración inicial lee sus cuentas y compras sin modificar el archivo.
Pagos y envíos siguen siendo simulados.

- [Manual](../../Proyecto_PrograAvanzada/COMO_EJECUTAR.md).
- [Matriz de cumplimiento](../../Proyecto_PrograAvanzada/entregables/MATRIZ_CUMPLIMIENTO.md).
- [Informe de análisis](../../Proyecto_PrograAvanzada/entregables/INFORME_ANALISIS.md).
- [Plan](../../tasks/plan.md).

Publicar solo en `desmonteix/Tickia-PrograAvanzada`, rama
`proyecto_progra_avanzada`, sin fusionar con las ramas principales originales.
