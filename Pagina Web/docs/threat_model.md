# Modelado de Amenazas de Flujos Críticos (TickerTrader)

Conforme a los requerimientos de seguridad de OWASP, este documento detalla el análisis de amenazas de los principales flujos de negocio del marketplace.

---

## 1. Publicación del Ticket (Upload)

*   **Quién puede iniciarlo:** Usuarios registrados y autenticados (con límite de 10 tickets/día).
*   **Qué datos puede modificar:** Crea un registro en la tabla `Ticket`. El precio, zona y nombre del evento son definidos por el usuario, pero con límites de rango (S/ 1 a S/ 5,000) validados en el servidor.
*   **Qué estados son válidos:** El ticket nace en estado `DISPONIBLE`.
*   **Qué pasa si se repite:** Se calcula el hash SHA-256 del contenido del QR. Si un ticket con ese mismo hash ya está activo, la transacción es rechazada (Previene duplicados).
*   **Qué pasa si ocurre simultáneamente:** El constraint `UNIQUE` en backend rechaza la carrera de datos.
*   **Qué pasa si falla en la mitad:** La imagen no se asocia a la base de datos o se hace un rollback de SQLAlchemy.
*   **Qué evidencia queda:** Se registra `TICKET_PUBLISHED` en `AuditLog`.
*   **Cómo se revierte:** El vendedor puede desactivar/eliminar la publicación si el estado aún es `DISPONIBLE`.

---

## 2. Reserva de Entradas (Bloqueo transaccional)

*   **Quién puede iniciarlo:** Un usuario autenticado distinto al vendedor (previene auto-compra para lavado).
*   **Qué datos puede modificar:** Cambia el estado del ticket a `RESERVADA`, asigna el `buyer_id` temporal, y fija un timeout (`reserved_until`).
*   **Qué estados son válidos:** Requiere que el estado original sea estrictamente `DISPONIBLE`.
*   **Qué pasa si se repite:** Si el estado ya es `RESERVADA`, el sistema rechaza la solicitud HTTP 409.
*   **Qué pasa si ocurre simultáneamente:** La base de datos utiliza `SELECT FOR UPDATE` (row-level lock) en PostgreSQL. El primer request bloquea la fila y el segundo es rechazado. (Previene Doble Venta).
*   **Qué pasa si falla en la mitad:** SQLAlchemy realiza un rollback automático de toda la transacción.
*   **Qué evidencia queda:** No se registra en AuditLog permanentemente hasta que el pago se concrete o expire, limitando basura transaccional, pero queda en los logs HTTP.
*   **Cómo se revierte:** Un Job en background (BackgroundWorker) busca automáticamente reservas expiradas (> 10 minutos) y revierte el estado a `DISPONIBLE`.

---

## 3. Confirmación del Pago (Compra Definitiva)

*   **Quién puede iniciarlo:** El webhook seguro de Culqi, o el cliente enviando el token (sujeto a validación idempotente).
*   **Qué datos puede modificar:** Transiciona el ticket a `VENDIDA`. Registra el movimiento financiero en la tabla `Transaction`.
*   **Qué estados son válidos:** Requiere que el ticket esté en estado `RESERVADA` a favor de quien paga.
*   **Qué pasa si se repite:** El sistema exige y valida idempotencia: el `culqi_charge_id` (o token) es verificado. Si ya existe, se rechaza la duplicidad.
*   **Qué pasa si ocurre simultáneamente:** Las restricciones `UNIQUE` de la BD sobre el charge ID abortan la transacción doble.
*   **Qué pasa si falla en la mitad:** Al igual que la reserva, se ejecuta el rollback de la DB.
*   **Qué evidencia queda:** Se registran `PAYMENT_SUCCEEDED` (o `PAYMENT_WEBHOOK_SUCCEEDED`) en `AuditLog`. La IP, monto total y comisión quedan plasmadas en `Transaction`.
*   **Cómo se revierte:** Al ser un cambio financiero, solo los administradores o un proceso de disputa verificado pueden transicionar la entrada a `REEMBOLSADA`.

---

## 4. Entrega de la Entrada (Visualización del QR)

*   **Quién puede iniciarlo:** Única y exclusivamente el usuario registrado que sea el dueño actual (`buyer_id`) de una entrada en estado `VENDIDA`.
*   **Qué datos puede modificar:** Genera un token HMAC temporal de descarga en la transacción.
*   **Qué estados son válidos:** Solo si la transacción tuvo status `SUCCEEDED`.
*   **Qué pasa si se repite:** El token de descarga HMAC es de 1 solo uso. Al abrir el QR por segunda vez con el mismo enlace, se obtiene un error HTTP 410 Gone.
*   **Qué pasa si falla en la mitad:** El token no se marca como usado.
*   **Qué evidencia queda:** Queda asentado el evento `QR_DOWNLOADED` en `AuditLog`.
*   **Cómo se revierte:** N/A (Operación de lectura).

---

## 5. Registro y Autenticación de Usuario

*   **Quién puede iniciarlo:** Cualquier usuario anónimo (limitado a 5 por minuto por IP).
*   **Qué datos puede modificar:** Crea una fila en `User`.
*   **Qué estados son válidos:** N/A.
*   **Qué pasa si se repite:** Constraint `UNIQUE` en email y DNI lo impiden.
*   **Qué evidencia queda:** Logs de `USER_REGISTERED` y fallos `FAILED_LOGIN` en `AuditLog` (IP y usuario, NUNCA contraseñas).
*   **Cómo se revierte:** Suspensión de la cuenta (`is_suspended=True`).
