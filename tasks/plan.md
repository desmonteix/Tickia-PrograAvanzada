# Marketplace universitario — adecuación a la rúbrica

## Alcance y decisiones

Repositorio de destino: `desmonteix/Tickia-PrograAvanzada`, rama
`proyecto_progra_avanzada`. Se conserva la identidad de Tickia. Pagos y envíos son
simulados; no se integran servicios ni cobros externos. La rúbrica exige MySQL:
el modo académico principal dejará de usar SQLite para su operación.

| Módulo | Responsabilidad | Depende de |
| --- | --- | --- |
| data-mysql | MySQL, 17 tablas normalizadas desde 15 CSV, carga íntegra, migración local | — |
| commerce-patterns | Builder, Strategy, Decorator, State, carrito y confirmación transaccional | data-mysql |
| shipping-social | Pagos, envíos, reseñas, preguntas y favoritos | commerce-patterns |
| analytics-pandas | Consultas SQL y análisis reproducibles sobre MySQL | data-mysql |
| marketplace-ui | Compra multítem, seguimiento, comunidad y reportes | commerce-patterns, shipping-social, analytics-pandas |
| university-delivery | Pruebas, ERD, manual y matriz de cumplimiento | Todos |

## Criterios verificables

1. Las 17 tablas normalizadas del modelo existen en MySQL con sus PK/FK, datos originales,
   IDs y fechas; se importan también pagos y favoritos encontrados en
   `P4_marketplace/`. La jerarquía añade una autorrelación de categorías a las
   18 relaciones entre tablas del diagrama de referencia. Las dos dimensiones
   geográficas y la FK del destino amplían el esquema a 22 FK.
2. Una cuenta puede vender productos con variantes y comprar varios artículos
   con un cupón. Un procedimiento almacenado confirma el pedido y descuenta
   stock dentro de una sola transacción, sin sobreventa ni doble confirmación.
3. Los cuatro patrones se usan en el flujo: Builder arma el pedido, Strategy
   calcula envío por courier, Decorator acumula descuentos y State valida
   pendiente → pagado → enviado → entregado.
4. El pago queda registrado, se puede seguir un envío, dejar una reseña tras
   recibir el producto, preguntar/responder y guardar favoritos.
5. Se entregan consultas ejecutables de categorías recursivas, ventas por
   vendedor/distrito (JOIN de seis tablas), stock crítico y el procedimiento.
6. Pandas obtiene de MySQL RFM, cohortes, co-compras, tiempos de entrega por
   courier/departamento y relación entre estrellas, reseña y ventas. Se responde
   al caso de vendedores con ventas altas y mala reputación por retrasos sin
   atribuir causalidad que el dataset no permita comprobar.
7. Los datos y cuentas de la versión local previa se preservan con migración
   idempotente; SQLite queda como respaldo de la versión anterior.
8. Pruebas unitarias, integración real con MySQL y navegador verifican los
   recorridos. Los documentos muestran cómo ejecutar y sustentar el proyecto.

## Orden de trabajo y verificación

- MySQL aislado en Docker, esquema y carga; comprobar conteos y relaciones.
- Dominio y procedimiento; probar dinero, descuentos, estados y concurrencia.
- API y carrito; probar autenticación, propiedad e idempotencia.
- Comunidad y seguimiento; comprobar permisos y transiciones.
- Pandas y consultas; verificar resultados, denominadores y exportaciones.
- UI, pruebas completas y migración; activar el servicio académico en 5174.
- Revisar y guardar los cambios; publicar únicamente en el remoto universitario,
  según la autorización del usuario, sin merge con las ramas principales.

## Referencias técnicas primarias

- https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- https://dev.mysql.com/doc/refman/8.4/en/with.html
- https://pandas.pydata.org/docs/reference/api/pandas.read_sql_query.html
- https://pandas.pydata.org/docs/user_guide/groupby.html


## Ampliación de requisitos de base de datos

Normalización explícita de geografía e importes, 17 tablas base y 22 FK.
Se entregan tres vistas, un trigger de estado, 13 consultas SQL con CTE y
ventanas, Repository con clases y generación NumPy verificable de 10.000 hechos
en la base de pruebas. El panel expone 18 reportes. Se verifican instalación
limpia, migración sin pérdidas, integración MySQL, regresión y navegador.
La evidencia está en entregables/AUDITORIA_REQUISITOS.md y su auditoría JSON.
