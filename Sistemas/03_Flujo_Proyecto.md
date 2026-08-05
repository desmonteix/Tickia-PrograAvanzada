# Flujo del Proyecto (Tickia)

El ciclo de vida de una entrada en la plataforma Tickia desde que se publica hasta que el vendedor recibe su dinero.

## 1. Fase de Publicación (Vendedor)
1.  El Vendedor accede a **"Vender"**.
2.  Sube el PDF original y rellena los datos (Evento, Fecha, Zona, Tipo, Precio).
3.  *Seguridad en Segundo Plano:* El sistema verifica el hash criptográfico del PDF para evitar duplicados. Además, se activa la **Barrera Anti-Evasión**, escaneando la descripción buscando teléfonos o Instagrams (si detecta trampa, banea al usuario de inmediato).
4.  La entrada aparece en el Catálogo como `DISPONIBLE`.
5.  *Social Boost:* El vendedor descarga la Tarjeta de Story y la sube a Instagram. Si atrae tráfico, la entrada se dispara a la cima del catálogo y la comisión baja a 0%.

## 2. Fase de Compra (Comprador)
1.  El Comprador encuentra la entrada en el Catálogo y hace clic en Comprar.
2.  El estado cambia a `RESERVADA` (nadie más puede comprarla por X minutos).
3.  El Comprador paga (vía Culqi/Stripe). El dinero se retiene en la cuenta de Tickia (Escrow).
4.  Al confirmarse el pago, el estado pasa a `PENDIENTE_RENOMINACION`. El Vendedor recibe los datos del comprador.

## 3. Fase de Renominación y Tiempos Límite (El Reloj)
1.  El Vendedor debe ir a Teleticket/Joinnus, pagar el cambio de nombre, y subir el nuevo PDF a Tickia.
2.  *El Deadline:* Tiene 24 horas (o hasta el inicio del evento, lo que ocurra primero).
3.  *Aviso y Extensión:* Si se cumplen 24h y falta mucho para el evento, el sistema le da una "última oportunidad" de 12 horas extra, enviándole una alerta severa.
4.  *Reembolso Automático:* Si el tiempo final se agota y no subió el PDF, el dinero es devuelto al Comprador y el Vendedor es suspendido (Sistema de Penalidades).

## 4. Fase de Entrega y Disputas
1.  Si el Vendedor sube el PDF renominado a tiempo, el estado cambia a `VENDIDA` (o completada).
2.  El Comprador descarga su entrada.
3.  *Ventana de Disputa:* Si el PDF es falso o tiene el nombre incorrecto, el Comprador puede presionar "Tengo un problema" y abrir una **Disputa Manual**. Esto congela el dinero indefinidamente hasta que el Admin de Tickia revise los PDFs y falle a favor de uno de los dos.

## 5. Fase Final (Liquidación)
1.  Si no hay disputa (o el evento ya pasó sin reclamos), el dinero es liberado al Vendedor, reteniendo la comisión de Tickia (salvo que haya activado exitosamente el Social Boost).
