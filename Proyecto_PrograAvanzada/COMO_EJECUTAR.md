# Tickia con el dataset local

Esta versión vive en la rama `proyecto_progra_avanzada`. Usa el código y el diseño
de Tickia, con un catálogo de productos en lugar de entradas para eventos.
No necesitas una cuenta de Supabase, PostgreSQL ni credenciales de pagos.

## Iniciar

Desde la raíz del repositorio:

```powershell
python Proyecto_PrograAvanzada/iniciar.py
```

Abre **http://127.0.0.1:5174**. El script inicia la API en el puerto 8001 y el
frontend en el 5174. Pulsa **Ctrl+C** para cerrar ambos. Si un puerto está ocupado:

```powershell
python Proyecto_PrograAvanzada/iniciar.py --api-port 8002 --web-port 5175
```

Si faltan dependencias, instálalas una vez (Python 3.13 y Node.js 22.16 o posterior):

```powershell
python -m venv "Pagina Web/backend/venv"
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m pip install -r "Pagina Web/backend/requirements.txt"
cd "Pagina Web/frontend"
npm.cmd ci
cd ../..
```

## Qué incluye

- Los **13 CSV originales**, con **610.021 registros** en total.
- **9.337 productos**, 700 vendedores, categorías jerárquicas y stock por variante.
- Búsqueda sin distinguir tildes ni mayúsculas; filtros, orden y paginación.
- Fichas con variantes, reputación, reseñas y preguntas reales del dataset.
- Resumen del número de registros por tabla, al pie del catálogo.
- Registro e inicio de sesión originales de Tickia, sobre una BD local de cuentas.

El catálogo es de consulta: no inventa QRs o fechas de eventos para los productos,
y no realiza compras, ventas ni cobros de productos. Los datos históricos de
pedidos y envíos se conservan íntegros en la BD y se pueden consultar por la API.
Los flujos originales de entradas se conservan en el código para referencia.

Las cuentas de `02_usuarios.csv` son datos del histórico y **no** credenciales de
Tickia: el CSV no contiene contraseñas. Puedes crear tu propia cuenta local.

## Archivos locales

La primera ejecución crea `Proyecto_PrograAvanzada/.local/`:

| Archivo | Uso |
| --- | --- |
| `marketplace.sqlite3` | Copia fija de las 13 tablas, abierta en modo de solo lectura por la API |
| `tickia.sqlite3` | Cuentas, sesiones y tablas originales de la aplicación |
| `secrets.json` | Claves locales generadas, persistentes entre reinicios |
| `storage/` | Archivos cifrados de los flujos originales de Tickia |
| `backend.log`, `frontend.log` | Salida de los servicios |

Esta carpeta está excluida de Git. Los CSV originales no se modifican. La rama
usa por defecto `TICKIA_DATA_MODE=dataset` e ignora el `.env` del backend para no
conectarse accidentalmente a la BD original. Conserva el modo `remote` para las
pruebas y como referencia del comportamiento original.

## Reconstruir la BD del dataset

Detén la aplicación y ejecuta desde `Pagina Web/`:

```powershell
& "backend/venv/Scripts/python.exe" -m backend.dataset
```

La importación valida columnas y relaciones, registra SHA-256 y número de filas
por archivo, y reemplaza la BD solo cuando toda la carga termina correctamente.
No reimporta ni duplica registros al reiniciar normalmente.

El README original enumera también `10_pagos.csv` y `15_favoritos.csv`; estos
archivos **no se entregaron en esta carpeta** y no se fabrican ni se importan de
otras carpetas.

## API local

Documentación interactiva: **http://127.0.0.1:8001/docs**.

- `GET /api/runtime`: modo de datos activo.
- `GET /api/dataset/summary`: las 13 tablas, conteos y hashes originales.
- `GET /api/dataset/categories`: categorías y cantidad directa de productos.
- `GET /api/dataset/products?q=lampara&category=1&sort=price_asc&page=1&page_size=24`.
- `GET /api/dataset/products/1`: producto con variantes, últimas reseñas y preguntas.
- `GET /api/dataset/tables/pedidos?page=1&page_size=25`: consulta paginada de cualquiera
  de las 13 tablas. El explorador omite los correos de la tabla de usuarios.

## Verificar

Desde `Pagina Web/`:

```powershell
& "backend/venv/Scripts/python.exe" -m unittest discover -s backend/tests -v
cd frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

Las pruebas de integración que requieren PostgreSQL se omiten si no está
configurado `TEST_POSTGRES_URL`, igual que en el proyecto original.

Con la aplicación encendida, puedes probar el catálogo en Chromium (requiere
Playwright instalado) desde `Pagina Web/`:

```powershell
$env:TICKIA_DATASET_URL = "http://127.0.0.1:5174"
python -m unittest discover -s tests/e2e -p test_dataset_catalog.py -v
```
