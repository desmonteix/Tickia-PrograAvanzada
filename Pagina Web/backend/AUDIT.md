# Auditoría del backend Tickia

Fecha: 4 de noviembre de 2026. Responsable: Bobby, revisión independiente solicitada por el usuario.

## Dictamen

Las correcciones y las pruebas locales están listas para revisión. El lanzamiento comercial sigue condicionado a las verificaciones externas descritas abajo. No se ha ejecutado un cobro real, un reembolso real, una transferencia a vendedores ni una migración sobre la base de datos del usuario.

Prueba final local: **52 pruebas aprobadas, cero omitidas**, incluidas las tres de concurrencia sobre PostgreSQL 17 real en un cluster temporal exclusivo y cuatro pruebas adicionales de identidad y límites detrás del proxy. Tiempo: 5.146 segundos. Actualización final: 5 de noviembre de 2026 (America/Lima).

## Hallazgos corregidos

Revisión independiente final de Bobby: se corrigió también la agrupación de usuarios bajo la IP del proxy. El limitador solo acepta una IP válida cuando la cabecera del gateway está autenticada con `PROXY_SHARED_SECRET`; solicitudes sin esa credencial conservan la IP de conexión. Dos clientes verificados tienen límites independientes y cabeceras públicas falsificadas no permiten reiniciar el contador. La configuración de ingress y del secreto está documentada en `DEPLOY.md`.

| Severidad inicial | Problema reproducido o confirmado | Corrección |
| --- | --- | --- |
| Crítica | El endpoint de cargo inventaba un identificador y marcaba la entrada pagada sin cobrar en Culqi. | Adaptador HTTPS real; pagos deshabilitados por defecto; respuesta confirmada por importe, moneda, metadata, captura y resultado. |
| Crítica | Cualquier imagen producía un QR aleatorio. Una imagen blanca fue aceptada; la misma imagen obtenía hashes distintos. | Decodificación real OpenCV y fallback Aruco; imagen sin QR rechazada; hash determinista y dominio exacto o subdominio legítimo. |
| Crítica | Una notificación sin secreto podía vender una entrada y no generaba transacción financiera. | Notificación tratada como dato no confiable; consulta autenticada del cargo en Culqi y conciliación contra un intento local existente. |
| Alta | Dos cargos podían pasar simultáneamente; la comprobación comparaba token contra identificador de cargo. | Intento persistido antes de contactar la pasarela, hash de token único e índice de liquidación único por entrada. |
| Alta | La descarga de un solo uso no tenía bloqueo y podía sobrevivir a un reembolso. | Orden de bloqueo entrada → transacción, relectura tras esperar, propiedad y estado financiero revalidados. |
| Alta | La renominación ejecutaba await sobre una función síncrona con un UploadFile donde esperaba bytes. | Lectura limitada, validación y almacenamiento cifrado reales, plazo y nuevo QR comprobados. |
| Alta | El bloqueo temporal se revisaba al iniciar sesión, pero una sesión ya emitida seguía operando. | Suspensión y banned_until comprobados en cada petición autenticada. |
| Alta | El job liberaba reservas después de aproximadamente 20 minutos; podía liberar una compra con cargo incierto. | Comparación con reserved_until actual; los intentos PROCESSING/UNKNOWN/SUCCEEDED bloquean la liberación automática. |
| Alta | El job anunciaba un reembolso sin solicitarlo a la pasarela. | Estado REFUND_PENDING y auditoría de revisión operativa; nunca se informa un reembolso inexistente. |
| Alta | La deduplicación del QR solo comprobaba una consulta sin restricción de base de datos. | Índice único parcial para hashes activos, además de rechazo HTTP 409 y limpieza de archivo huérfano. |
| Media | El comprador pagaba precio + 10%; los montos no cuadraban. | El comprador paga exactamente el precio publicado. Comisión de Tickia al vendedor; tarifa externa pendiente hasta verificación. |
| Media | La fecha del evento se inventaba al subir la entrada. | Fecha futura y zona horaria obligatorias; respuesta de fechas en UTC explícito. |
| Media | Imágenes demasiado grandes se leían completas antes de limitarse. | Lectura máxima de 5 MB y límite ASGI de 6 MB incluso sin Content-Length. |
| Media | Una contraseña UTF-8 larga podía provocar excepción bcrypt 5. | Validación de 72 bytes; credenciales inválidas devuelven errores controlados. |
| Media | Identificadores administrativos y paginación inválidos podían provocar errores o consultas excesivas. | UUID tipado, rangos de días y paginación limitada. |
| Media | La sesión utilizaba una clave JWT de desarrollo conocida si faltaba configuración. | Clave efímera aleatoria en desarrollo y configuración obligatoria al arrancar en producción. |
| Media | La cuenta nueva seguía sin acceso al marketplace. | Registro abierto; sin endpoint ni gates funcionales de lista de espera. Columnas antiguas conservadas para compatibilidad. |

## Cobertura ejecutada

- Registro abierto, duplicados, normalización de email, contraseñas Unicode y credenciales erróneas.
- Inicio y cierre de sesión con cookie HttpOnly; suspensión de una sesión existente y JWT con sujeto mal formado.
- Acceso administrativo, UUID incorrecto, días inválidos y paginación fuera de rango.
- Rechazo de mutaciones desde un origen ajeno; cabeceras de seguridad; salud y readiness.
- Publicación PNG con QR real; imagen inválida, imagen sin QR, duplicado y caída del almacenamiento.
- Precio inválido o con más de dos decimales; fecha pasada o sin zona; datos de contacto rechazados sin ban automático.
- Reserva propia, usuario anónimo, otra reserva y expiración.
- Identidad verificada obligatoria antes de reservar una entrada nominada.
- Pagos deshabilitados, rechazo, timeout, respuesta con importe incorrecto, repetición y reserva vencida.
- Importe del comprador exacto; estimado del vendedor y tarifa/número final sin inventar.
- Notificación falsificada, JSON inválido y notificación verificada idempotente.
- Renominación con QR nuevo y plazo vencido con reembolso pendiente.
- Descarga ajena, token usado, token expirado, revocación financiera y fallo de almacenamiento sin quemar el enlace.
- Contrato del adaptador Culqi: importe enviado, credenciales de entorno, timeout, rechazo, JSON inválido y respuesta de autenticación 3DS.
- Restricción única de QR comprobada al insertar directamente en la base de datos de pruebas.

Las pruebas utilizan FastAPI, SQLAlchemy, bcrypt, cifrado Fernet y decodificación QR reales. Las llamadas a almacenamiento y pasarela se sustituyen únicamente dentro de tests. TICKIA_LOAD_ENV=0 evita cargar credenciales locales.

## PostgreSQL: verificado con un cluster aislado

Los tres tests opcionales utilizan un esquema privado tickia_test_<uuid>, lo crean y eliminan de forma aislada:

1. Dos compradores simultáneos reservan la misma entrada: un 200 y un 409.
2. Dos peticiones de cargo simultáneas: una llamada al proveedor y una transacción confirmada.
3. Dos publicaciones simultáneas con el mismo QR: una inserción y un rechazo por índice.

Los tres casos aprobaron en PostgreSQL 17. El runner tests/run_postgres.py creó un cluster nuevo dentro de backend/test-results, eligió un puerto libre de loopback, inició procesos ocultos y detuvo el servidor en finally. Ningún servicio ni base de datos del usuario se utilizó. Evidencia local: test-results/postgres-tests.txt. Si falta TEST_POSTGRES_URL al ejecutar únicamente unittest, estos tres casos se omiten explícitamente. El build de contenedores y la matriz PostgreSQL 16 de CI siguen pendientes de ejecutarse en su entorno.

## Condiciones para habilitar producción

1. **Pagos reales y 3DS.** PAYMENT_ENABLED=false es el estado inicial seguro. Configurar credenciales correctas y validar cargos aprobados/rechazados, expiración y conciliación con Culqi en sandbox. La respuesta 200 que exige 3DS no se declara pagada; la autenticación adicional todavía necesita un flujo confirmado antes de habilitar ese medio.
2. **Desembolsos y reembolsos.** No hay integración contractual validada para pagar al vendedor ni reembolso automático confirmado. Los métodos correspondientes fallan de forma explícita. Es necesario un procedimiento operativo o una integración verificada antes de cobrar a compradores.
3. **Tarifas del vendedor.** amount_seller y estimated_seller_amount son estimados tras la comisión Tickia del 10%. provider_fee y seller_net_amount quedan null hasta verificar todos los costos de pasarela. Nunca se cobra ese costo adicional al comprador.
4. **Identidad y titularidad.** No hay un proveedor KYC ni verificación oficial con las ticketeras. Se bloquea comprar entradas nominadas sin identidad marcada como verificada. Leer un QR y reconocer su dominio no demuestra autenticidad, titularidad ni validez de acceso.
5. **Migración y datos antiguos.** Aplicar migrations/production_readiness.sql primero en staging con backup y revisión de duplicados. Revisar las entradas antiguas: antes se guardaban fechas inventadas y QR mock; no se deben asumir válidas.
6. **Concurrencia y CI.** Las tres verificaciones de concurrencia pasaron sobre PostgreSQL 17. Exigir también el resultado de la matriz PostgreSQL 16 en CI y staging antes del despliegue.
7. **Servicios y operación.** Verificar bucket privado, llaves, DNS/TLS, orígenes, cookies a través del proxy, métricas y alertas. Los intentos UNKNOWN requieren conciliación; no se debe invitar al comprador a repetir un cargo.
8. **Escala.** El limitador actual mantiene estado por proceso. Una réplica adicional requiere almacenamiento compartido para conservar límites globales.
9. **Contenedor y staging.** Dockerfile actualizado a Python 3.13 y usuario sin privilegios. La imagen no se construyó localmente porque el daemon Docker no estaba disponible. Exigir build de CI y smoke test del despliegue con sus credenciales.

La aplicación valida la configuración y los índices principales al iniciar en producción. /health comprueba el proceso; /ready comprueba acceso a base de datos y muestra si los pagos están habilitados.

## Reproducir

Desde la raíz del repositorio en PowerShell:

```powershell
& 'Pagina Web/backend/venv/Scripts/python.exe' -m unittest discover -s 'Pagina Web/backend/tests' -v
```

Para activar los checks de PostgreSQL, definir TEST_POSTGRES_URL apuntando a una base de pruebas dedicada y ejecutar el mismo comando. El rol necesita crear y eliminar su propio esquema.

Fixture HTTP para pruebas de navegador, desde Pagina Web:

```powershell
& backend/venv/Scripts/python.exe -m backend.tests.e2e_server
```

Escucha únicamente en 127.0.0.1:8001, usa SQLite temporal y almacenamiento en memoria. Es un servidor de pruebas y debe permanecer fuera de producción.

## Fuentes del protocolo financiero

- [API oficial Culqi: cargos y respuesta](https://apidocs.culqi.com/)
- [Creación de cargos](https://docs.culqi.com/es/documentacion/pagos-online/cargo-unico/cargos/)
- [Webhooks](https://docs.culqi.com/es/documentacion/pagos-online/webhooks/)
- [Denegaciones](https://docs.culqi.com/es/documentacion/pagos-online/denegaciones/)

La documentación pública no define el HMAC x-culqi-signature que asumía el código anterior. La verificación implementada consulta el cargo directamente a Culqi. Las comisiones de Culqi pueden calcularse de forma asíncrona; no se inventó una tarifa.

## Dependency audit and SAST evidence

Native pip-audit 2.10.1: 55 pinned runtime packages, zero known vulnerabilities. pip check: no broken requirements. PyPI release feed independently confirmed zero advisories. Before correction: 46 advisory records, representing 24 unique vulnerabilities across eight packages after alias consolidation.

| Package | Before | Patched | Unique advisories before |
| --- | --- | --- | --- |
| anyio | 4.14.0 | 4.14.2 | 3 |
| certifi | 2026.6.17 | 2026.10.23 | 1 |
| cryptography | 49.0.0 | 50.0.2 | 1 |
| dnspython | 2.8.0 | 2.9.2 | 1 |
| h2 | 4.3.0 | 4.4.1 | 1 |
| hpack | 4.1.0 | 4.2.0 | 1 |
| multidict | 6.7.1 | 6.9.1 | 1 |
| PyJWT | 2.13.0 | 2.15.1 | 15 |

Bandit 1.9.4: zero high and zero medium findings. One low B106 finding is the public OAuth token_type value bearer in routers/auth.py, not a secret. This was reviewed explicitly and is preserved in bandit-report.json instead of hiding the scanner result. No security checks were disabled.

The PyJWT advisory GHSA-gvp8-978c-rx2q covers versions through 2.13.0 and reuse of mutable options after an insecure decode. Tickia never used that insecure decode path; the updated decoder also supplies fresh options and requires exp, user_id, signature and expiration verification. Tests reject expired JWTs, absent expiration, invalid subjects and non-HS256 algorithms. PyJWT 2.15.1 has no advisories in the queried release feed.

Evidence: dependency-audit-before.json, dependency-audit.json, pip-audit-report.json, bandit-report.json. The full Python source set (28 files) parses successfully. Runtime requirements were normalized from UTF-16 to UTF-8 while applying patches.

Audit sources: https://docs.pypi.org/api/json/ and https://github.com/advisories/GHSA-gvp8-978c-rx2q.

For native local PostgreSQL tests: backend/venv/Scripts/python.exe backend/tests/run_postgres.py from Pagina Web. It requires PostgreSQL 17 binaries and permission to initialize the isolated cluster.
