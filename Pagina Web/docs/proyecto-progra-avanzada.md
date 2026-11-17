# Tickia — Proyecto de Programación Avanzada

## Alcance acordado

Rama `proyecto_progra_avanzada`, basada en `origin/master` (`1dc6f86`) después
del pull solicitado el 17-11-2026. Conservar el código y la identidad visual de
Tickia y mostrar los productos del dataset como catálogo, sin Supabase.

## Criterios de aceptación

- Importar íntegramente los 13 CSV de `Proyecto_PrograAvanzada/`, con sus
  columnas, IDs, relaciones y valores nulos. No modificar los originales.
- Crear una BD SQLite reproducible y fija para el dataset. Validar integridad
  referencial y mantener la BD anterior si falla una nueva importación.
- Consultar productos, categorías, vendedores, variantes, stock, reseñas y
  preguntas reales desde la interfaz de Tickia, con búsqueda y paginación.
- Mantener cuentas y archivos de la aplicación en almacenamiento local,
  independiente del dataset. No cargar credenciales de Supabase del `.env`.
- No inventar fechas de evento, entradas QR ni pagos que no contiene el dataset.
- Documentar arranque y reconstrucción local; probar importador, API y navegador.

## Compra y venta dentro de la plataforma

Ampliación solicitada: comprar artículos y publicar productos desde Tickia.

- El catálogo y el inventario se copian una sola vez a tablas `local_*` en
  `tickia.sqlite3`. Las 13 tablas originales continúan fijas en `marketplace.sqlite3`.
- Una cuenta local puede publicar un producto con categoría, precio, descripción,
  stock, talla, color y foto PNG/JPEG opcional. La publicación aparece en el catálogo.
- Comprar requiere iniciar sesión, seleccionar una variante y una cantidad y
  confirmar el total. El servidor calcula el importe en céntimos y descuenta stock
  mediante una actualización condicional dentro de la misma transacción del pedido.
- Repetir una solicitud de compra devuelve el pedido anterior. No se permite
  comprar un artículo propio ni vender más unidades de las disponibles.
- Cada comprador consulta sus pedidos en **Mis compras** y cada vendedor sus
  publicaciones y ventas en **Vender**. Las listas tienen paginación.
- Las compras son de demostración: no se llama a pasarelas, no se cobra dinero y
  no se promete un envío real. Reiniciar la aplicación conserva pedidos y stock.
- Las pruebas de navegador usan una carpeta temporal con `TICKIA_LOCAL_DIR` para
  no crear publicaciones o compras de prueba en la BD del usuario.

Los archivos `10_pagos.csv` y `15_favoritos.csv` aparecen en el README original
del dataset, pero no están entre los 13 archivos entregados en esa carpeta.
No se importan los archivos de otras carpetas ni se fabrican sus registros.
