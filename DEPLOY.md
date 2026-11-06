# Despliegue de Tickia

La web queda preparada para validación en staging. **No habilitar cobros ni anunciar el lanzamiento comercial hasta cerrar los bloqueos del informe de auditoría.** No se ha desplegado este cambio ni se ha alterado la base real.

## Requisitos y estructura

- Python 3.13 y Node 22.16 o superior.
- Código backend: `Pagina Web/backend`; frontend: `Pagina Web/frontend`.
- CI activo: `.github/workflows/production-quality.yml`, en la raíz del repositorio.
- Informe técnico del backend: `Pagina Web/backend/AUDIT.md`.
- Plan y marca: `Pagina Web/docs/production-audit-plan.md` y `brand-implementation.md`.

## Configuración privada

Copiar `backend/.env.example` en `backend/.env` únicamente para desarrollo o inyectar sus valores desde el gestor de secretos del servidor. La imagen excluye `.env` y el entorno virtual.

Variables imprescindibles de producción:

- `ENVIRONMENT=production`.
- `DATABASE_URL`: PostgreSQL dedicado. SQLite se rechaza en producción.
- `SECRET_KEY`: aleatoria, al menos 32 caracteres.
- `QR_ENCRYPTION_KEY`: clave Fernet válida, con respaldo seguro. Cambiarla sin migrar archivos impide recuperar entradas anteriores.
- `SUPABASE_URL` y `SUPABASE_KEY`: acceso de servidor al bucket privado de QR cifrados.
- `FRONTEND_PROD_URL`: orígenes HTTPS exactos separados por comas.
- `COOKIE_SAMESITE=lax` con proxy de mismo origen.
- `PROXY_SHARED_SECRET`: el mismo valor privado en backend y proxy; 32-128 caracteres aleatorios URL-safe. Nunca usar un prefijo `VITE_` ni enviarlo al navegador. El backend rechaza arrancar en producción sin él.
- `PAYMENT_ENABLED=false` hasta completar las validaciones financieras.
- `SETTLEMENT_ENABLED=false` hasta certificar reembolsos y desembolsos con el proveedor contratado. Es independiente del interruptor de nuevos cobros.

La clave secreta Culqi pertenece exclusivamente al backend. `VITE_CULQI_PUBLIC_KEY` es la clave pública del checkout. Configurar claves de sandbox en staging y claves live solo después de aprobarlo. Nunca poner secretos en variables `VITE_*`.

## Base de datos y migración

1. Crear respaldo verificado y copia de staging de PostgreSQL.
2. Para una base nueva, desde `Pagina Web`: `python -m backend.init_db`.
3. Para una base existente, revisar y ejecutar primero `backend/migrations/production_readiness.sql` y después `backend/migrations/purchase_reviews.sql` en staging antes de producción. No es suficiente `create_all`: no migra tablas existentes.
4. Si hay duplicados, la migración debe fallar: resolverlos manualmente, sin borrar operaciones.
5. Revisar con los vendedores los anuncios antiguos. El código anterior inventaba fechas y hashes QR; no hay evidencia de que esas entradas sean utilizables.
6. El servidor verifica columnas e índices de integridad al arrancar; una migración pendiente debe impedir su inicio.

`purchase_reviews.sql` crea ratings y revisiones de compras sin inventar la finalización del concierto. Los casos históricos terminados conservan su visibilidad sin generar nuevos pagos ni puntos; los reembolsos pendientes requieren conciliación. Una compra entregada sin finalización conocida admite respuesta explícita, pero no vence automáticamente. Las nuevas publicaciones exigen inicio y finalización con zona horaria. El cierre se guarda al comprar y ocurre 24 horas después del final.

## Compras, reclamos y abonos

«Todo bien con mi entrada» se habilita al entregar el archivo. Confirma una decisión definitiva incluso antes del concierto. El silencio solo libera una compra efectivamente entregada al vencer el plazo. Un reclamo requiere una imagen privada y mantiene los fondos congelados hasta la decisión motivada de administración. Una renominación incumplida debe entrar en la cola de reembolso, sin simular devolución.

La orden financiera se persiste antes de invocar al proveedor. Los estados `PROCESSING` o `UNKNOWN` no se reenvían automáticamente. Los reembolsos inciertos pueden conciliarse consultando el cargo; una transferencia incierta requiere verificar la referencia real con el proveedor antes de cualquier recuperación. Las operaciones `BLOCKED` permanecen pendientes y son visibles en administración. No actualizar manualmente un caso a `SUCCEEDED` sin confirmación verificable ni repetir una transferencia para comprobar si funcionó.

La reputación se modifica después de confirmar el resultado financiero, una sola vez. Rating inicial 4, rango 0–5 y cambios de 0,25 según la especificación. El catálogo prioriza rating del vendedor, también durante la búsqueda.

El adaptador actual **no ejecuta abonos bancarios al vendedor**. La investigación está en `Resultados/Auditoria/OPCIONES_PAGOS_PERU.md`. Deben completarse contratación, identificación del vendedor, cuenta verificada, conciliación de cargos, integración y certificación. El comprador paga el precio publicado y todos los cargos se imputan al vendedor. No abrir ventas reales con este circuito incompleto.

## Opción Docker / Easypanel

### Recuperación del arranque en Easypanel

Si el backend informa `PROXY_SHARED_SECRET requiere 32-128 caracteres`, su entorno tiene la clave ausente o con formato inválido. Generar **una sola clave nueva para este propósito** en una terminal privada con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Copiar exactamente el mismo resultado en `PROXY_SHARED_SECRET` del backend y del frontend. No pegarlo en chats, repositorios ni variables `VITE_*`. No cambiar `SECRET_KEY` ni `QR_ENCRYPTION_KEY` para resolver este error.

En servicios App separados, configurar estas variables de ejecución:

| Servicio | Variable | Valor |
| --- | --- | --- |
| Backend | `PROXY_SHARED_SECRET` | La clave compartida generada |
| Backend | `FRONTEND_PROD_URL` | `https://tickia-frontend-tickia.7w1nku.easypanel.host` mientras ese sea el dominio usado |
| Backend | `COOKIE_SAMESITE` | `lax` |
| Backend | `PAYMENT_ENABLED` / `SETTLEMENT_ENABLED` | `false` / `false` |
| Frontend | `PROXY_SHARED_SECRET` | Exactamente la misma clave del backend |
| Frontend | `API_UPSTREAM` | `http://NOMBRE_INTERNO_REAL:8000`, sustituyendo el nombre por el asignado al backend; sin `/api` ni barra final |
| Frontend | `TRUSTED_INGRESS_CIDR` | IP/red concreta del proxy HTTPS, obtenida del despliegue; no inventarla ni usar toda internet |

Conservar las demás variables privadas del backend ya configuradas. El dominio del frontend debe apuntar al puerto interno **80**; el backend escucha por **HTTP en 8000**. El contexto de build frontend es `Pagina Web/frontend`; el argumento `VITE_API_URL` es `/api`.

El alias `backend` funciona en el Compose incluido, pero no identifica automáticamente un servicio App de Easypanel. Confirmar su nombre interno y que ambos servicios compartan una red que permita resolverlo. Desde la Shell del frontend, `wget -q -O - http://NOMBRE_INTERNO_REAL:8000/health` comprueba DNS, conectividad y salud sin mostrar secretos. Un fallo de esta comprobación requiere revisar nombre/red/estado del backend; no usar un DNS público para resolver servicios internos.

Después de guardar, seleccionar **Deploy** primero para el backend y después para el frontend; guardar variables por sí solo puede no actualizar el contenedor. Comprobar en el dominio frontend `/health`, `/ready`, `/api/tickets` y `/api/auth/me`: se espera 200, 200, 200 y 401 para una sesión anónima. Un error posterior de migración o clave de cifrado se debe resolver con su requisito específico, sin desactivar las validaciones.

La imagen frontend ahora exige un origen explícito y valida el secreto antes de generar nginx. Resuelve el backend mediante el DNS interno Docker durante las solicitudes: la portada puede arrancar mientras la API está ausente, pero `/ready` y `/api/` seguirán fallando hasta que el backend responda. Esto evita reinicios por DNS sin presentar la API como disponible.

Pruebas: `python -m unittest discover -s tests -p test_container_config.py -v` desde `Pagina Web`; con las imágenes `tickia-web` y `tickia-api` construidas, `python tools/test_container_startup.py` verifica el arranque real, DNS inicialmente ausente, recuperación, conservación de ruta/query/cookie y autenticación del proxy. El pipeline ejecuta ambas pruebas y también se activa con cambios en `master`.

Referencias: [variables y despliegues de Easypanel](https://easypanel.io/docs/services/app), [resolución de upstreams variables de nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass) y [DNS interno de Docker](https://docs.docker.com/engine/network/#dns-services).

`Pagina Web/compose.yml` define frontend con nginx y backend. El puerto 8080 se enlaza solo a localhost y debe ponerse detrás del proxy HTTPS del servidor. El frontend usa `/api`; nginx reenvía al backend conservando las cookies en el mismo origen. `API_UPSTREAM` configura el destino al arrancar el contenedor.

Exportar `PROXY_SHARED_SECRET` antes de invocar Compose para inyectarlo en ambos servicios. Configurar `TRUSTED_INGRESS_CIDR` con la IP o red exacta del proxy HTTPS que conecta a nginx; el valor por defecto solo confía en loopback. No usar `0.0.0.0/0` ni `::/0`. El proxy exterior debe sobrescribir `X-Forwarded-For`. nginx resuelve la IP desde ese origen autorizado y transmite su propia cabecera autenticada al backend. Comprobar en staging que dos clientes conservan límites independientes. Para destinos HTTPS de `API_UPSTREAM`, nginx habilita SNI y verifica el certificado.

En Easypanel, asociar el dominio HTTPS al frontend/nginx y conservar el backend en la red interna. Si se construyen como servicios separados, usar los contextos `Pagina Web/frontend` y `Pagina Web/backend`, configurar `API_UPSTREAM` con el nombre interno real del backend e inyectar las variables privadas desde el panel. El nombre `backend` del ejemplo Compose solo es válido si ese servicio se llama así en la red del despliegue. Configurar la IP/red concreta del proxy de Easypanel en `TRUSTED_INGRESS_CIDR`: el valor loopback de ejemplo no identifica por sí solo ese proxy. No exponer el puerto de la API como un segundo acceso público que evite nginx.

Para diagnosticar un 502 de un dominio backend existente cuando Uvicorn informa que escucha en `0.0.0.0:8000`, comprobar que ese dominio apunta al servicio correcto, con protocolo interno HTTP y puerto de destino 8000. El frontend/nginx de estos Dockerfiles escucha internamente en el puerto 80. Confirmar la configuración guardada en el despliegue activo; la mera presencia de `EXPOSE 8000` en el Dockerfile no prueba el destino que tiene configurado un dominio de Easypanel.

Desde la Shell del contenedor backend se puede comprobar el transporte local sin leer secretos ni modificar datos:

```sh
python -c "import http.client; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=5); c.request('GET','/health'); r=c.getresponse(); print(r.status,r.getheader('Content-Type'))"
```

La versión actual espera `200 application/json` en `/health`. Si responde localmente y el dominio devuelve 502, revisar destino, puerto, protocolo y red del proxy. Si no acepta conexiones locales, contrastar el servicio/replica, el estado actual y los logs con sus fechas. No atribuir automáticamente un 502 a la base de datos ni cambiar la aplicación sin ese contraste. [Dominios de Easypanel](https://easypanel.io/docs/services/app#domains).

Desde `Pagina Web`: `docker compose build`, aplicar la migración con el procedimiento anterior y `docker compose up -d`. La configuración conserva los cobros y liquidaciones deshabilitados, también si el archivo de entorno los habilitara. Para habilitarlos después de la aprobación operativa, cambiar explícitamente `PAYMENT_ENABLED` y `SETTLEMENT_ENABLED` en la configuración del servicio; no basta una clave pública.

El Dockerfile del frontend acepta `VITE_API_URL=/api` y `VITE_CULQI_PUBLIC_KEY` como argumentos de build. Si cambia la clave pública, volver a compilar. El backend no se expone directamente a internet en el Compose incluido.

## Opción Vercel + backend separado

En Vercel elegir como Root Directory `Pagina Web/frontend`, Node 22, build `npm run build` y salida `dist`. Variables:

- `VITE_API_URL=/api`.
- `VITE_CULQI_PUBLIC_KEY`: clave pública correspondiente al entorno.
- `BACKEND_ORIGIN`: origen HTTPS del backend, sin `/api` ni credenciales. Es variable del servidor, sin prefijo VITE.
- `PROXY_SHARED_SECRET`: idéntico al backend, solo en el entorno del servidor Vercel.

La función `api/index.mjs` reenvía las rutas `/api/*` por el mismo origen, conserva las cookies HttpOnly y los bytes de archivos. Rechaza configuración ausente, redirecciones y fallos de red. El frontend no debe apuntar directamente a un dominio distinto si las cookies se bloquean entre sitios. La configuración del proxy necesita verificarse en un preview real de Vercel; las pruebas locales no demuestran el enrutamiento de su infraestructura. Considerar el límite de cuerpo de las funciones de Vercel para las imágenes grandes; Docker conserva el límite completo de 5 MB de la aplicación.

El gateway solo confía en la IP sobrescrita por la plataforma cuando se ejecuta en Vercel (`VERCEL=1`), y autentica esa cabecera hacia el backend. No copiar ese modo de confianza a un servidor público genérico. Un CDN adicional delante de Vercel requiere validar cómo conserva la IP real; no habilitar límites colectivos involuntariamente.

Render usa `rootDir: Pagina Web`, instala `backend/requirements.txt` e inicia `backend.main:app`. Configurar los secretos en el panel y conectar el origen del backend a Vercel. `Procfile` también contiene el directorio de aplicación correcto para ejecución desde la raíz.

## Verificación antes de abrir

- `GET /health`: proceso vivo; `GET /ready`: base accesible y estado de pagos.
- Bucket de almacenamiento privado; cookies HttpOnly/Secure en HTTPS; orígenes y CSP comprobados a través del proxy real.
- Registro abierto, login, logout, publicación, venta, compra, renominación y descarga de un solo uso en staging.
- El comprador paga exactamente el precio publicado. Comisión y costos de pasarela a cargo del vendedor; conciliar el neto real antes de pagarle.
- Culqi sandbox: aprobado, rechazado, autenticación adicional 3DS, timeout y notificación duplicada. Un pago incierto requiere conciliación: nunca pedir repetir el cargo.
- Aprobar y verificar los procedimientos de reembolso, liberación del dinero, identidad y atención de incidencias. Estos no se sustituyen con un cambio de interfaz.
- Exigir el pipeline verde, incluidas las pruebas concurrentes PostgreSQL y las imágenes Docker. No considerar un test omitido como aprobado.
- Revisar alertas, registros, respaldo/restauración y capacidad antes de admitir usuarios.

## Comandos de calidad

Desde `Pagina Web/frontend`: `npm ci`, `npm run lint`, `npm test`, `npm run build`, `npm audit --audit-level=moderate`.

Desde `Pagina Web`: instalar `backend/requirements.txt` y `tests/requirements.txt`, ejecutar `python -m unittest discover -s backend/tests -v`, `python -m unittest discover -s tests/e2e -v`, `python -m bandit -r backend -x backend/venv,backend/tests -ll` y `python -m pip_audit -r backend/requirements.txt`. Instalar navegadores con `python -m playwright install chromium firefox`.

Para la evidencia del bundle compilado, ejecutar `python tools/audit_browser.py` después de `npm run build`. Produce capturas y métricas de laboratorio en `Pagina Web/test-results`. No equivale a Core Web Vitals de usuarios reales.

En Windows se puede usar `backend/venv/Scripts/python.exe` para backend. Los tests de navegador requieren un Python con Playwright; buscan el Python del backend solo para iniciar el fixture aislado. `TICKIA_LOAD_ENV=0` evita leer secretos locales en los fixtures.

## Reversión

Antes de publicar, conservar la imagen/artefacto anterior y el respaldo de base verificado. Si aumenta la tasa de errores, deshabilitar pagos y volver al artefacto anterior solo si es compatible con el esquema actualizado. No revertir operaciones financieras ni restaurar una base sobre cargos posteriores: primero conciliar con la pasarela y aplicar el procedimiento de recuperación.
