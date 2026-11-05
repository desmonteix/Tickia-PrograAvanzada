# Actualización de Tickia en Easypanel: entorno de pruebas

Paquetes del código local auditado, preparados el 5 de noviembre de 2026. **No están desplegados ni aprobados para operar con dinero real.** Para desplegar desde GitHub, seleccionar la rama y el commit que contienen esta actualización. Ejecutar «Deploy» sobre el origen Git anterior volvería a construir la versión anterior.

Los ZIP y sus huellas se entregaron como archivos locales en esta carpeta. El repositorio conserva el código fuente y esta guía; no necesita almacenar esos paquetes duplicados para construir las imágenes.

## Archivos

- `tickia-staging-backend.zip`: contexto Docker del backend, con las dos migraciones revisadas.
- `tickia-staging-frontend.zip`: contexto Docker del frontend, interfaz y activos de marca.
- `SHA256SUMS.txt` y `release.json`: huellas y datos de los paquetes. Cada ZIP contiene un `RELEASE-MANIFEST.json` con huellas de sus archivos.

Se comprobaron integridad ZIP y huellas de contenido. Los ZIP excluyen archivos `.env`, entorno virtual, bases locales, dependencias instaladas y fixtures de prueba. No incorporan las credenciales del servidor. La validación de los archivos no sustituye la construcción de las imágenes ni sus pruebas en Easypanel.

## Preparación antes de sustituir servicios

1. Conservar la versión o imagen actualmente desplegada y verificar un respaldo de PostgreSQL. Trabajar primero sobre un entorno de pruebas.
2. Revisar las variables privadas descritas en [DEPLOY.md](../../DEPLOY.md), especialmente PostgreSQL, cifrado QR, almacenamiento privado, origen HTTPS y secreto compartido entre proxy y backend. Conservar la clave de cifrado que protege los archivos existentes.
3. Mantener **`PAYMENT_ENABLED=false` y `SETTLEMENT_ENABLED=false`** en el backend. Este cambio no integra todavía los abonos bancarios al vendedor.
4. Aplicar primero `migrations/production_readiness.sql` y después `migrations/purchase_reviews.sql` a la copia de pruebas. No ejecutarlas a ciegas sobre la base real; revisar conflictos y conservar operaciones. El backend actualizado rechaza arrancar en producción si falta el esquema requerido.

## Construcción y conexión

En servicios App de Easypanel puede utilizarse Source → Upload, cargar el ZIP correspondiente y elegir el constructor Dockerfile, con `Dockerfile` en la raíz del contexto. La documentación de Easypanel indica que una carga requiere construir y desplegar para aplicarse. [Origen Upload y construcción](https://easypanel.io/docs/services/app).

- **Backend:** escucha internamente por HTTP en el puerto **8000**. Inyectar las variables privadas desde Easypanel. No incluirlas en el ZIP.
- **Frontend:** nginx escucha internamente por HTTP en el puerto **80**. Construir con `VITE_API_URL=/api`; configurar la clave pública del checkout solo cuando corresponda al entorno. `API_UPSTREAM` debe contener el origen interno real del backend, con puerto 8000 y sin el sufijo `/api`.
- **Ambos servicios:** mismo `PROXY_SHARED_SECRET`. En nginx configurar `TRUSTED_INGRESS_CIDR` con la IP/red concreta del proxy de Easypanel. Los nombres de red de un Compose no deben suponerse válidos para servicios App separados.
- Asociar el dominio HTTPS al frontend/nginx. Mantener el backend en la red interna para la arquitectura final. Guardar ajustes no demuestra que ya se hayan aplicado: comprobar el despliegue activo.

## Verificación después de desplegar en pruebas

- `/health`: JSON con estado `ok`; `/ready`: JSON y `payments_enabled=false`.
- `/api/payments/status`: JSON con `enabled=false`.
- `/api/auth/me` y `/api/purchases`, sin sesión: **401 JSON**.
- `/api/*` no debe devolver el HTML de React.
- La web debe mostrar la marca y «Mis compras» al iniciar sesión, sin lista de espera ni inventario ficticio al fallar la API.
- Verificar acceso, publicación, descarga privada, sesiones y proxy con el procedimiento del runbook; después completar la certificación financiera con sandbox y el proveedor seleccionado.

La identidad real, las cuentas bancarias verificadas, el proveedor de abonos, las alertas y la recuperación de datos siguen siendo bloqueos de lanzamiento. [Estado completo](../Auditoria/ESTADO_LANZAMIENTO.md).
