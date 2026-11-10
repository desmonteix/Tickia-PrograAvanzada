# Prueba end to end de Tickia — 10 de noviembre de 2026

## Resultado

Las 23 pruebas automatizadas ejecutadas sobre el código local pasaron. El flujo de autenticación publicado en `https://tickia.lat` completó sus 7 pasos en un navegador Edge aislado, con validación HTTPS activa y sin excepciones de JavaScript.

La corrección de autenticación del [PR #3](https://github.com/desmonteix/Tickia/pull/3) se integró en `master` mediante el commit `6a077775ea9cc90b6807304089bbadde80f3dc7c`. Antes del merge, las cinco comprobaciones de la [CI del PR](https://github.com/desmonteix/Tickia/actions/runs/42866551714) finalizaron correctamente: frontend, backend, contenedores, Chromium y Firefox.

## Ejecución local nueva

| Grupo | Resultado | Duración |
| --- | --- | --- |
| Recorridos completos con FastAPI y base temporal | 18/18 | 97,380 s |
| Bundle compilado y cookies reales HttpOnly/Lax | 3/3 | 9,093 s |
| dLocal Go con API real de la app y HTTP del proveedor simulado | 2/2 | 30,404 s |

Se comprobaron registro, ingreso, errores de credenciales y registro duplicado, publicación y búsqueda de entradas, rechazo de imágenes sin QR, compra y descarga, pagos rechazados o inciertos, cancelación del checkout, compra propia bloqueada, entrega de entradas nominadas, permisos de administración, móvil, confirmación de compra, vencimiento del plazo sin respuesta, evidencia de reclamos, devolución y consecuencias en ratings.

Los dos recorridos de dLocal verificaron el alta/validación del beneficiario, compra, confirmación, abono al vendedor y el caso de denuncia que congela fondos hasta que el administrador aprueba una devolución. El proveedor financiero y los resultados bancarios son simulados; no se hicieron cobros, transferencias ni devoluciones reales.

Comandos ejecutados desde `Pagina Web`:

```powershell
python -m unittest discover -s tests/e2e -p test_journeys.py -v
python -m unittest discover -s tests/e2e -p test_go_journeys.py -v
```

Desde `Pagina Web/frontend`:

```powershell
python tests/test_auth_browser.py
```

## Producción: ejecución medida

Realizada aproximadamente entre las 14:00:48 y 14:01:20, hora de Perú. Se crearon cuentas sintéticas de diagnóstico; las contraseñas solo existieron en memoria y no se guardaron en los resultados. No se utilizaron cuentas personales, SMS ni servicios de pago.

| Paso observado en el navegador | Resultado | Duración |
| --- | --- | --- |
| Abrir el sitio con HTTPS válido | PASS | 10,978 s |
| Crear cuenta e ingresar automáticamente | PASS | 4,694 s |
| Recargar conservando la sesión | PASS | 2,939 s |
| Salir, recargar y comprobar sesión anónima | PASS | 2,743 s |
| Ingresar con la misma cuenta existente | PASS | 2,472 s |
| Recargar conservando esa sesión | PASS | 2,900 s |
| Salir y comprobar nuevamente el cierre | PASS | 2,677 s |

La red confirmó registro 201 → login 200 → `/auth/me` 200. Tras cerrar sesión y recargar, `/auth/me` devolvió 401, como corresponde. Todas las llamadas de autenticación usaron `https://tickia.lat/api/`; el bundle observado fue `/assets/index-DVXUNOs6.js`. El formulario mostró el aviso de cuenta creada de la corrección.

Evidencia: [JSON completo](produccion-medicion/live-auth.json), [captura al terminar](produccion-medicion/live-auth.png) y [catálogo anónimo](produccion-medicion/catalogo-anonimo.png).

## Incidencias y límites

- El primer intento agotó una espera de 15 segundos al encadenar registro, login y consulta de sesión. El registro devolvió 201 y el login 200, pero no se llegó a observar la sesión antes de cerrar ese navegador. Se conserva el [resultado fallido](produccion/live-auth.json) y su captura. No permite atribuir la demora a una causa concreta.
- La prueba se corrigió para medir inicio/fin de cada solicitud y contemplar las tres llamadas consecutivas, cada una con el timeout de 20 segundos de la app. La ejecución medida completó el registro e ingreso en 4,694 segundos. No se modificaron los timeouts de la aplicación.
- La apertura inicial tardó entre 10,978 y 14,478 segundos en estas dos muestras. Es una observación desde este equipo/red, no una medición de percentiles ni una prueba de carga.
- La ejecución medida contó cuatro mensajes de consola HTTP sin excepciones JavaScript; ese primer contador no guardaba sus ubicaciones. Una revisión anónima posterior registró únicamente el 401 esperado de `/api/auth/me`, sin otros errores HTTP ni excepciones: [detalle](produccion-medicion/console-anonimo.json). No se afirma que el primer contador completo esté clasificado.
- La prueba de producción cubre autenticación. Las compras, reclamos, abonos y devoluciones se comprobaron en el entorno aislado con pasarela simulada. La ejecución real del circuito financiero requiere la aceptación de pruebas con el proveedor y su configuración.

Reproducción de producción desde `Pagina Web` (crea una cuenta sintética nueva por ejecución):

```powershell
python tools/check_live_auth.py --allow-test-registration --output ../Resultados/Despliegue/2026-11-10/E2E/nueva-ejecucion
```
