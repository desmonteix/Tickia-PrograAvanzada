# Matriz de cumplimiento

Entrega: 18-11-2026 · rama `proyecto_progra_avanzada`.
Las rutas `backend/` y `frontend/` son relativas a `Pagina Web/`.

| Requisito | Implementación | Verificación |
| --- | --- | --- |
| Marketplace multivendedor con diseño Tickia | `App.tsx`, `ProductCatalog.tsx`, `MarketplaceSeller.tsx` | Compra de productos de dos vendedores en un carrito |
| MySQL, 17 tablas normalizadas y relaciones | `sql/01_esquema.sql`, `academic/bootstrap.py`, `compose.mysql.yml` | 801.519 filas originales, PK/FK reales |
| Usuarios, distritos y vendedores | `academic/auth.py`, `social.py`, `catalog.py` | Registro, publicación y destino de entrega |
| Variantes con talla, color y stock | `social.py`, `MarketplaceSeller.tsx`, `ProductDetail.tsx` | Stock independiente por combinación; hasta 20 variantes |
| Builder | `academic/patterns.py:OrderBuilder`, `commerce.py:quote_cart` | Pedido multítem, agrupación de cantidades y cupón |
| Strategy | `StandardShipping`, `ExpressShipping`, `EconomyShipping` | Courier y departamento cambian el costo |
| Decorator | `BasePrice`, `PercentageDiscount` | 3% por volumen seguido del porcentaje del cupón |
| State | `OrderContext` y estados concretos, `commerce.py` | Pendiente → pagado → enviado → entregado; saltos rechazados |
| Pagos y envíos | `commerce.py`, `MySQLOrders.tsx` | Registro de pago simulado, despacho y recepción con fechas |
| Reseñas, preguntas y favoritos | `social.py`, `ProductCommunity.tsx` | Reseña tras recibir; respuesta solo del propietario |
| Categorías con CTE recursiva | `sql/03_consultas.sql:categorias` | Árbol con nivel y ruta, también visible en Análisis |
| Ventas por vendedor y distrito, seis tablas | `sql/03_consultas.sql:ventas_distrito` | productos, variantes, pedido_detalle, pedidos, usuarios, distritos |
| Stock crítico | `sql/03_consultas.sql:stock` | Variantes actuales con 0–3 unidades |
| Procedimiento transaccional | `sql/02_procedimientos.sql:confirmar_pedido` | Rollback total, idempotencia y última unidad concurrente |
| RFM | `analysis_frames.py:rfm` | 45.000 clientes, recencia/frecuencia/monetario y segmentos |
| Cohortes | `analysis_frames.py:cohorts` | Retención por primera compra y clientes únicos |
| Co-compras | `analysis_frames.py:co_purchases` | Soporte, confianza y lift por pares |
| Entrega por courier/departamento | `analysis_frames.py:delivery_summary` | Días medios, promesas conocidas y porcentaje tardío |
| Estrellas, reseñas y ventas | `analysis_frames.py:vendor_summary` | Ventas, número de reseñas, estrellas y gráfico |
| Diagnóstico de ventas altas/reputación/retrasos | `analysis_frames.py:diagnose` | 14 vendedores; umbrales y limitaciones explícitos |
| Exportación reproducible | `academic/analytics.py`, `MarketplaceAnalytics.tsx` | 18 CSV completos, CLI y panel |
| Conservación de la versión anterior | `academic/migration.py` | SQLite de solo lectura y reinicio sin restaurar stock |

## Evidencia

- Catorce pruebas de integración/requisitos con MySQL real: esquema, compra/cupón/idempotencia,
  estados/permisos/comunidad, rollback, concurrencia, migración y consultas SQL.
- Trece pruebas puras: seis de patrones, cinco de Pandas y dos de generación.
- Regresión backend: 208 pruebas, 35 omitidas por servicios externos no configurados.
- Frontend: 28 pruebas, lint y compilación correctos.
- Chromium: publicación con foto y variantes; compra de dos vendedores y tres
  variantes; volumen y cupón; despacho, recepción, reseña, pregunta/respuesta,
  favoritos y análisis. Exportación RFM de 45.000 filas. Móvil y escritorio sin
  desbordamiento horizontal de la página, errores JavaScript ni llamadas externas.

Reproducir con el [manual](../COMO_EJECUTAR.md) y `verificar.py`.
Los logs y capturas de prueba se conservan en `.local/`, excluida de Git.

## Decisiones del modelo

El diagrama indica 18 relaciones entre tablas. La autorrelación
`categorias.id_padre → categorias.id_categoria` daba **19 FK** en el modelo inicial.
La normalización añade provincias, departamentos y la FK del destino del pedido:
el modelo actual tiene 17 tablas y 22 FK. Hay tres vistas y un trigger.
Los requisitos adicionales se detallan en [la auditoría](AUDITORIA_REQUISITOS.md).
Los cinco emails duplicados del histórico se conservan: la unicidad se exige
solo para cuentas operativas con contraseña. No se asignan credenciales a
identidades del dataset.
