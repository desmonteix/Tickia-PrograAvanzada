# Auditoría de producción · Tickia

Fecha: 2026-11-04 (America/Lima). Solicitud: auditoría completa, correcciones, retirada de lista de espera y aplicación de los dos PDF Tickia de la raíz.

## Criterios de aceptación

- Registro e inicio de sesión abiertos, sin lista de espera ni invitaciones.
- Contratos frontend/backend compatibles en registro, publicación, compra y descarga.
- Ningún catálogo, entrada, QR o pago ficticio en el producto ante errores.
- Cobros confirmados con proveedor; configuración incompleta rechaza la operación.
- Controles de propiedad, administración, suspensión, duplicados y reserva concurrente.
- Validación de archivos, importes, fechas y entradas malformadas; errores recuperables.
- Pruebas backend aisladas, E2E con navegador y API real local, y pruebas de fallos de red.
- Compilación, tipos, lint y auditoría de dependencias con resultados documentados.
- Navegación por teclado, formularios etiquetados, móvil y temas claro/oscuro.
- Identidad: Ruta A recomendada en PDF, eslogan, Sora/DM Sans/Space Grotesk y paleta del manual. Sin garantías absolutas inventadas.
- CI ejecutable desde la raíz; instrucciones de despliegue y bloqueos externos explícitos.

## Línea base observada

- Frontend compila; ESLint falla con 23 errores.
- `npm audit`: 29 vulnerabilidades (16 altas, 12 moderadas, 1 baja).
- No existe suite de pruebas ni CI activo en `.github/workflows` de la raíz.
- Registro UI envía nombre/DNI pero API exige teléfono.
- Publicación UI envía `ticket_type` pero API exige dos booleanos.
- Billetera solicita descarga por ID y JSON pero API espera token y devuelve bytes.
- Catálogo y billetera muestran datos ficticios si falla la API.
- Pago marca éxito sin cobrar; QR usa valores aleatorios; renominación produce error.

## Alcance y límites

Bobby realiza revisión y correcciones independientes del backend; agente principal integra UI, marca, despliegue y navegador. Pruebas usan datos y servicios aislados, sin tocar base real ni cobrar dinero. Una suite finita cubre escenarios definidos, no demuestra todos los estados posibles. La habilitación de cobros reales requiere credenciales, conciliación y validación externa; no se declarará el lanzamiento aprobado mientras existan bloqueos.
