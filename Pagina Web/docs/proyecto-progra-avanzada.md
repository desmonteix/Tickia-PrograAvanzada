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

Los archivos `10_pagos.csv` y `15_favoritos.csv` aparecen en el README original
del dataset, pero no están entre los 13 archivos entregados en esa carpeta.
No se importan los archivos de otras carpetas ni se fabrican sus registros.
