# Compra, confirmación, reclamos y liquidación

Especificación del flujo solicitado y precisado por el usuario el 5 de noviembre de 2026. La implementación y la validación local se documentan en `Resultados/Auditoria/FLUJO_POSTCOMPRA.md`. La ejecución bancaria real sigue pendiente de proveedor.

## Situación actual comprobada

El pago confirmado crea una compra en «Mis compras». Una entrada nominada permanece pendiente hasta que el vendedor carga el archivo renominado. Se implementaron confirmación, reclamos con evidencia privada, resolución administrativa, vencimiento y órdenes financieras persistentes. El adaptador de desembolsos rechaza la operación explícitamente mientras no se contrate e integre un proveedor; el reembolso Culqi requiere habilitación independiente, credenciales y certificación en sandbox. Los tests usan proveedores sintéticos, sin mover dinero.

## Reglas confirmadas

1. El comprador paga exactamente el precio publicado, sin sobrecostos. Comisión y cargos corresponden al vendedor.
2. Después de comprar, la entrada aparece en un buzón «Mis compras». Si falta la renominación, se muestra ese estado y se entrega el archivo al completarse.
3. Se ofrece «Todo bien con mi entrada» o «Reportar un problema». El plazo cierra **24 horas después del final del concierto**. La fecha de inicio actual no debe usarse como si fuera la de finalización.
4. Un reclamo presentado a tiempo requiere evidencia y congela la liquidación hasta que administración lo resuelva. El vencimiento del plazo no cierra un reclamo que ya está abierto.
5. La administración examina la evidencia, registra su decisión y justificación y determina si es concluyente. No hay aprobación automática de evidencia.

| Caso | Destino del dinero | Rating comprador | Rating vendedor | Advertencia vendedor |
|---|---|---|---|---|
| Comprador confirma que todo está bien | Vendedor, descontando comisión y cargos | Sube | Sube | No |
| Comprador no responde hasta el cierre | Vendedor, descontando comisión y cargos | No cambia | Sube | No |
| Reclamo aceptado: evidencia concluyente | Reembolso al comprador | Sube | No cambia | Sí |
| Reclamo rechazado: evidencia no concluyente | Vendedor, descontando comisión y cargos | Baja | Sube | No |

## Decisiones confirmadas en la respuesta del usuario

- «Todo bien» se habilita **al recibir la entrada**, incluso antes del evento.
- Rating entre **0 y 5**, inicial **4**, cambios de **+0,25 / −0,25**, acotados a ese rango.
- El catálogo ordena primero por rating del vendedor, descendente. Las promociones no pueden adelantar a un vendedor con rating superior.
- El destino es **abono automático a la cuenta del vendedor**, no un saldo ficticio dentro de Tickia. La ejecución requiere un proveedor de desembolsos y una cuenta verificada; el adaptador actual no dispone de ellos. La aplicación debe conservar la orden pendiente sin marcarla pagada.

La confirmación es una decisión definitiva: se advertirá que libera el dinero y cierra el reclamo ordinario. Un resultado financiero no confirmado no modifica la reputación.

## Integración financiera pendiente

El usuario aún no eligió proveedor y solicitó investigar las opciones. La comparación se encuentra en `Resultados/Auditoria/OPCIONES_PAGOS_PERU.md`. No se presupone elegibilidad comercial ni autorización para retener fondos por tener acceso a una API de cobros.

La confirmación autoriza la orden de abono y cierra el reclamo ordinario. La interfaz lo advierte explícitamente. No se promete congelar dinero después de desembolsarlo.

## Componentes y orden de implementación

| Componente | Responsabilidad | Dependencias |
|---|---|---|
| Calendario de revisión | Inicio habilitado y finalización del concierto, cierre a +24 h, fechas UTC | Decisión del momento de habilitación |
| Buzón de compras | Entrega, estado del dinero, plazo, confirmación y reclamo | Calendario y contratos de compra |
| Reclamos privados | Texto, evidencia obligatoria, fecha de presentación y bloqueo | Compra pagada y permisos de propietario |
| Administración | Cola, acceso autorizado a archivos, decisión y motivo | Reclamos |
| Liquidación | Orden persistente, ejecución y conciliación de pago/reembolso | Decisiones y proveedor o saldo elegido |
| Reputación | Cambios de puntuación y advertencias exactamente una vez | Resultado financiero confirmado |

Orden: calendario y estados → confirmación/reclamos → revisión administrativa → liquidación/reputación → UI y pruebas E2E.

## Condiciones técnicas de aceptación

- Añadir una hora de finalización explícita; no inventar una duración. Para compras antiguas sin ese dato, bloquear el cierre automático, conservando la posibilidad de confirmar o reclamar desde la entrega. Cambiar el calendario de una compra no debe acortar unilateralmente el derecho a reclamar.
- Guardar el resultado de la revisión separado del estado del cargo. Una compra pagada cuyo dinero está retenido sigue siendo una compra pagada.
- Bloquear transaccionalmente confirmación, presentación de reclamo y vencimiento para impedir dos decisiones concurrentes sobre el mismo dinero.
- La orden de pago/reembolso será única por compra y persistirá antes de contactar a un proveedor. Un timeout se considera resultado incierto: se concilia antes de reintentar.
- No mostrar «pagado» o «reembolsado» ni modificar ratings por una transferencia que no se confirmó. Si el proveedor está deshabilitado, conservar el estado pendiente y explicarlo.
- Aplicar cada cambio de rating y advertencia una sola vez, incluso si se repite una petición, una notificación o el job.
- Un reclamo abierto bloquea también el job automático después de las 24 horas. Nunca pagar simultáneamente al vendedor y al comprador.
- No liberar automáticamente una entrada que sigue sin entregarse. La falta de archivo o de renominación requiere intervención; el silencio del comprador no demuestra entrega.
- Evidencia privada y acotada en tamaño y formato; acceso solo del comprador correspondiente y administradores. No exponer documentos o URLs públicas al resto de usuarios.
- Administradores deben registrar motivo y autor de la decisión. Las resoluciones contradictorias o repetidas se rechazan.
- La UI distinguirá «dinero retenido», «reclamo en investigación», «pago pendiente», «pago confirmado», «reembolso pendiente» y «reembolso confirmado».

## Pruebas necesarias

Backend: las cuatro filas de la tabla; apertura y cierre exactos de plazo; transacciones ajenas; falta de evidencia; formatos y tamaño; confirmación/reclamo simultáneos; reclamo contra job de vencimiento; decisiones administrativas repetidas y contradictorias; fallos y timeout financieros; repetición de eventos sin duplicar ratings; entrada pendiente de entrega; datos antiguos sin finalización.

PostgreSQL real: dos resoluciones concurrentes y carrera entre reclamo y liquidación automática.

Navegador: compra → buzón → QR → confirmación; silencio y cierre; reclamo con evidencia → panel administrador → resolución aceptada/rechazada; errores de subida, sesión vencida y operación financiera pendiente. Revisar teclado, móvil y ambos temas en los nuevos formularios.

Comandos existentes: desde `Pagina Web/frontend`, `npm run lint`, `npm test`, `npm run build`; desde la raíz, `python -m unittest discover -s 'Pagina Web/tests/e2e' -v`; backend con su entorno virtual y `backend/tests/run_postgres.py` para la base temporal.
