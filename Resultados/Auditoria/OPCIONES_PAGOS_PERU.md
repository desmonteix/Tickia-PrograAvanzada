# Pagos y abonos para Tickia en Perú

Investigación: 5 de noviembre de 2026. Supuesto de trabajo: Tickia opera mediante una empresa peruana, cobra en soles y paga a vendedores con cuentas bancarias peruanas. Si la entidad está en otro país, debe revisarse la elegibilidad.

## Recomendación

Evaluar **Kushki primero para la operación bancaria local y dLocal Platforms en paralelo para el modelo de marketplace**. Es una recomendación técnica condicionada: ninguna documentación pública consultada confirma por sí sola la aprobación comercial de todo el flujo de Tickia. No se ha contratado, contactado ni elegido un proveedor.

La decisión depende de que acepten por escrito la reventa de entradas entre particulares, el plazo entre compra y concierto, la retención durante reclamos y el reembolso íntegro al comprador. Las compras pueden anticiparse meses al evento; no basta permitir una demora de unos días.

## Comparación

| Opción | Evidencia pública | Implicación para Tickia |
|---|---|---|
| **Kushki PayIns + Transfer Out** | Dispersión bancaria en PEN a personas y empresas, consulta de estados y notificación final. | Buen candidato local. Requiere certificar la integración y aclarar financiación del saldo, retención y aceptación de vendedores particulares. |
| **dLocal Platforms + Payouts** | Cuentas de plataforma/vendedores, KYC, cuentas para mantener fondos, reparto y responsabilidad de cargos. Su API de payouts documenta Perú. | Es el diseño público más próximo al flujo de marketplace. Confirmar que Platforms y los abonos peruanos pueden contratarse juntos para Tickia y bajo qué volumen mínimo. |
| **Culqi** | Cobros y devoluciones; los depósitos estándar corresponden al comercio registrado. | Puede servir para cobrar. No encontré confirmación pública de una API que ordene abonos a cada vendedor con este control de liberación. No confundir consultar abonos con enviar dinero a terceros. |
| **Mercado Pago Split 1:1** | Reparto automático vendedor/marketplace; OAuth individual y comisión de pasarela al vendedor. | Facilita la comisión, pero no acredita el control de retención requerido. Un vendedor sin saldo puede impedir el reembolso total mediante el split. |
| **Stripe Connect / Global Payouts** | Amplias herramientas, con restricciones de país y producto. | No es la primera opción para una entidad exclusivamente peruana; no basta que un destinatario pueda recibir dinero en Perú. |

## Kushki: qué verificar

La guía peruana exige tokenizar la cuenta, iniciar la dispersión y consultar el resultado o recibir una notificación. El token dura 30 minutos: debe crearse al desembolsar. Una transferencia iniciada no puede anularse. Los tiempos dependen del banco y calendario; no prometer un abono instantáneo universal. La guía describe recargar fondos y una certificación previa a credenciales productivas. Deben confirmar si los cobros alimentan el saldo de dispersión o exigen prefondos separados. [Guía Transfer Out Perú](https://docs.kushki.com/pe/payouts/transfer/transfer-out/).

Su producto anuncia pagos desde Balance Kushki por API y casos de uso de marketplaces. Eso acredita capacidad de dispersión, no autorización automática para custodiar dinero de compradores hasta un concierto. [Producto PayOuts](https://www.kushkipagos.com/dispersion-de-pagos-payouts).

## dLocal: qué verificar

Platforms documenta onboarding de vendedores y cuentas «Liable» para mantener fondos. Permite configurar responsabilidad de devoluciones y contracargos. Se necesita aprobación de la combinación de productos, entidad y países concretos. [Platforms](https://docs.dlocal.com/docs/platforms-overview).

La documentación de splits permite asignar cargos a cuentas de usuarios o a la cuenta responsable. La de Perú describe transferencias a cuentas bancarias en PEN, identificador externo y datos del beneficiario. No establece una oferta comercial ni un plazo máximo de retención aplicable a Tickia. [Cargos y splits](https://docs.dlocal.com/docs/split-payments-platforms), [abonos en Perú](https://docs.dlocal.com/docs/peru-payouts-v3).

## Culqi: qué puede y qué no está demostrado

Los abonos estándar se realizan a una cuenta con la misma información que el comercio. Eso no equivale a abonar individualmente a cada vendedor. Una combinación de Culqi para cobros y otro proveedor para transferencias es una alternativa a evaluar contractualmente; añade conciliación entre dos servicios y posiblemente prefondos. [Depósitos Culqi](https://docs.culqi.com/es/documentacion/pagos-online/depositos/resumen/).

Culqi documenta devoluciones por API y diferencias de comisión/plazo según el momento del reembolso. Tickia debe confirmar cómo devolver el precio completo y quién cubre cargos no recuperables, respetando la instrucción de no trasladarlos al comprador. No presupuestar una devolución bancaria inmediata. [Devoluciones Culqi](https://docs.culqi.com/es/documentacion/pagos-online/operaciones/devoluciones/).

## Mercado Pago: encaje parcial

Split 1:1 distribuye automáticamente el cobro y utiliza OAuth de cada vendedor. La comisión de Mercado Pago se descuenta al vendedor antes de la comisión del marketplace. El reembolso se reparte entre ambas cuentas y, si al vendedor le falta saldo, el marketplace no puede completar por esa vía la devolución total. La página consultada no demuestra que Tickia pueda impedir el retiro hasta la resolución del reclamo. Por eso no lo recomiendo para este flujo sin una confirmación específica. [Integración de Split 1:1 para Perú](https://www.mercadopago.com.pe/developers/es/docs/split-payments/split-1-1/integration-configuration/integrate-marketplace).

## Stripe: elegibilidad antes que integración

Perú no figura en la lista de países para abrir una cuenta comercial estándar de Stripe. [Disponibilidad global](https://stripe.com/global).

Connect no ofrece de forma autoservicio abonos transfronterizos fuera de las regiones enumeradas en su guía; Perú no está incluido. Global Payouts tiene una elegibilidad propia: empresas de EE. UU. y Reino Unido, con otros países en vista previa. No se debe asumir que constituir una entidad extranjera garantiza la aprobación de Tickia o del flujo hacia vendedores peruanos. [Connect transfronterizo](https://docs.stripe.com/connect/connect-cross-border-payouts), [Global Payouts](https://docs.stripe.com/global-payouts).

Los abonos manuales de Connect permiten retrasar desembolsos, pero tienen límites por país —90 días en la mayoría— y Stripe aclara que no presta servicios de escrow. Esa función no prueba que una venta con meses de anticipación sea compatible. [Abonos manuales](https://docs.stripe.com/connect/manual-payouts).

## Condiciones para comparar ofertas

Solicitar a Kushki y dLocal una respuesta sobre este caso concreto:

> Tickia es un marketplace de reventa de entradas entre particulares en Perú. El comprador paga el precio publicado sin sobrecostos. La plataforma cobra al vendedor un 10 % sobre ese precio; también corresponden al vendedor los cargos de procesamiento y desembolso. El comprador recibe la entrada y puede confirmar desde ese momento. Si confirma, ordenamos el abono neto al vendedor. Si no responde, lo ordenamos 24 horas después de finalizar el evento. Un reclamo presentado a tiempo congela los fondos hasta resolución administrativa, que puede ordenar un reembolso íntegro al comprador. Necesitamos cuentas bancarias verificadas, consulta de estados, referencias únicas y protección contra duplicados. ¿Aceptan este modelo y estos plazos, incluidos conciertos comprados con meses de anticipación?

Pedir cotización completa: comisión porcentual y fija, impuestos, costo de payout, devoluciones, transferencias fallidas, contracargos, reservas, prefondos, mínimos mensuales y permanencia. No hay una cotización verificada comparable para Tickia: no se asigna un ganador por precio.

Validar además quién mantiene los fondos y bajo qué contrato, duración máxima de la retención, KYC de personas naturales, titularidad bancaria, liberación anticipada por conformidad, congelamiento por reclamo y mecanismo de reembolso si ya hubo desembolso o contracargo. Una autorización de tarjeta sin captura no sustituye una retención de meses.

## Impacto en la aplicación

El flujo y la cola financiera están preparados con estados persistentes y pruebas sin dinero real. Los abonos a vendedores siguen rechazándose explícitamente mientras no exista una integración operativa. `SETTLEMENT_ENABLED=false` conserva las órdenes pendientes; no convierte una aprobación administrativa en una transferencia ficticia. La reputación se aplica una vez confirmado el resultado financiero.

Para integrar al proveedor elegido faltan: onboarding y cuenta verificada del vendedor; adaptador de cobros/abonos compatible con ese contrato; cargos reales conciliados; notificaciones y consulta de resultados; pruebas de sandbox y certificación. No activar `PAYMENT_ENABLED` ni `SETTLEMENT_ENABLED` para producción antes de completar ese circuito.
