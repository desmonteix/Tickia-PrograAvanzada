# Ejecutar el marketplace universitario

## Preparación

Python 3.13, Node.js 22.16 o posterior y Docker Desktop iniciado con contenedores Linux.
El repositorio es privado: cada integrante necesita acceso para clonarlo.

```powershell
git clone --branch proyecto_progra_avanzada https://github.com/desmonteix/Tickia-PrograAvanzada.git
cd Tickia-PrograAvanzada
python -m venv "Pagina Web/backend/venv"
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m pip install -r "Pagina Web/backend/requirements.txt"
npm.cmd ci --prefix "Pagina Web/frontend"
python Proyecto_PrograAvanzada/iniciar.py
```

| Servicio | Dirección |
| --- | --- |
| Aplicación | http://127.0.0.1:5174 |
| API y Swagger | http://127.0.0.1:8001/docs |
| Disponibilidad | http://127.0.0.1:8001/ready |
| MySQL | 127.0.0.1:3307, base `tickia_universidad` |

La primera ejecución descarga MySQL, crea 15 tablas e importa 801.519 filas.
El lanzador espera a ambos servicios antes de mostrar la URL. Ctrl+C cierra
API y frontend; MySQL conserva el volumen `tickia-universidad_mysql-data`.
No elimines ese volumen para reiniciar la aplicación.

Puertos alternativos:

```powershell
python Proyecto_PrograAvanzada/iniciar.py --api-port 8002 --web-port 5175
```

Ante `ERR_CONNECTION_REFUSED`, abre Docker Desktop, ejecuta el lanzador y usa
la dirección que muestra. Revisa `.local/backend.log`, `.local/frontend.log`
y la salida del lanzador si un servicio no inicia.

## Comprar y vender

1. Crea una cuenta en **Ingresar**. Los usuarios históricos del CSV no tienen
   contraseñas y no son credenciales de acceso.
2. En **Vender**, publica un título, descripción, precio, categoría, foto opcional
   y variantes con stock propio por talla/color.
3. Con otra cuenta, busca el producto y agrega variantes al carrito. Puedes
   mezclar productos de varios vendedores en un mismo pedido.
4. En **Carrito**, elige distrito, courier, pago simulado y cupón vigente.
   Tres unidades o más reciben además 3% por volumen.
5. Confirma: MySQL registra pedido, detalle, pago y envío y descuenta todas las
   unidades en una transacción. El servidor vuelve a calcular el precio.
6. En **Mis compras**, usa **Simular despacho** y **Confirmar recepción**.
   Después puedes reseñar el producto una vez. El vendedor ve **Mis ventas**.
7. En cada ficha puedes guardar favoritos, preguntar y responder como propietario.
8. **Análisis** ofrece nueve reportes y sus CSV completos.

Pagos y envíos son educativos: no se cobra dinero ni se contrata un courier.
El comprador también puede simular despacho para demostrar compras a vendedores
históricos que no tienen cuentas de acceso.

## Persistencia

| Ubicación | Contenido |
| --- | --- |
| Volumen Docker | Las 15 tablas operativas MySQL |
| `.local/mysql.env` | Contraseñas aleatorias y nombre de la base |
| `.local/mysql-manifest.json` | SHA-256 de los CSV y conteos verificados al iniciar |
| `.local/secrets.json` | Claves persistentes de sesión |
| `.local/product-images/` | Fotos publicadas |
| `.local/legacy-migrated-tickia_universidad.json` | Resultado de migrar la versión anterior |
| `.local/analisis/` | Reportes completos generados por CLI |

`.local/` está excluida de Git. No compartir sus claves ni archivos de cuentas.
Los CSV no se modifican. El manifiesto refleja conteos actuales; después de
publicar/comprar pueden superar los iniciales. Reiniciar no recarga stock.
Una base poblada con otros hashes se rechaza sin sobrescribirla.

Para otro MySQL 8.4, configura `TICKIA_ACADEMIC_MYSQL_URL` (URL SQLAlchemy
`mysql+pymysql`) en el entorno; se omite Docker. El usuario SQL debe poder crear
las tablas, índices y procedimiento y ejecutar este último.
`TICKIA_LOCAL_DIR` permite aislar claves, fotos y logs.

La primera activación migra cuentas, hashes, publicaciones, compras y stock de
`.local/tickia.sqlite3` en modo de solo lectura. La migración es idempotente y
preserva SQLite. El respaldo puede ejecutarse con `--legacy-sqlite`, en puertos
distintos. Después de migrar, no alternar ambos modos para registrar compras:
sus inventarios divergen.

## Análisis reproducible

Con MySQL iniciado, desde la raíz:

```powershell
Push-Location "Pagina Web"
& "backend/venv/Scripts/python.exe" -m backend.academic.analytics
Pop-Location
```

Genera nueve CSV y `resultados.json` en `.local/analisis/`. El histórico usa
`origen='dataset'`; las compras web no alteran RFM/cohortes/diagnóstico. Stock
crítico sí refleja inventario actual.

Los SQL están en `sql/01_esquema.sql`, `02_procedimientos.sql` y `03_consultas.sql`.
El importador envía el CREATE PROCEDURE como sentencia completa. En el cliente
`mysql`, usar `DELIMITER $$`, pegar la sentencia seguida de `$$` y restaurar
`DELIMITER ;` para ejecutarla manualmente.

## Pruebas

```powershell
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m unittest discover -s "Pagina Web/backend/tests" -v
npm.cmd run lint --prefix "Pagina Web/frontend"
npm.cmd test --prefix "Pagina Web/frontend"
npm.cmd run build --prefix "Pagina Web/frontend"
```

Las pruebas que requieren una BD externa se omiten en el comando anterior.
Para MySQL y Chromium en una base aislada:

```powershell
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m pip install -r "Pagina Web/tests/requirements.txt"
& ".\Pagina Web\backend\venv\Scripts\python.exe" -m playwright install chromium
& ".\Pagina Web\backend\venv\Scripts\python.exe" Proyecto_PrograAvanzada/verificar.py
```

El verificador crea únicamente `tickia_universidad_test`, ejecuta la integración
real y abre una instancia temporal en 8031/5201 para Chromium. Cierra sus procesos
al terminar y conserva capturas/logs en `.local/`. `--sin-navegador` ejecuta solo
MySQL. No elimina ni reinicia la base del usuario.
