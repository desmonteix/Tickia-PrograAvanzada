# Estructura de la Página Web (Tickia)

La arquitectura de la aplicación web está diseñada para ser extremadamente lineal y evitar que los usuarios se pierdan. La navegación se centra en tres pilares: Comprar, Vender y Administrar (para el usuario).

## 1. El Gatekeeper (Bloqueo de Lanzamiento)
*   **WaitlistView:** Pantalla obligatoria para cualquier usuario recién registrado que aún no tiene el flag de `has_access`. Muestra:
    *   Mensaje de "Estás en la fila".
    *   Temporizador de cuenta regresiva para el lanzamiento oficial.
    *   Su posición en la cola y un botón nativo para copiar su link único de referido.

## 2. Autenticación y Onboarding
*   **AuthFlow (Login / Registro):** Pantallas minimalistas centradas en capturar el correo (y en el futuro validación DNI). Incluye detección automática del link de referido si el usuario entró invitado por un amigo.

## 3. Navegación Principal (El Catálogo)
Una vez que el usuario tiene acceso (`has_access = True` o es Admin), se desbloquea la barra superior (Navbar) con las siguientes rutas:

*   **Explorar (Catálogo Central):** La página de inicio (Hero Section) donde se listan todas las entradas disponibles. El orden está regido por el motor del *Social Boost* (primero las destacadas por tráfico orgánico).
*   **Buscar / Filtrar:** Barra de búsqueda inteligente con *Fuse.js* para encontrar eventos específicos por nombre o artista.

## 4. Gestión Personal (El Dashboard del Usuario)
*   **Mis Entradas (BuyerFlow):** Donde el comprador ve las entradas que ha pagado. Los estados fluyen desde "Pendiente de Renominación" hasta "Completado" (donde ya pueden descargar el PDF final). También incluye el botón de **Abrir Disputa** (Opción D).
*   **Vender (SellerFlow):** Pantalla para crear un nuevo listado (subiendo el ticket original, precio, etc.). 
*   **Mis Ventas:** Donde el vendedor gestiona su inventario. Aquí se muestran las alertas de *Deadlines* (tiempos límite para subir la renominación), y el botón para descargar la **Tarjeta de Instagram (Story)** para activar el Social Boost.

## 5. Panel Administrativo (Solo Admins)
*   **AdminDashboard:** Acceso exclusivo para cuentas con `is_admin = True` (ej. el equipo de Tickia).
*   **Métricas:** Ingresos, transacciones en curso.
*   **Gestión de Disputas:** Herramientas para fallar a favor del comprador o vendedor.
*   **Control de Accesos:** Herramienta para liberar usuarios de la Waitlist hacia la plataforma en vivo.
