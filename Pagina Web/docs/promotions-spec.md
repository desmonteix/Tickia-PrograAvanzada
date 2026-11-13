# Promociones de lanzamiento de Tickia

## Objetivo y reglas confirmadas

Implementar las promociones autorizadas y ampliadas el 12 de noviembre de 2026. La ventana inicial es
`[2026-11-13 00:00, 2026-12-13 00:00)` en Perú (UTC−05:00), exactamente 30 días.

| Módulo | Responsabilidad | Dependencia |
| --- | --- | --- |
| launch-commission | Fijar 5 % en entradas publicadas en la ventana; 10 % fuera | Precio y publicación |
| referral-reward | Atribuir un registro nuevo y conceder un único beneficio de compra | Registro y campaña |
| promotional-checkout | Reservar, cobrar, conciliar y consumir el descuento sin duplicarlo | Ambos módulos |

Orden: cálculo monetario y persistencia → publicación → referidos → checkout y
conciliación → interfaz → migración y pruebas. No se añaden proveedores ni dependencias.

## Comisión

- La fecha válida es la publicación inicial que guarda el servidor, nunca una fecha enviada por el cliente.
- El 5 % es la comisión final con IGV incluido, en lugar del 10 %. Los cargos del proveedor siguen a cargo del vendedor.
- La tasa queda guardada en la entrada y se copia a cada operación. Vender después del 12 de diciembre no elimina el beneficio.
- Las operaciones históricas conservan sus importes. No se recalculan pagos ya iniciados.

## Referidos

- Cuenta una persona nueva que se registra con el enlace/código del usuario durante la ventana.
- El beneficio pertenece a quien invita, no a la persona invitada. Una cuenta existente no puede añadirse después como referido.
- Cada registro tiene como máximo un referente. No se admite autorreferencia ni alterar la atribución después del registro.
- Uno o varios referidos conceden exactamente un descuento del 5 % del precio publicado. No se acumula ni se vuelve a generar tras usarlo.
- Puede usarse después de la campaña y por usuarios con compras anteriores: aplica a su primera compra elegible posterior a obtenerlo.
- Tickia financia el descuento. La comisión y la estimación del vendedor parten del precio publicado, no del precio descontado.
- Ejemplo: precio S/ 100, comisión promocional S/ 5, descuento S/ 5: comprador paga S/ 95; vendedor tiene S/ 95 antes de los cargos externos. La comisión contable sigue siendo S/ 5 y el subsidio de Tickia S/ 5.

## Referidos que empiezan a vender

- El referente gana la mejora cuando la persona invitada publica su **primera entrada válida** dentro de la campaña. Un archivo inválido, una publicación rechazada o un registro aislado no conceden esta mejora.
- La atribución se captura únicamente al registrarse con el código. Si la primera publicación ocurrió fuera de la campaña, las publicaciones posteriores no la vuelven a calificar.
- El beneficio único permite elegir **10 % en la siguiente compra elegible** o **0 % de comisión Tickia en la siguiente venta elegible**. Los cargos de cobro y depósito del proveedor siguen a cargo del vendedor.
- Sustituye al 5 % por registro si todavía no se usó. No acumula dos beneficios ni se rearma por invitar a más vendedores.
- La elección puede cambiar mientras esté disponible. Una reserva la bloquea; se consume al confirmar el pago, nunca al publicar una entrada.
- Si el 5 % ya está reservado, la mejora espera: ni la reserva ni un pago incierto cambian de importe. Un rechazo definitivo o el vencimiento de una reserva sin pago aplica la mejora; si el pago anterior tiene éxito, consume el único beneficio.
- La campaña limita cuándo se gana; el beneficio ganado no caduca al finalizar, deshabilitar o archivar la campaña.

## Administración y separación de responsabilidades

`campaigns.py` consulta campañas persistidas y controles de operación. `promotions.py`
concede y reserva beneficios; `money.py` solo calcula importes a partir de tasas.
No hay campañas obligatorias: sin campañas habilitadas se publica y vende con la
comisión normal del 10 %, y los beneficios obtenidos siguen siendo utilizables.

- Panel **Campañas**: crear, editar fechas/tasas, deshabilitar y archivar. Las campañas habilitadas no se superponen; las fechas llevan zona horaria. Archivar nunca elimina entradas, operaciones ni beneficios.
- Panel **Beneficios**: conceder/editar uno disponible o revocarlo individualmente con motivo. Los usados, revocados o reservados conservan su historial; no se pueden reiniciar ni cambiar durante un pago.
- Panel **Operación**: pausar nuevos registros, publicaciones y compras, activar mantenimiento y publicar un aviso. Pausar no bloquea login, compras existentes, reclamos, webhooks ni conciliaciones. Habilitar compras aquí **no** sustituye las credenciales ni los bloqueos del proveedor configurados en el servidor.
- Panel **Reclamos**: mantiene investigación, evidencia privada y decisiones válidas/no concluyentes; los fondos continúan congelados durante la investigación.
- Panel **Auditoría**: cambios administrativos con actor, entidad, fecha y motivo. Solo cuentas con `is_admin` validado en el servidor acceden a estos endpoints; no se promueven administradores desde el navegador.
- Las tasas del precio publicado, de la reserva y del pago son instantáneas independientes. Cambiar una campaña no modifica las condiciones ya publicadas ni cotizadas.
- Un comprador y un vendedor distintos pueden usar sus respectivos beneficios en una misma operación. Cada cuenta tiene una única fila de beneficio y todos los bloqueos de esas filas se adquieren en orden UUID estable.

**Financiación:** con precio S/ 100, descuento de compra del 10 % y comisión de
venta del 0 %, se cobra S/ 90 y el vendedor conserva S/ 100 antes de los cargos
externos. Tickia debe aportar el subsidio y mantener liquidez suficiente en el
proveedor. El panel muestra comisión y subsidios por separado; no los presenta
como utilidad neta. El cambio no habilita pagos reales por sí mismo.

## Reservas y resultados financieros

- La disponibilidad del descuento se fija al reservar una entrada. El servidor devuelve el desglose y el total que se debe cobrar.
- Un beneficio no puede reservarse para dos compras simultáneas. Una reserva sin intento de pago se libera al vencer sus diez minutos.
- Antes de contactar al proveedor, la intención de pago queda persistida y vinculada al beneficio.
- Un rechazo definitivo libera el beneficio para reintentar; un resultado incierto lo conserva reservado hasta la conciliación.
- Un pago verificado consume el beneficio una sola vez, también si se reciben notificaciones duplicadas. Una devolución posterior no genera un segundo beneficio.
- La devolución es del importe realmente cobrado al comprador. La promoción no autoriza devolver el precio publicado si se cobró menos.
- Los estados y precios calculados por el navegador nunca acreditan elegibilidad ni pago. No se modifican importes de una intención ya creada.

## Estructura y estilo

Backend FastAPI/SQLAlchemy en `backend/`; cálculos Decimal en `money.py` y políticas
en un módulo de promociones. Migración aditiva en `backend/migrations/`, pruebas
en `backend/tests/`. Interfaz React/TypeScript en `frontend/src/`.

```python
total = listed_amount - buyer_discount
seller_amount = listed_amount - platform_commission
```

La contabilización conserva precio, descuento, comisión y total de forma separada.
Se utiliza redondeo `ROUND_HALF_UP` a céntimos; fechas con zona horaria explícita.

## Verificación

- Unitarias: límites exactos de campaña, céntimos, comisión permanente y descuento sin acumulación.
- API/BD: registro atribuido, reserva, rechazo, incertidumbre, confirmación y webhook duplicado.
- PostgreSQL aislado: redenciones concurrentes y migración repetible con historial conservado.
- Navegador: enlace de invitación → registro → beneficio disponible → checkout con desglose → compra confirmada.
- Pruebas sin dinero real; proveedor simulado y base temporal. No se leen secretos locales.

Desde `Pagina Web`:

```powershell
backend/venv/Scripts/python.exe -m unittest discover -s backend/tests -v
python -m unittest discover -s tests/e2e -v
```

Desde `Pagina Web/frontend`:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

## Límites operativos

La migración debe aplicarse antes de desplegar la versión que use sus columnas.
Orden para esta entrega: `launch_promotions.sql` y después `campaign_controls.sql`.
La segunda es repetible, conserva el historial y no reactiva una campaña que el
administrador haya deshabilitado. Primero aplicar y verificar en staging con un
respaldo recuperable. Si se revierte la aplicación, conservar las tablas y los
importes y pausar nuevas compras; no borrar beneficios ni reconstruir el libro
financiero. Una reversión de datos requiere revisión manual, nunca un DROP automático.
No se ejecutan cambios de esquema contra producción con credenciales tomadas del
chat o archivos privados. Se mantienen las validaciones de pagos, la verificación
del proveedor, las cookies seguras, el bloqueo de reclamos y los cargos al vendedor.
