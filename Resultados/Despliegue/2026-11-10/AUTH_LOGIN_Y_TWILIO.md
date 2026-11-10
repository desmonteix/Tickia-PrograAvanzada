# Corrección de registro y sesión de Tickia

## Causa confirmada

En el navegador desplegado el registro devuelve 201 y el login 200, pero las solicitudes van directamente a `tickia-backend-tickia.7w1nku.easypanel.host`. La comprobación posterior `/api/auth/me` devuelve 401: la cookie no mantiene la sesión en este flujo entre sitios con el navegador probado. El formulario continúa en modo registro y al repetirlo el correo ya existe, por lo que devuelve «No se pudo completar el registro. Verifica tus datos».

La prueba directa por `https://tickia.lat/api` sí completó registro 201 → login 200 → sesión 200 → logout 200 → sesión 401. La base de datos permite crear cuentas; no se confirmó ningún fallo de migración para este incidente.

## Corrección

- Los builds de producción utilizan `/api` en el origen de la web, aunque `VITE_API_URL` conserve un dominio antiguo. Desarrollo conserva su override local.
- El Dockerfile tiene `/api` como valor por defecto.
- Tras un registro confirmado, el formulario conserva el estado de cuenta creada y pasa a ingreso. Si falla login o `/me`, el siguiente intento solo inicia sesión; no vuelve a crear la cuenta.
- Se conserva la sesión mediante cookie HttpOnly, Secure en producción y SameSite=Lax. No hace falta relajar cookies ni guardar tokens en localStorage.

`VITE_*` se integra en el JavaScript durante la compilación. Cambiar solo las variables del contenedor ya construido no cambia ese JavaScript. [Documentación oficial Vite](https://vite.dev/guide/env-and-mode).

## Despliegue en Easypanel

1. Publicar la corrección en la rama que consume el frontend.
2. En frontend, conservar `VITE_API_URL=/api` y `API_UPSTREAM=http://tickia_backend-tickia:8000` cuando esa conexión interna esté verificada.
3. En backend, configurar `FRONTEND_PROD_URL=https://tickia.lat,https://www.tickia.lat` y `COOKIE_SAMESITE=lax`. El secreto del proxy debe coincidir en ambos servicios.
4. Reconstruir el frontend desde el commit corregido; usar Force Rebuild si mantiene un artefacto anterior. Un reinicio de un contenedor con un bundle viejo no sustituye la compilación.
5. En una sesión nueva, iniciar sesión con una cuenta existente. No volver a registrarla. En Network las rutas de login y `/me` deben estar bajo `https://tickia.lat/api/`, no bajo el dominio separado del backend.
6. Verificar sesión al recargar y ausencia de sesión al cerrar y recargar. Comprobar que un fallo transitorio de login después del registro permite reintentar el ingreso.

Este cambio no requiere migraciones de base de datos.

## Twilio

Las variables son reservas para una futura integración de verificación telefónica:

| Variable | Función prevista |
| --- | --- |
| `TWILIO_ACCOUNT_SID` | Identificador de la cuenta Twilio |
| `TWILIO_AUTH_TOKEN` | Secreto de autenticación de la cuenta |
| `TWILIO_VERIFY_SERVICE_SID` | Identificador del servicio Verify que enviaría y validaría códigos |

El código actual de Tickia no llama a Twilio. No envía SMS ni valida un OTP al registrarse; no hacen falta esas credenciales para login/signup y pueden quedar vacías. La plantilla se actualizó para que no parezcan obligatorias. `RESEND_API_KEY` también permanece reservada para una integración futura de correo. [Twilio Verify](https://www.twilio.com/docs/verify/api).

## Evidencia

- `AUTH_LIVE_DIAGNOSTIC.json`: flujo directo por el proxy funcionando.
- `AUTH_BROWSER_DIAGNOSTIC.json`: registro/login aceptados por el dominio separado, seguidos de sesión 401 en Edge.
- Pruebas Node: el cliente mantiene login y `/me` en `/api` aunque reciba una URL absoluta heredada.
- Prueba del bundle compilado con URL de backend obsoleta: registro, cookie real HttpOnly/Lax, recarga, logout, ingreso posterior y recuperación de fallos tras crear la cuenta.

Se crearon dos cuentas de diagnóstico en la aplicación durante la reproducción; sus correos sintéticos están identificados en los dos JSON locales. No se registraron contraseñas ni tokens en esos archivos. Las pruebas automáticas restantes usan exclusivamente el servidor de pruebas local.
