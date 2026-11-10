# Configuración dLocal Go: Tickia

9 de noviembre de 2026. Implementados payin, beneficiarios/KYC, payout y devolución. Las pruebas usan un simulador aislado de Go: todavía falta certificar el circuito con la cuenta del operador. No hubo pagos reales ni despliegue en Easypanel.

## Cuenta y tarifas

Solicitar a **dLocal Go** payins y **Payouts v2, beneficiarios B2C, Perú/PEN** para reventa de entradas entre particulares bajo tu RUC. Obtener aprobación expresa del plazo entre cobro/concierto, bloqueo por denuncias y pagos a terceros. Completar KYC/2FA del operador. La integración no elude 2FA. Una cuenta habilitada para cobrar no demuestra permiso para este modelo ni para payouts.

Confirmar tarifa porcentual/fija de ambos servicios, impuestos, mínimo/límites, disponibilidad, refunds y contracargos. **El 3,53 % informado solo corresponde a payin: no confirma impuestos incluidos ni salida gratuita.** Esta versión admite payout porcentual sobre el importe enviado más cargo fijo y un tratamiento tributario común a ambos cargos. Si el contrato usa bandas, mínimo de comisión o impuestos distintos por servicio, adaptar el cálculo antes de activar.

## Credenciales y variables

Panel **Go → Integrations → API Integration**: obtener **API Key y Secret Key de sandbox**. Producción usa otras claves. No usar OAuth de Payouts v3 ni credenciales de Platforms.

En **Easypanel → backend → Environment** agregar:

```dotenv
PAYMENT_PROVIDER=dlocal_go
DLOCAL_GO_ENV=sandbox
DLOCAL_GO_API_KEY=REEMPLAZAR_CON_API_KEY_SANDBOX
DLOCAL_GO_SECRET_KEY=REEMPLAZAR_CON_SECRET_KEY_SANDBOX
DLOCAL_GO_PUBLIC_URL=https://tickia.lat
PAYMENT_ENABLED=false
SETTLEMENT_ENABLED=false

# Completar con contrato confirmado; los blancos bloquean ventas.
DLOCAL_GO_PAYIN_PERCENT=
DLOCAL_GO_PAYIN_FIXED_PEN=
DLOCAL_GO_PAYOUT_PERCENT=
DLOCAL_GO_PAYOUT_FIXED_PEN=
DLOCAL_GO_FEES_TAX_PERCENT=
DLOCAL_GO_MIN_PAYOUT_PEN=
DLOCAL_GO_PAYOUT_PURPOSE=
```

- Porcentajes en puntos: `3.53` significa 3,53 %, no `0.0353`.
- Fijos y mínimo en soles. Escribir `0` solo si ese concepto está confirmado como cero.
- `FEES_TAX_PERCENT=0` si las tarifas configuradas ya incluyen sus impuestos; `18` si ambas excluyen un impuesto de 18 %. No cambia la comisión Tickia de 10 % final, incluido su IGV.
- `PAYOUT_PURPOSE=ENTERTAINMENT` es un código documentado potencialmente aplicable: usar el que Go apruebe para la actividad. No usar `GOODS` ni `SERVICES`.
- Sin espacios alrededor de `=`. Conservar configuración existente de base, sesiones, cifrado y proxy.

**Frontend:** `VITE_API_URL=/api`. No necesita SDK ni clave pública Go. Nunca poner API Key/Secret Key en variables `VITE_*`, servicio frontend, argumentos de build o repositorio. `API_UPSTREAM` y `PROXY_SHARED_SECRET` siguen siendo variables del proxy servidor.

## Migración y despliegue

1. Respaldar base y verificar restauración. Aplicar primero en staging.
2. Aplicar migraciones pendientes de `Pagina Web/backend/migrations`, en orden: `production_readiness.sql`, `purchase_reviews.sql`, **`dlocal_go.sql`**. Son PostgreSQL y conservan historial Culqi. La nueva versión exige el esquema Go incluso con pagos apagados.
3. Reconstruir y desplegar backend y frontend. Backend HTTP interno 8000; frontend/nginx HTTP interno 80, expuesto mediante HTTPS Easypanel. Estos cambios locales no se publican automáticamente en GitHub/Easypanel.

Las tablas financieras nuevas tienen RLS y no conceden acceso a `PUBLIC`, `anon` o `authenticated` de Supabase. El backend debe conectarse con el propietario de esas tablas o un rol servidor con privilegios y autorización RLS adecuados; no usar la clave/rol público. Revisar también las políticas de las tablas anteriores según la guía de despliegue.

4. En la shell del backend, desde `/app`:

```sh
python -m backend.check_dlocal --check-api
```

Solo consulta `GET /v1/me`, sin claves/datos de cuenta en la salida. `api_authenticated=true` acredita autenticación, no permisos payout ni saldo. Usa las variables del contenedor, no carga `.env` por su cuenta.

5. Revisar `/health`, `/ready`, `/api/payments/status` y sesiones desde el origen frontend. En Compose los gates están fijados a `false` en `compose.yml`: cambiarlos explícitamente allí o mediante una sobreescritura; el `.env` no los sobreescribe.

El backend registra automáticamente el callback siguiente en órdenes y beneficiarios:

```text
https://tickia.lat/api/payments/webhooks/dlocal-go
```

Debe ser accesible para Go; conservar cuerpo original y cabecera `Authorization`. La firma usa el Secret Key de Go, sin otro secreto webhook. Volver del checkout en el navegador no confirma pago: la API consulta el estado auténtico en Go.

## Certificación sandbox

Con claves, habilitación y tarifario confirmados, poner **ambos** gates a `true` en staging. Tickia no cobra con depósitos deshabilitados.

1. Vendedor registra DNI/RUC, CCI PEN y acepta cargos. Completa identidad en enlace alojado por Go; solo `VERIFIED` permite vender. Los cambios de banco requieren revisión, no sustitución libre desde la app.
2. Comprar con datos de prueba oficiales: aprobado, rechazado, 3DS, cancelado, vencido y conexión interrumpida. Comprobar precio exacto y entrada en Mis compras; nominadas esperan archivo nuevo tras renominación.
3. Confirmar entrada, esperar disponibilidad, comparar importe/cargos/banco y acreditación en Go/Tickia.
4. Denunciar con evidencia: ningún payout mientras se investiga. Resolución válida: refund completo; no válida: payout. Comprobar rating una sola vez tras resultado financiero final.
5. Notificaciones repetidas, timeout y reinicio: sin duplicar dinero/rating. Un `UNKNOWN` no permite enviar otra operación manualmente.
6. Depósito rechazado: revisar datos/saldo; Administración → Depósitos y devoluciones permite autorizar otro intento con motivo. Tickia confirma el rechazo de nuevo y conserva historial. Los resultados inciertos no permiten ese reintento.

El mantenimiento corre aproximadamente cada 60 segundos: no escalar a cero si se espera procesamiento automático. Vigilar errores y antigüedad de pendientes. Las búsquedas de recuperación de pagos/refunds están acotadas a 200 registros; si no hay coincidencia inequívoca, conciliar con Go sin reenviar.

## Disponibilidad y protección del dinero

Los fondos quedan en el balance del operador en Go hasta crear una orden elegible. Tickia lleva el registro por compra; esto no acredita cuentas escrow segregadas. No retirar fondos comprometidos y mantener liquidez para refunds completos y cargos no devueltos por Go.

Esta versión aplica **7 días desde aprobación** antes del payout, también a medios alternativos. Go publica siete días para tarjetas y 48 horas hábiles para otros medios; se usa una espera conservadora común. Disponibilidad/revisiones bancarias pueden tardar más: no prometer abono inmediato al confirmar entrada. Si el contrato exige otro plazo/calendario, ajustar y probar antes de abrir ventas.

Ejemplo **sintético, no cotización**: entrada S/ 100; Tickia S/ 10 finales; payin final 3,53 %; payout fijo final S/ 1 → vendedor S/ 85,47. Se concilia el cargo real payin en PEN y se aplica el tarifario payout aceptado. Datos ausentes o cargos superiores a los aceptados bloquean el depósito. El comprador no asume cargos. El refund devuelve S/ 100: cargos externos requieren liquidez y política contractual del operador.

## Producción y reversión

Tras certificar sandbox y aprobar actividad/tarifas/operación: `DLOCAL_GO_ENV=live`, sustituir **ambas** claves por las de producción, revisar dominio final y desplegar. Comenzar con gates apagados; validar autenticación y alertas antes de habilitar. No reutilizar claves expuestas.

`PAYMENT_ENABLED=false` detiene nuevos checkouts. `SETTLEMENT_ENABLED=false` detiene envíos/mantenimiento financiero; los webhooks aún pueden confirmar operaciones enviadas. No borrar órdenes ni restaurar una base antigua sobre movimientos posteriores. Conservar claves/conciliación de la cuenta anterior hasta cerrar operaciones. La migración es aditiva: no eliminar tablas/columnas al volver a una imagen anterior.

## Fuentes oficiales

- [Autenticación](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/authentication).
- [Crear pago](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payments/create-a-payment), [consulta](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payments/retrieve-a-payment), [firma](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payments/notifications).
- [Beneficiarios/Payouts v2](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payouts-integration/payouts-v2), [consulta/notificaciones](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payouts-integration/notifications), [Perú](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payouts-integration/country-requirements/peru).
- [Refund](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payments/create-a-refund), [consulta refund](https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api/payments/retrieve-a-refund).
- [Disponibilidad](https://helpcenter.dlocalgo.com/es/articles/7846583-cuando-puedo-retirar-el-dinero-de-mis-ventas), [estados payout](https://helpcenter.dlocalgo.com/es/articles/15182096-que-significan-los-estados-de-mi-payout), [requisitos](https://helpcenter.dlocalgo.com/es/articles/15183460-que-son-y-como-usar-payouts-en-dlocal-go).
