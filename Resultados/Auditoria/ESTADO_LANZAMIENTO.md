# Estado de lanzamiento de Tickia

Actualizado: 5 de noviembre de 2026, America/Lima. Destino confirmado por el usuario: **Docker / Easypanel**. URL revisada: `https://tickia-frontend-tickia.7w1nku.easypanel.host/`.

**Dictamen: no basta con afiliar una pasarela. La versión local tiene pruebas aprobadas, pero no está certificada para abrir operaciones con dinero real.**

## Qué está comprobado

- 118 pruebas locales aprobadas: 82 backend, 30 navegador Chromium y 6 gateway. Incluyen PostgreSQL real temporal, compra, entrega, las cuatro ramas postcompra, evidencia privada, reputación, migraciones y concurrencia.
- Lista de espera retirada; identidad visual aplicada desde los PDF Tickia.
- Compilación, TypeScript y lint aprobados; auditorías de dependencias sin vulnerabilidades conocidas y análisis estático sin hallazgos altos ni medios.
- Decisiones y órdenes financieras persistentes, sin presentar una transferencia simulada como un abono real.

Esas pruebas usan pasarela y almacenamiento remoto sustituidos por adaptadores de prueba. No demuestran un desembolso bancario ni la configuración del servidor del usuario.

## Bloqueos que deben cerrarse

| Bloqueo | Estado comprobado | Qué falta | Tipo de trabajo |
|---|---|---|---|
| Cobro, retención, abono y devolución | Culqi para cobros; el método de abono al vendedor rechaza explícitamente la operación. | Proveedor que acepte el modelo, integración de abonos y devoluciones, tarifas reales y pruebas externas, incluido 3DS. | Contratación, código y certificación |
| Cuenta de destino del vendedor | No existe todavía un flujo para registrar y verificar el beneficiario bancario con el proveedor. | Onboarding, titularidad y referencia verificada de la cuenta; usarla al abonar y conciliar. | Código e integración |
| Identidad del comprador de una entrada nominada | El registro no completa nombre/DNI/verificación. Las compras nominadas exigen esos datos y una verificación ya aprobada. | Un flujo operativo verificable de identidad y su interfaz; las identidades sintéticas de los tests no cubren este paso. | Código y operación |
| Entorno real Docker/Easypanel | Tras cambiar el destino a 8000, el backend responde. Sigue publicada la API antigua 1.0.0 y el frontend anterior. | Desplegar las imágenes actualizadas, aplicar migraciones con respaldo y probar dominio, cookies, proxy y archivos privados. | Infraestructura y validación |
| Operación y recuperación | Hay registros, auditoría de acciones, salud del proceso y cola administrativa. | Confirmar alertas, responsable de conciliaciones/reclamos, copias de seguridad y una restauración/reversión ensayada. | Configuración y operación |
| Verificaciones pendientes del pipeline | Las pruebas locales aprobadas son Chromium; Firefox y contenedores no están certificados. | Pipeline del código actualizado con imágenes Docker/nginx y Firefox aprobados. | Ejecución y correcciones si aparecen fallos |

## Bloqueos confirmados en la web publicada

La revisión de lectura del despliegue encontró cuatro problemas concretos:

1. **502 resuelto tras corregir el puerto:** el origen backend inicialmente respondió 502. Después de que el usuario cambió el puerto de destino a 8000, `/health` devolvió 200 JSON y `/api/auth/me` devolvió 401 JSON sin sesión. La nueva comprobación también identificó que el backend sigue en la versión anterior.
2. **Frontend anterior al código auditado:** el bundle publicado contiene `waitlist` y «Mis entradas», sin «Mis compras», «Todo bien con mi entrada» ni «Reportar un problema». La interfaz muestra «El marketplace infalible para tus entradas». Sus assets difieren de los compilados localmente. Los cambios auditados no están reflejados en esta versión pública.
3. **Rutas de API del frontend sin el proxy previsto:** `/api/payments/status`, `/api/purchases`, `/health` y `/ready` responden 200 `text/html`, sirviendo la aplicación en lugar de JSON. La nueva configuración debe enrutar esas rutas al backend interno. Esto no prueba una exposición de compras privadas: no se obtuvo información de usuarios.
4. **Inventario ficticio en la versión publicada:** el bundle contiene `uuid-mock-1`, `uuid-mock-2`, «Concierto Mock» y «Festival Mock». La captura muestra las tarjetas de respaldo con identificador «uuid» durante el fallo del backend. El código local auditado ya eliminó ese comportamiento y muestra un error recuperable cuando falla la API; esa corrección también necesita publicarse.

Evidencias: [HTTP del frontend](easypanel-http.json), [HTTP del backend](easypanel-backend.json), [versión publicada](easypanel-version.json), [inspección de navegador](easypanel-browser.json), [captura pública](easypanel-publicado.png). No se crearon cuentas ni compras, no se subieron archivos y no se efectuaron pagos.

### Contraste con los logs de arranque facilitados por el usuario

El proceso informó `Application startup complete` y `Uvicorn running on http://0.0.0.0:8000`. Eso demuestra un arranque correcto en el momento de esos logs; no identifica por sí solo el estado actual ni el destino configurado en el proxy. Una nueva comprobación pública siguió recibiendo 502 del backend: [revisión posterior](easypanel-after-startup-log.json).

El aviso `pyzbar deshabilitado temporalmente (falta DLL en Windows)` coincide exactamente con un mensaje fijo del código anterior, donde `PYZBAR_AVAILABLE` se fijaba en falso. No es una excepción que haya detenido Uvicorn ni demuestra que Docker esté ejecutando Windows. El código local auditado ya usa OpenCV y no contiene ese aviso. También el backend desplegado debe actualizarse.

Se indicó contrastar el dominio del servicio backend con el listener de Uvicorn: destino interno **HTTP, puerto 8000**. Después de que el usuario cambió el puerto a 8000, el dominio comenzó a responder correctamente. La documentación de Easypanel exige que el destino coincida con el puerto del proceso. [Documentación oficial](https://easypanel.io/docs/services/app#domains).

### Resultado después del cambio a puerto 8000

[Comprobación de lectura posterior](easypanel-after-port-change.json):

| Ruta del backend | Resultado |
|---|---|
| `/health` | 200 JSON, `status=ok` |
| `/api/auth/me` sin sesión | 401 JSON |
| `/api/tickets` | 200 JSON |
| `/ready` | 404 JSON |
| `/api/payments/status` | 404 JSON |
| `/api/purchases` | 404 JSON |
| `/openapi.json` | 200 JSON, `TickerTrader API 1.0.0` |

El esquema público aún incluye `/api/auth/waitlist/status` y no incluye las rutas postcompra nuevas. El problema de acceso al backend quedó resuelto; siguen pendientes las actualizaciones de código e infraestructura y los demás bloqueos de lanzamiento.

Se prepararon [paquetes de código para el entorno de pruebas](../Despliegue/LEEME.md), con contextos Docker separados, integridad ZIP y huellas verificadas, excluyendo archivos de entorno y credenciales. No se construyeron ni desplegaron esas imágenes desde este equipo.

La renominación dentro de la aplicación se prueba con el archivo nuevo que sube el vendedor. Todavía debe validarse el procedimiento real de transferencia con las tiqueteras admitidas; decodificar un QR no prueba por sí solo que permita el acceso al concierto.

## Comprobaciones nuevas de esta revisión

- Docker CLI está instalado, pero no hay un daemon accesible en este equipo. No se presenta la inspección de archivos como una construcción de contenedores aprobada.
- Firefox está instalado en la carpeta de navegadores del proyecto, pero falla al arrancar por un error gráfico SWGL. Esto es una limitación del entorno de pruebas, no evidencia de que la aplicación falle o funcione en Firefox.
- El código local configura `/api` en el mismo origen. La versión publicada aún usa el origen separado del backend; requiere actualizar ambos servicios y el proxy de nginx.
- Compose ahora fija explícitamente tanto `PAYMENT_ENABLED=false` como `SETTLEMENT_ENABLED=false`, evitando heredar una habilitación financiera accidental del archivo de entorno al preparar el despliegue.

## Orden de cierre

1. Actualizar ambos servicios al código auditado y validar las rutas de API. El 502 por el destino del backend ya quedó resuelto. Mantener los cobros deshabilitados.
2. Conseguir aprobación comercial de un proveedor para la retención y los abonos del modelo Tickia. Completar identidad y cuentas verificadas conforme a esa integración.
3. Construir y validar las imágenes; desplegar primero en pruebas, aplicar las migraciones y recorrer los flujos con credenciales de sandbox, sin cargos reales.
4. Verificar privacidad de archivos, sesiones, IP del cliente detrás del proxy, alertas, conciliación y recuperación de datos en ese entorno.
5. Abrir cobros solo cuando exista evidencia del circuito completo, incluido el abono neto al vendedor y el reembolso íntegro al comprador. La habilitación de una clave comercial por sí sola no satisface ese criterio.

No se ha desplegado esta revisión ni se ha modificado la base real. [Informe de auditoría](INFORME_PRODUCCION.md) · [Flujo postcompra](FLUJO_POSTCOMPRA.md) · [Opciones de pagos](OPCIONES_PAGOS_PERU.md) · [Despliegue y recuperación](../../DEPLOY.md).
