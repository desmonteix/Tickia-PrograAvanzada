# Design System Tickia — "Wrapped Model"

## Concepto
Una estructura visual fija + una capa de color/energía que cambia por evento.
La estructura nunca cambia. El color sí.

---

## CAPA FIJA (no tocar nunca)

### Tipografía (inamovible)
| Uso | Fuente | Tamaño base |
|---|---|---|
| Hero / impacto | BigShoulders-Bold | 120–200px |
| Títulos | Outfit-Bold | 48–72px |
| Body | Outfit-Regular | 32–40px |
| Labels / datos | GeistMono-Regular | 22–28px |

### Layout Grid (inamovible)
- Margen lateral: 60px
- Zona header: top 0–90px (label de contexto + progress bar)
- Zona hero: 90–820px (elemento dominante)
- Zona footer: 820–1080px (CTA / logo / slide número)

### Componentes fijos
- Progress bar: 4px top, relleno en accent color
- Logo "Tickia": siempre footer-center, Outfit-Bold 28px
- Slide number: footer-left, GeistMono 22px, gris
- Corner L-bracket: top-right, 28×28px, en accent color

### Arquetipos de slide (layouts fijos)
| Tipo | Descripción | Uso |
|---|---|---|
| IMPACT | Color fill 100%, texto blanco masivo | LUZ ROJA, momentos de clímax |
| SPLIT | Dark top 55% / color bottom 45%, texto atraviesa el corte | Dinero, cifras clave |
| GLOW | Dark gradient, elemento hero con glow de color | Portadas, cierres |
| DATA | Dark bg, número o dato como héroe visual | Estadísticas, contadores |
| SAFE | Dark-to-green, ícono + CTA | Slides de solución |

---

## CAPA VARIABLE (cambia por evento/artista)

### Variables de un skin
```
skin = {
  "name":     "BTS Lima 2026",
  "bg_a":     color base (siempre cerca de #0A0A0A),
  "bg_b":     tinte del gradiente inferior,
  "accent":   color primario del evento,
  "energy":   color secundario / urgencia,
  "label_col": color de los tags // ESCENA 01 etc.,
  "hero_col": color del texto hero (blanco o el accent),
  "panel_bg": fondo de paneles de datos,
}
```

### Skins planificados
| Evento | accent | energy | bg_b |
|---|---|---|---|
| Default Tickia | #8B5CF6 púrpura | #F97316 naranja eléctrico | #1a0830 |
| BTS (octubre) | #5B21B6 violeta profundo | #EC4899 rosa BTS | #0d0520 |
| Alianza vs Universitario | #003F8A azul Alianza | #CC0000 rojo U | #000a1a |
| Reggaetón Fest | #F97316 naranja | #FBBF24 gold | #1a0a00 |
| Coldplay | #3B82F6 azul | #22D3EE cyan | #001020 |

---

## Regla de oro
> El fandom ve el slide y siente: "esto es para mí."
> Tickia sigue siendo Tickia: misma tipografía, mismo logo, mismo layout.
> Solo cambia el mundo de color alrededor.

---

## Cómo crear un nuevo skin (paso a paso)
1. Identifica el color dominante del artista/evento (buscar en sus propias redes)
2. Define accent (color principal) y energy (color de urgencia/CTA)
3. Asegúrate de que haya contraste suficiente entre hero text (#FFF) y el accent
4. Aplica el skin al generador (`SKIN = SKINS["nombre"]`)
5. Genera los 15 archivos y revisar el smoke test: portada + luz roja + cierre
