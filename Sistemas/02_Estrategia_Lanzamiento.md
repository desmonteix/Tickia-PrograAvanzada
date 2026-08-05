# Estrategia de Lanzamiento: Waitlist & Viralidad

Para asegurar un lanzamiento explosivo y evitar que el catálogo de entradas se vea vacío el Día 1, ejecutaremos una estrategia de **"Puerta Cerrada" con Listas de Espera (Waitlist)**.

## 1. El Bloqueo Temporal (Gatekeeper)
Antes de la fecha de apertura oficial, la plataforma principal de Tickia estará inaccesible para el público. Cualquiera que intente navegar hacia el catálogo o las opciones de compra/venta será interceptado por el "Gatekeeper" y redirigido a una sala de espera virtual.

## 2. La Dinámica de la Cola y el Link Único
*   Al registrarse (dejando su correo), el usuario adquiere un número en la fila (ej. "Eres el número #1450 en la cola").
*   Automáticamente, el sistema le genera un **link de referido único**.
*   **El Incentivo Egoísta:** Se le indica claramente al usuario que, por cada amigo que se registre usando su enlace, él **saltará posiciones** hacia adelante en la cola.

## 3. ¿Por qué funciona esto?
Las apps virales (como Robinhood o Monzo) demostraron que la gente no comparte productos por altruismo corporativo, sino para ganar un beneficio directo (acceso anticipado, mejores lugares, o recompensas). 
Al crear esta fricción artificial (escasez), el usuario promedio pondrá su link de Tickia en sus historias de Instagram o grupos de WhatsApp de conciertos, haciendo el marketing por nosotros.

## 4. El Día Cero (Lanzamiento)
*   En la fecha estipulada (guiada por el temporizador en pantalla), Tickia no abrirá sus puertas a todo el mundo de golpe.
*   El administrador usará el panel interno para liberar el acceso (cambiando la variable `has_access` a `True`) en **bloques controlados** (por ejemplo, los primeros 500 de la fila).
*   Esto genera una ola de FOMO (Fear Of Missing Out) en redes sociales, con usuarios presumiendo que "ya entraron" y los rezagados compartiendo sus links con más desesperación para subir de puesto.
