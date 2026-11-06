# Auditoría de lanzamiento · Tickia

Trabajo realizado el 4–5 de noviembre de 2026, zona America/Lima. Auditoría, correcciones y pruebas con participación del agente **Bobby**; su revisión independiente final añadió los casos de reserva vencida e identidad del cliente detrás del proxy.

Actualización del 5 de noviembre: flujo postcompra ampliado según las respuestas del usuario, con revisión adicional de Bobby. [Implementación y límites](FLUJO_POSTCOMPRA.md) · [Investigación de proveedores para Perú](OPCIONES_PAGOS_PERU.md).

Revisión posterior de la URL facilitada por el usuario: el backend inicialmente respondía **502**. El usuario corrigió el destino a puerto 8000 y se verificó `/health` con 200 JSON. Sigue publicada la API antigua 1.0.0; el frontend también es anterior y sus rutas de API devuelven HTML. Actualizar el despliegue sigue siendo un bloqueo adicional a la integración financiera. [Estado concreto de lanzamiento y evidencias](ESTADO_LANZAMIENTO.md).

## Dictamen

**La versión corregida está preparada para revisión y validación en staging. El lanzamiento comercial con cobros sigue bloqueado por las verificaciones financieras y operativas de esta sección.** No se ha publicado, cobrado dinero, enviado mensajes ni aplicado migraciones a la base del usuario. Las 118 pruebas automatizadas usan servicios externos sustituidos; la revisión posterior de Easypanel solo efectuó lecturas públicas, sin modificar cuentas ni datos.

Antes de habilitar cobros:

1. Validar Culqi sandbox y la cuenta comercial real: aprobación, rechazo, autenticación adicional 3DS, timeout y conciliación de notificaciones. El widget actual usa Culqi Custom Checkout; el SDK real y sus desafíos requieren comprobación con credenciales autorizadas. El código no declara pagado un cargo incierto.
2. Contratar e integrar el proveedor de **abonos bancarios al vendedor** y certificar las devoluciones. Las reglas de confirmación, reclamos y reputación ya fueron definidas por el usuario e implementadas. La cola financiera es persistente, pero el adaptador de abonos sigue rechazando operaciones hasta completar la integración. El reembolso Culqi requiere certificación externa. Mantener `PAYMENT_ENABLED=false` y `SETTLEMENT_ENABLED=false` hasta resolverlo.
3. Completar la verificación de identidad y el procedimiento oficial de transferencia o renominación. Las compras nominadas requieren identidad verificada; las identidades de las pruebas son sintéticas. Leer un QR no demuestra validez ante una tiquetera.
4. Aplicar las migraciones primero en staging con respaldo y revisar entradas antiguas, que antes podían tener fechas inventadas y hashes simulados. Configurar bucket privado, secretos, DNS/TLS, ingress, cookies, observación y atención de incidencias; probarlos a través del dominio real.
5. Ejecutar el pipeline en el proveedor: incluye construcción de imágenes, validación nginx y Firefox. Docker no tenía daemon disponible aquí; Firefox no llegó a arrancar en este equipo por un fallo gráfico SWGL. No se cuentan como verificaciones aprobadas.

Las instrucciones concretas, configuración y reversión están en [DEPLOY.md](../../DEPLOY.md). No se sustituyeron decisiones de operación por garantías comerciales inventadas.

## Cambios aplicados

- **Lista de espera retirada:** pantalla eliminada, registro abierto y sin restricciones por invitación. Se preservan columnas antiguas de la base para compatibilidad; ya no gobiernan el acceso.
- **Marca de los dos PDF Tickia:** Ruta A recomendada, logotipo extraído del original, Sora/DM Sans/Space Grotesk alojadas localmente, navy/violeta/coral/lima y «Tu entrada, su próximo plan». Se eliminaron promesas como «infalible», «válida» y «QR dinámico» que no respaldaba el producto. [Detalle de marca](<../../Pagina Web/docs/brand-implementation.md>).
- **Comprador sin sobrecostos:** total igual al precio publicado. Comisión de plataforma del 10 % y costos externos a cargo del vendedor, conforme a la aclaración del usuario. El neto definitivo queda pendiente hasta conciliar las tarifas reales; no se inventa su importe.
- **Postcompra:** buzón «Mis compras», confirmación desde la entrega, cierre a finalización +24 h, evidencia privada obligatoria, decisión administrativa motivada, órdenes financieras y reputación una sola vez. Rating inicial 4, rango 0–5 y pasos de 0,25. Orden por rating del vendedor, también al buscar. Se conservaron compras históricas y se encaminaron las renominaciones incumplidas a reembolso verificable.
- **Contratos reparados:** registro con teléfono, publicación con fecha y tiquetera reales, y descarga autenticada de bytes mediante enlace de un solo uso. Se eliminaron catálogos y compras ficticias que aparecían cuando fallaba la API.
- **Pagos:** confirmación contra el proveedor, intentos persistidos antes de cobrar, protección contra repetición y notificaciones verificadas mediante consulta autenticada del cargo. Timeout o conflicto financiero bloquean el reintento automático.
- **QR y archivos:** decodificación real, hash determinista, cifrado, límites de tamaño, rechazo de imágenes sin QR, control de duplicados y permisos. Renominación con archivo nuevo y plazo validado.
- **Reservas:** exclusión concurrente, vencimiento real y descarte del checkout vencido. Cancelar y reabrir un checkout vigente no crea otra reserva.
- **Acceso:** suspensión comprobada en cada petición, controles de administración, validación de UUID, importes, fechas, paginación y errores recuperables.
- **Proxy:** identidad de cliente autenticada entre gateway y backend; cabeceras falsificadas no reinician los límites. nginx confía solo en el ingress configurado y verifica TLS del upstream HTTPS. El secreto compartido nunca pertenece a variables `VITE_*`.
- **Interfaz:** etiquetas de formularios, teclado, tabla desplazable accesible, temas, móvil, estados vacíos, recuperación tras errores y manejo de sesión vencida. Se corrigió la interpretación de fechas UTC y los saltos visibles al cargar fuentes y catálogo.
- **Entrega:** CI situado en la raíz correcta, versiones actualizadas, instalación limpia npm verificada, proxy de mismo origen para Vercel, Docker/Compose y guía de despliegue corregidos.

## Evidencia y cobertura

Los recuentos y resultados finales se encuentran en los archivos adjuntos a este informe. La matriz comprende:

**118 pruebas automatizadas aprobadas:** 82 de backend, 30 de navegador Chromium y 6 del gateway. Cero pruebas omitidas en esas ejecuciones finales. Las 20 combinaciones de accesibilidad general, las comprobaciones de formularios de reclamos/administración y las mediciones del bundle son comprobaciones dentro de la matriz; no se suman artificialmente al recuento.

| Área | Qué verifica | Evidencia |
|---|---|---|
| Backend y PostgreSQL | Registro, sesiones, validación, QR, pagos, notificaciones, renominación, descarga y concurrencia real | [Registro backend](backend-tests.txt), [detalle de Bobby](<../../Pagina Web/backend/AUDIT.md>) |
| Navegador Chromium | Registro, acceso, venta, búsqueda, compra, descarga, rechazo, cancelación, vencimiento, pérdida de red, permisos y fallo del SDK | [Registro de navegador](browser-tests.txt) |
| Gateway | Rutas, cookies, cuerpos, binarios, fallos y autenticación de IP | `npm test`, frontend/tests/proxy.test.mjs |
| Accesibilidad | Catálogo, acceso, venta, billetera y administración × móvil/escritorio × oscuro/claro: 20 combinaciones | axe, reglas WCAG A/AA evaluadas; sin infracciones detectadas |
| Código | TypeScript, compilación Vite, ESLint y revisión independiente | Comandos del runbook y pipeline |
| Dependencias | npm audit y pip-audit nativos | [npm](npm-audit.json), [Python](<../../Pagina Web/backend/pip-audit-report.json>) |
| Análisis estático | Bandit | [Resultado completo](<../../Pagina Web/backend/bandit-report.json>) |

Ocho pruebas usan PostgreSQL real en esquemas de un cluster temporal propio que se apaga al terminar. Cinco comprueban concurrencia: reserva, cargo, QR duplicado, confirmación contra reclamo y dos trabajadores de liquidación. Tres comprueban migraciones repetibles: compras históricas terminadas, devolución pendiente heredada y creación desde el esquema sin las nuevas tablas/columnas. No se equipararon las pruebas SQLite con evidencia de bloqueo PostgreSQL.

La ampliación detectó y corrigió fechas que desbordaban después de cobrar, respuestas bloqueadas en compras antiguas, pérdida de históricos en el buzón, renominaciones incumplidas fuera de la cola y errores tardíos que podían sobrescribir resultados financieros confirmados. La migración se corrigió también para tablas creadas por el ORM sin defaults de servidor. Un timeout de arranque en frío de Vite se resolvió esperando la preparación de JavaScript antes de las aserciones de interfaz; se conservan los límites de esas aserciones y no se omiten casos.

Las pruebas de navegador utilizan React, FastAPI, almacenamiento cifrado y decodificación QR reales en un entorno local aislado. Se sustituyen exclusivamente el almacenamiento remoto y la pasarela. Los casos de fallos de red y accesibilidad usan respuestas controladas. No se han probado todas las combinaciones matemáticamente posibles ni se certifica disponibilidad de servicios externos con estos resultados.

## Seguridad y dependencias

- Frontend: inicialmente 29 alertas, incluidas 16 altas; después de las correcciones, **cero vulnerabilidades conocidas** en la auditoría npm guardada.
- Python: inicialmente 24 vulnerabilidades únicas en ocho paquetes; después de actualizar los parches, **cero vulnerabilidades conocidas en 55 versiones fijadas**, comprobadas con pip-audit y el feed oficial PyPI.
- Bandit: **cero hallazgos altos y medios**. Un hallazgo bajo B106 corresponde al literal público OAuth `token_type='bearer'`; se revisó y se conserva en el resultado, sin presentarlo como un secreto.
- `pip check` sin incompatibilidades. Las pruebas muestran avisos de deprecación de TestClient/httpx y un aviso de clave corta en un caso que intenta deliberadamente usar un algoritmo JWT no autorizado; no son fallos de los flujos de producción.
- La búsqueda de patrones de claves privadas en fuentes no encontró coincidencias. Esto no equivale a una auditoría del historial Git ni de los secretos o la configuración de los servicios desplegados.

## Rendimiento y capturas

Medición de la primera etapa de auditoría, antes de ampliar el flujo postcompra, sobre el bundle compilado, API controlada y navegador local sin ralentización de CPU o red:

| Ancho | LCP | CLS | Desbordamiento horizontal | Errores JS / infracciones axe |
|---|---:|---:|---|---|
| 360 px | 132 ms | 0 | No | 0 / 0 |
| 768 px | 132 ms | 0 | No | 0 / 0 |
| 1440 px | 172 ms | 0 | No | 0 / 0 |

El primer control detectó CLS superior a 0,20 en móvil; se corrigió sin relajar el umbral. Estas mediciones son de laboratorio: no representan Core Web Vitals de usuarios reales ni una medición de INP en producción. [Datos completos](production-lab.json).

[Captura de escritorio](web-escritorio.png) · [Captura móvil](web-movil.png). El evento visible en la captura del bundle es un dato de prueba local, identificado como tal; no se añadió inventario ficticio al producto.

## Fuentes

- Los dos PDF Tickia de la raíz del proyecto: identidad y decisiones de marca.
- [Culqi Custom Checkout](https://docs.culqi.com/es/documentacion/checkout/checkout-custom): constructor y callback por instancia del checkout vigente.
- [API de cargos Culqi](https://apidocs.culqi.com/): confirmación de importe, moneda, captura y resultado; tarifas de conciliación.
- [Cabeceras de Vercel](https://vercel.com/docs/headers/request-headers): IP sobrescrita por el edge y límites al introducir otro proxy.
- [Funciones Node de Vercel](https://vercel.com/docs/functions/runtimes/node-js): gateway de servidor con Request/Response.
- [Feed JSON PyPI](https://docs.pypi.org/api/json/): comprobación independiente de versiones y avisos de seguridad.
