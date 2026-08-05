# Identidad Visual y Paleta de Colores (Tickia)

Para transmitir el posicionamiento de una plataforma financiera ("Bóveda Segura") que a la vez opera en la industria musical, el diseño debe ser **Premium, Nocturno y Futurista**.

## 1. El Concepto Visual
**Dark Mode por Defecto (Modo Oscuro).**
La industria de los conciertos y la vida nocturna ocurre en la oscuridad, iluminada por luces de neón y pantallas. Nuestro diseño refleja eso. Un fondo oscuro transmite exclusividad, reduce la fatiga visual al escanear catálogos y hace que los colores de acento resalten dramáticamente (generando un efecto de urgencia y tecnología).

## 2. Paleta de Colores

### Colores Base (Estructura y Fondos)
*   **Fondo Principal (Background):** `Negro Carbón (#0A0A0A)` - Un negro casi puro, no molesta a la vista pero da profundidad absoluta.
*   **Fondo Secundario (Tarjetas/Paneles):** `Gris Asfalto (#171717)` o `Gris Zafiro Oscuro (#111827)` - Para crear elevación y separar contenedores de contenido del fondo.
*   **Texto Principal:** `Blanco Hueso (#F3F4F6)` - Para máxima legibilidad sin el brillo hiriente del blanco puro.
*   **Texto Secundario:** `Gris Pizarra (#9CA3AF)` - Para fechas, subtítulos e información de apoyo.

### Colores de Acento (Llamados a la Acción y Estados)
*   **Acento Principal (Primario):** `Púrpura Eléctrico (#8B5CF6)` o `Azul Neón (#3B82F6)` - Se usa para el botón principal ("Comprar", "Crear Listado"). El púrpura transmite lujo, creatividad y música; el azul transmite seguridad financiera. (Recomendado: Gradiente entre ambos).
*   **Éxito / Seguridad:** `Verde Esmeralda (#10B981)` - Para estados como "Pago Asegurado", "Entrada Renominada" o para destacar el "0% de Comisión" del Social Boost.
*   **Peligro / Urgencia:** `Rojo Carmesí (#EF4444)` o `Naranja Alarma (#F97316)` - Vital para el temporizador de la *Waitlist*, deadlines a punto de expirar y estados como "Disputa Abierta" o "Cuenta Suspendida".
*   **Destacado / Fuego:** `Amarillo Oro (#FBBF24)` - Exclusivo para resaltar entradas que tienen el *Social Boost* activo (las que atraen tráfico).

## 3. Tipografía (Fuentes)
Debemos huir de fuentes tradicionales como Arial o Times New Roman. Necesitamos algo limpio, geométrico y altamente legible en pantallas.

*   **Tipografía Principal (Títulos e Interfaz):** *Inter* o *Outfit*. (Google Fonts).
    *   *Por qué:* Son fuentes sin serifas (sans-serif), neutras pero con muchísima personalidad en sus pesos más gruesos (Bold/Black). Dan un aspecto de aplicación moderna de Sillicon Valley.
*   **Tipografía Secundaria (Números y Temporizadores):** *JetBrains Mono* o *Roboto Mono*.
    *   *Por qué:* Usar una fuente monoespaciada para el temporizador de la Waitlist o los códigos de boletos genera un impacto de "sistema computacional exacto" o "reloj de alta precisión".

## 4. Efectos Adicionales (Micro-interacciones)
*   **Glassmorphism:** Las tarjetas superpuestas (como modales de advertencia o el menú de navegación) deben tener un ligero desenfoque en el fondo (`backdrop-blur`) simulando cristal oscuro esmerilado.
*   **Bordes Luminosos:** Las entradas destacadas por *Social Boost* no solo tienen un ícono, sino un tenue borde brillante (box-shadow) en color oro o púrpura para captar la atención de inmediato en el catálogo.
