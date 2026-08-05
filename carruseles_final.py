# -*- coding: utf-8 -*-
"""
Carruseles Tickia — Semana 1 "Nombrar el Dolor"
Copy fuente: Resultados/Copy/semana1_nombrar_el_dolor.md
Design system: Resultados/Estrategia/sistema_diseno_tickia.md
Skin: Default (purple #8B5CF6 + electric orange #F97316)
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, sys
sys.stdout.reconfigure(encoding="utf-8")

FONTS = r"C:\Users\matid\.claude\plugins\cache\anthropic-agent-skills\document-skills\b29e7cf65e5c\skills\canvas-design\canvas-fonts"
OUT   = r"C:\Users\matid\OneDrive\Documentos\TickerTrader\Resultados\Diseno"

# ── SKIN DEFAULT ──────────────────────────────────────────────────
PURPLE  = (139, 92, 246)
ORANGE  = (249, 115, 22)
GREEN   = (16, 185, 129)
RED     = (239, 68, 68)
BLUE    = (59, 130, 246)
WHITE   = (255, 255, 255)
GRAY    = (156, 163, 175)
BLACK   = (10, 10, 10)
DGRAY   = (55, 65, 81)

# ── TYPOGRAFIA ────────────────────────────────────────────────────
_sc = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

def F(kind, size):
    order = {
        "impact":  ["BigShoulders-Bold.ttf", "Outfit-Bold.ttf"],
        "bold":    ["Outfit-Bold.ttf", "BricolageGrotesque-Regular.ttf"],
        "regular": ["Outfit-Regular.ttf", "BricolageGrotesque-Regular.ttf"],
        "mono":    ["GeistMono-Regular.ttf", "JetBrainsMono-Regular.ttf"],
    }
    for n in order.get(kind, []):
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def tw(t, f): bb = _sc.textbbox((0,0), t, font=f); return bb[2]-bb[0]
def th(t, f): bb = _sc.textbbox((0,0), t, font=f); return bb[3]-bb[1]

def wrap(text, font, max_w):
    words = text.split()
    lines, cur = [], []
    for w in words:
        if tw(" ".join(cur+[w]), font) <= max_w:
            cur.append(w)
        else:
            if cur: lines.append(" ".join(cur))
            cur = [w]
    if cur: lines.append(" ".join(cur))
    return lines or [text]

# ── HELPERS CORE ─────────────────────────────────────────────────
def grad(w, h, top, bot):
    strip = Image.new("RGBA", (1, h))
    strip.putdata([tuple(int(top[i]+(bot[i]-top[i])*y/max(h-1,1)) for i in range(3))+(255,) for y in range(h)])
    return strip.resize((w, h), Image.NEAREST)

def glow_fn(img, draw_fn, blur_r):
    gl = Image.new("RGBA", img.size, (0,0,0,0))
    draw_fn(gl)
    return Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(blur_r)))

def ambient(img, cx, cy, r, col, alpha=20, blur=130):
    def f(gl): ImageDraw.Draw(gl).ellipse([cx-r,cy-r,cx+r,cy+r], fill=col+(alpha,))
    return glow_fn(img, f, blur)

def deco_circle(img, cx, cy, r, col, stroke=3, alpha=45):
    def f(gl): ImageDraw.Draw(gl).ellipse([cx-r,cy-r,cx+r,cy+r], outline=col+(alpha,), width=stroke)
    return glow_fn(img, f, 4)

def txt_c(img, text, font, cy, color, glow_col=None, glow_r=20, max_w=None):
    """Draw text centered at cy. Returns (img, bottom_y)."""
    W = img.width
    mw = max_w or W-80
    lines = wrap(text, font, mw)
    lh = th("Ag", font)
    sp = int(lh*0.2)
    total = len(lines)*lh + max(len(lines)-1,0)*sp
    y = cy - total//2
    for line in lines:
        x = W//2 - tw(line,font)//2
        if glow_col:
            def f(gl, x=x, y=y, line=line):
                ImageDraw.Draw(gl).text((x,y), line, font=font, fill=glow_col+(140,))
            img = glow_fn(img, f, glow_r)
        ImageDraw.Draw(img).text((x,y), line, font=font, fill=color)
        y += lh+sp
    return img, cy + total//2

def txt_l(img, text, font, x, y, color):
    ImageDraw.Draw(img).text((x,y), text, font=font, fill=color)

def hline(img, x1, y, x2, col, w=2, gr=0):
    if gr:
        def f(gl): ImageDraw.Draw(gl).rectangle([x1,y-w*2,x2,y+w*2], fill=col+(100,))
        img = glow_fn(img, f, gr)
    ImageDraw.Draw(img).rectangle([x1,y,x2,y+w], fill=col)
    return img

def color_band(img, y1, y2, col):
    block = Image.new("RGBA", (img.width, y2-y1), col+(255,))
    out = img.copy(); out.paste(block, (0, y1)); return out

def panel(img, x1,y1,x2,y2, fill, border, r=12, glow_r=8):
    def f(gl): ImageDraw.Draw(gl).rounded_rectangle([x1,y1,x2,y2], radius=r, outline=border+(150,), width=2)
    img = glow_fn(img, f, glow_r)
    ImageDraw.Draw(img).rounded_rectangle([x1,y1,x2,y2], radius=r, fill=fill, outline=border, width=1)
    return img

def progress(img, frac, col):
    ImageDraw.Draw(img).rectangle([0,0,img.width,4], fill=(20,20,20))
    ImageDraw.Draw(img).rectangle([0,0,int(img.width*frac),4], fill=col)

def slide_num(img, n, total):
    f = F("mono", 22)
    ImageDraw.Draw(img).text((44, img.height-52), f"{n:02d} / {total:02d}", font=f, fill=GRAY)

def logo(img, col=GRAY):
    f = F("bold", 28)
    W,H = img.size
    t = "Tickia"
    ImageDraw.Draw(img).text((W//2-tw(t,f)//2, H-46), t, font=f, fill=col)

def corner_bracket(img, col):
    W = img.width
    d = ImageDraw.Draw(img)
    d.rectangle([W-50, 22, W-20, 24], fill=col)
    d.rectangle([W-22, 22, W-20, 52], fill=col)

def left_bar(img, col):
    gl = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(gl).rectangle([0,0,4,img.height], fill=col+(200,))
    img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(img).rectangle([0,0,3,img.height], fill=col)

def lock_icon(img, cx, cy, sz=90, col=GREEN):
    gl = Image.new("RGBA", img.size, (0,0,0,0))
    gd = ImageDraw.Draw(gl)
    bx,by = cx-sz//2, cy; bw,bh = sz, int(sz*0.65)
    gd.rounded_rectangle([bx,by,bx+bw,by+bh], radius=8, fill=col+(100,))
    sw=int(sz*0.38); sx=cx-sw//2
    gd.arc([sx,cy-sz//2,sx+sw,cy+int(sz*0.25)], 180, 0, fill=col+(100,), width=int(sz*0.14))
    img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx,by,bx+bw,by+bh], radius=8, fill=col)
    d.arc([sx,cy-sz//2,sx+sw,cy+int(sz*0.25)], 180, 0, fill=col, width=int(sz*0.14))
    d.ellipse([cx-7,by+12,cx+7,by+28], fill=BLACK)
    return img

def cta_btn(img, text, cy, col):
    f = F("bold", 36)
    W = img.width
    tw_ = tw(text,f); th_ = th(text,f)
    bx = W//2 - (tw_+60)//2
    ImageDraw.Draw(img).rounded_rectangle([bx,cy,bx+tw_+60,cy+th_+22], radius=14, fill=col)
    ImageDraw.Draw(img).text((bx+30, cy+11), text, font=f, fill=BLACK)

S = 1080  # canvas size

# ═══════════════════════════════════════════════════════════════════════════
# CARRUSEL 1 — COMPRADOR — 7 slides
# Copy: Pieza 4 de semana1_nombrar_el_dolor.md
# ═══════════════════════════════════════════════════════════════════════════

# ── PORTADA C1 — "Asi se ve comprar en reventa en Lima hoy." ──────────────
# Archetype: GLOW | Accent: purple | Label: orange
img = grad(S, S, BLACK, (20, 8, 42))
img = ambient(img, S+60, -60, 580, PURPLE, alpha=22, blur=150)
img = deco_circle(img, S+60, -60, 340, PURPLE, stroke=3, alpha=40)
img = deco_circle(img, S+60, -60, 210, ORANGE, stroke=2, alpha=30)
progress(img, 1/7, PURPLE); corner_bracket(img, ORANGE)
txt_l(img, "CARRUSEL 01 — COMPRADOR", F("mono",21), 60, 52, ORANGE)
img, bot = txt_c(img, "Asi se ve comprar una entrada en reventa en Lima hoy.",
                 F("impact",94), S//2-50, WHITE, glow_col=PURPLE, glow_r=14, max_w=S-80)
img = hline(img, 60, bot+28, S-60, ORANGE, w=3, gr=10)
img, _ = txt_c(img, "(No es bonito.)", F("bold",34), bot+72, RED)
img, _ = txt_c(img, "Desliza  ->", F("regular",24), S-80, DGRAY)
logo(img)
img.save(os.path.join(OUT, "c1_portada.png")); print("OK c1_portada.png")

# ── SLIDE 1/7 — "Encuentras al vendedor en un grupo de Facebook." ──────────
# Archetype: GLOW | Danger: ambient orange
img = grad(S, S, BLACK, (22, 10, 6))
img = ambient(img, -80, S//2, 380, ORANGE, alpha=10, blur=120)
progress(img, 2/7, PURPLE); corner_bracket(img, ORANGE); slide_num(img, 2, 7)
txt_l(img, "// ESCENA 01", F("mono",22), 60, 52, ORANGE)
img, bot = txt_c(img, "Encuentras al vendedor en un grupo de Facebook.",
                 F("bold",60), S//2-80, WHITE, max_w=S-100)
img = hline(img, 60, bot+22, S-60, DGRAY, w=1, gr=0)
f_s = F("regular",36)
img, b2 = txt_c(img, "Parece confiable.", f_s, bot+62, GRAY)
img, _ = txt_c(img, "Tiene fotos. Comentarios. Historia.", F("mono",28), b2+14, DGRAY)
# Pill tag
f_tag = F("mono",21); tag = "  TODO PARECE NORMAL  "
tw_t = tw(tag,f_tag)
tx = S//2 - (tw_t+24)//2
d = ImageDraw.Draw(img)
d.rounded_rectangle([tx, S-100, tx+tw_t+24, S-65], radius=20, fill=(35,22,5), outline=ORANGE, width=1)
d.text((tx+12, S-92), tag, font=f_tag, fill=ORANGE)
logo(img)
img.save(os.path.join(OUT, "c1_s01_vendedor.png")); print("OK c1_s01_vendedor.png")

# ── SLIDE 2/7 — "Le transfieres. 300 soles. 500. 800." ────────────────────
# Archetype: BAND | Purple band mid-screen, amounts in white on purple
img = grad(S, S, BLACK, (14, 8, 30))
img = ambient(img, S//2, S//2, 400, PURPLE, alpha=16, blur=130)
progress(img, 3/7, PURPLE); corner_bracket(img, PURPLE); slide_num(img, 3, 7)
txt_l(img, "// ESCENA 02", F("mono",22), 60, 52, PURPLE)

# "Le transfieres." header
f_b = F("bold",60)
img, _ = txt_c(img, "Le transfieres.", f_b, 185, WHITE)

# Purple mid-band
band_y1, band_y2 = 270, 620
img = color_band(img, band_y1, band_y2, PURPLE)
# Glow on band edges
def _bg(gl):
    ImageDraw.Draw(gl).rectangle([0, band_y1-2, S, band_y1+4], fill=PURPLE+(180,))
    ImageDraw.Draw(gl).rectangle([0, band_y2-4, S, band_y2+2], fill=PURPLE+(180,))
img = glow_fn(img, _bg, 12)

# Amounts on band — stacked, escalating size
amounts = [("300 soles.", 56), ("500 soles.", 72), ("800 soles.", 92)]
cy_a = band_y1 + 30
for txt_a, sz in amounts:
    f_a = F("impact", sz)
    lh_a = th(txt_a, f_a)
    ImageDraw.Draw(img).text((S//2-tw(txt_a,f_a)//2, cy_a), txt_a, font=f_a, fill=WHITE)
    cy_a += lh_a + 12

img = hline(img, 60, band_y2+18, S-60, DGRAY, w=1, gr=0)
img, _ = txt_c(img, "Y esperas.", F("regular",42), band_y2+80, GRAY)

logo(img)
img.save(os.path.join(OUT, "c1_s02_transferiste.png")); print("OK c1_s02_transferiste.png")

# ── SLIDE 3/7 — "A veces llega el PDF..." ─────────────────────────────────
# Archetype: GLOW + red panel
img = grad(S, S, BLACK, (28, 6, 6))
img = ambient(img, S//2, S//2+80, 400, RED, alpha=14, blur=120)
progress(img, 4/7, RED); corner_bracket(img, RED); slide_num(img, 4, 7)
txt_l(img, "// ESCENA 03", F("mono",22), 60, 52, RED)

f_g = F("bold",52)
img, b1 = txt_c(img, "A veces llega el PDF.", f_g, 200, GRAY)
img, b2 = txt_c(img, "A veces no llega nadie.", f_g, b1+14, GRAY)

# Red panel for the worst case
img = panel(img, 50, b2+35, S-50, b2+245, (55,8,8), RED, r=14, glow_r=10)
f_r = F("bold",40)
cy_r = b2 + 58
for line in ["A veces el PDF llega —", "y tiene el nombre", "de otra persona."]:
    img, _ = txt_c(img, line, f_r, cy_r, RED)
    cy_r += th(line, f_r) + 16

img = hline(img, 60, b2+265, S-60, DGRAY, w=1, gr=0)
img, _ = txt_c(img, "Tu dinero ya salio. La entrada, no.", F("regular",32), b2+300, GRAY)

logo(img)
img.save(os.path.join(OUT, "c1_s03_pdf.png")); print("OK c1_s03_pdf.png")

# ── SLIDE 4/7 — "Luz roja." IMPACT ────────────────────────────────────────
# Archetype: IMPACT — full red background
img = Image.new("RGBA", (S, S), (185, 15, 15, 255))
# Radial vignette: brighter center
vig = Image.new("RGBA", (S, S), (210, 25, 25, 255))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).ellipse([S//2-580, S//2-580, S//2+580, S//2+580], fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(220))
img.paste(vig, mask=mask)
progress(img, 5/7, (255,80,80)); slide_num(img, 5, 7)

txt_l(img, "// EL PEOR ESCENARIO", F("mono",20), 60, 52, (255,130,130))
img, _ = txt_c(img, "El peor escenario:", F("bold",36), 140, (255,200,200))
img, _ = txt_c(img, "Llegas a la puerta. Escanean tu codigo.", F("regular",34), 205, (255,200,200))

# MASSIVE white "LUZ ROJA."
img, _ = txt_c(img, "LUZ", F("impact",196), S//2-60, WHITE, glow_col=WHITE, glow_r=25)
img, _ = txt_c(img, "ROJA.", F("impact",196), S//2+120, WHITE, glow_col=WHITE, glow_r=25)

# Dark footer bar
ImageDraw.Draw(img).rectangle([0, S-125, S, S], fill=(120, 5, 5))
img, _ = txt_c(img, "Alguien mas ya entro con ese QR.", F("regular",34), S-78, WHITE)
logo(img, col=(255,150,150))
img.save(os.path.join(OUT, "c1_s04_luzroja.png")); print("OK c1_s04_luzroja.png")

# ── SLIDE 5/7 — "mercado sin garantia." ───────────────────────────────────
# Archetype: GLOW purple
img = grad(S, S, BLACK, (12, 8, 28))
img = ambient(img, S//2, S//2+80, 450, PURPLE, alpha=24, blur=140)
img = deco_circle(img, -80, S+80, 380, PURPLE, stroke=2, alpha=28)
progress(img, 6/7, PURPLE); corner_bracket(img, PURPLE); slide_num(img, 6, 7)
txt_l(img, "// LA REALIDAD", F("mono",22), 60, 52, PURPLE)

f_b = F("bold",46)
img, b1 = txt_c(img, "Esto no es un caso raro.", f_b, 195, WHITE)
img, b2 = txt_c(img, "Es lo que le pasa a cientos de personas en Lima cada semana.",
                f_b, b1+14, WHITE, max_w=S-100)

img = hline(img, 60, b2+28, S-60, PURPLE, w=3, gr=12)
img, b3 = txt_c(img, "Y se llama:", F("regular",38), b2+68, GRAY)
img, _ = txt_c(img, "mercado sin garantia.", F("impact",100),
               b3+18, PURPLE, glow_col=PURPLE, glow_r=26, max_w=S-60)
img = hline(img, 60, S-110, S-60, PURPLE, w=1, gr=4)
img, _ = txt_c(img, "Hasta ahora.", F("regular",32), S-84, GRAY)

logo(img)
img.save(os.path.join(OUT, "c1_s05_mercado.png")); print("OK c1_s05_mercado.png")

# ── SLIDE 6/7 — Cierre con Tickia ─────────────────────────────────────────
# Archetype: SAFE — dark to green, lock icon, CTA button
img = grad(S, S, BLACK, (5, 22, 16))
img = ambient(img, S//2, S//2, 420, GREEN, alpha=20, blur=140)
progress(img, 7/7, GREEN)

img = lock_icon(img, S//2, 130, sz=100, col=GREEN)

f_b = F("bold",44)
img, bot = txt_c(img,
    "Existe una forma en que tu dinero no le llegue al vendedor hasta que la entrada este verificada a tu nombre.",
    f_b, S//2+10, WHITE, max_w=S-90)

img = hline(img, 80, bot+24, S-80, GREEN, w=2, gr=8)

img, b2 = txt_c(img, "Todavia no abrimos.", F("regular",30), bot+58, GRAY)
cta_btn(img, "Entra a la lista  ->", b2+24, GREEN)
logo(img, col=BLUE)
img.save(os.path.join(OUT, "c1_s06_cierre.png")); print("OK c1_s06_cierre.png")

print("--- CARRUSEL 1 completo (7 slides) ---")


# ═══════════════════════════════════════════════════════════════════════════
# CARRUSEL 2 — VENDEDOR — 6 slides
# Copy: Pieza 5 de semana1_nombrar_el_dolor.md
# ═══════════════════════════════════════════════════════════════════════════

# ── PORTADA C2 — "Intentaste vender una entrada por redes." ───────────────
# Archetype: GLOW | Left bar: orange
img = grad(S, S, BLACK, (20, 8, 42))
img = ambient(img, -80, S+80, 500, PURPLE, alpha=20, blur=150)
img = deco_circle(img, S+60, -60, 310, ORANGE, stroke=3, alpha=35)
left_bar(img, ORANGE)
progress(img, 1/6, PURPLE); corner_bracket(img, ORANGE)
txt_l(img, "CARRUSEL 02 — VENDEDOR", F("mono",21), 60, 52, ORANGE)

f_b = F("bold",62)
img, bot = txt_c(img, "Intentaste vender una entrada por redes.", f_b, S//2-80, WHITE, max_w=S-100)
img = hline(img, 60, bot+22, S-60, PURPLE, w=3, gr=10)
img, _ = txt_c(img, "Aqui esta lo que en realidad paso.", F("bold",42),
               bot+76, RED, glow_col=RED, glow_r=10, max_w=S-100)
img, _ = txt_c(img, "Desliza  ->", F("regular",26), S-80, DGRAY)
logo(img)
img.save(os.path.join(OUT, "c2_portada.png")); print("OK c2_portada.png")

# ── SLIDE 1/6 — "Publicaste en tres grupos. 15 mensajes." ─────────────────
# Archetype: DATA — giant "15" watermark in orange
img = grad(S, S, BLACK, (22, 12, 6))
img = ambient(img, S//2, S//2, 380, ORANGE, alpha=12, blur=120)
progress(img, 2/6, ORANGE); corner_bracket(img, ORANGE); slide_num(img, 2, 6)
txt_l(img, "// 10 MINUTOS DESPUES", F("mono",22), 60, 52, ORANGE)

# Giant "15" ghost watermark
f_wm = F("impact", 380)
gl_wm = Image.new("RGBA", img.size, (0,0,0,0))
wm_txt = "15"
ImageDraw.Draw(gl_wm).text((S//2-tw(wm_txt,f_wm)//2, S//2-160), wm_txt, font=f_wm, fill=ORANGE+(32,))
img = Image.alpha_composite(img, gl_wm)

f_b = F("bold",52)
img, b1 = txt_c(img, "Publicaste en tres grupos.", f_b, 200, WHITE)
img, b2 = txt_c(img, "En 10 minutos ya tenias 15 mensajes.", f_b, b1+10, WHITE)

img = hline(img, 60, S-130, S-60, DGRAY, w=1, gr=0)
img, _ = txt_c(img, "Ninguno era de alguien que iba a comprar.", F("regular",34), S-94, GRAY)

logo(img)
img.save(os.path.join(OUT, "c2_s01_mensajes.png")); print("OK c2_s01_mensajes.png")

# ── SLIDE 2/6 — Chat spam ─────────────────────────────────────────────────
# Archetype: GLOW + panel dark (chat simulation)
img = grad(S, S, BLACK, (24, 8, 8))
img = ambient(img, S//2, S//2, 350, RED, alpha=12, blur=110)
progress(img, 3/6, RED); corner_bracket(img, RED); slide_num(img, 3, 6)
txt_l(img, "// LOS MENSAJES", F("mono",22), 60, 52, RED)

# Chat card
img = panel(img, 50, 115, S-50, 840, (18,8,8), RED, r=16, glow_r=10)
chat_lines = [
    ('";Sigue disponible?"',          GRAY),
    ('";Sigue disponible?"',          GRAY),
    ('";Me puedes hacer rebaja?"',    GRAY),
    ('";Cuanto menos me cobras?"',    GRAY),
    ('"Ya te mande el comprobante."', WHITE),
    ('<- nunca llego.',               RED),
]
f_ch = F("mono", 28)
cy_c = 148
for line, col in chat_lines:
    txt_l(img, line, f_ch, 82, cy_c, col)
    cy_c += th(line, f_ch) + 26

logo(img)
img.save(os.path.join(OUT, "c2_s02_chat.png")); print("OK c2_s02_chat.png")

# ── SLIDE 3/6 — "Y no volviste a saber de el." ────────────────────────────
# Archetype: GLOW purple, big hero text
img = grad(S, S, BLACK, (14, 8, 30))
img = ambient(img, S//2, S//2+60, 420, PURPLE, alpha=22, blur=140)
img = deco_circle(img, S//2, S//2, 450, PURPLE, stroke=1, alpha=18)
progress(img, 4/6, PURPLE); corner_bracket(img, PURPLE); slide_num(img, 4, 6)
txt_l(img, "// EL RIESGO", F("mono",22), 60, 52, PURPLE)

f_b = F("bold",46)
img, b1 = txt_c(img, "Decidiste arriesgar.", f_b, 195, WHITE)
img, b2 = txt_c(img, "Renominaste la entrada.", f_b, b1+8, WHITE)
img = hline(img, 80, b2+22, S-80, DGRAY, w=1, gr=0)
img, b3 = txt_c(img, "El comprador leyo tu mensaje.", F("regular",36), b2+58, GRAY)

img = hline(img, 60, b3+30, S-60, PURPLE, w=3, gr=14)

img, _ = txt_c(img, "Y no volviste a saber de el.", F("impact",100),
               S-195, WHITE, glow_col=PURPLE, glow_r=24, max_w=S-60)

logo(img)
img.save(os.path.join(OUT, "c2_s03_desaparecio.png")); print("OK c2_s03_desaparecio.png")

# ── SLIDE 4/6 — "Ahora tienes... Y empiezas de cero." ────────────────────
# Archetype: SPLIT dark/red — list in dark, "Y empiezas de cero." on red
img = grad(S, S, BLACK, (28, 6, 6))
split_y = int(S * 0.54)
img = color_band(img, split_y, S, RED)
# Glow at split line
def _sp(gl): ImageDraw.Draw(gl).rectangle([0,split_y-3,S,split_y+3], fill=RED+(160,))
img = glow_fn(img, _sp, 8)
progress(img, 5/6, RED); corner_bracket(img, RED); slide_num(img, 5, 6)
txt_l(img, "// EL RESULTADO", F("mono",22), 60, 52, RED)

f_b = F("bold",52)
img, bot = txt_c(img, "Ahora tienes:", f_b, 195, WHITE)

items = [
    "— La entrada a nombre de alguien que no existe.",
    "— 0 soles.",
    "— El concierto en 24 horas.",
]
f_list = F("mono", 28)
cy_l = bot + 22
for it in items:
    txt_l(img, it, f_list, 66, cy_l, GRAY)
    cy_l += th(it, f_list) + 20

# "Y empiezas de cero." — dark text on red (strong contrast)
img, _ = txt_c(img, "Y empiezas de cero.", F("impact",104),
               split_y + (S-split_y)//2, BLACK)

logo(img, col=BLACK)
img.save(os.path.join(OUT, "c2_s04_consecuencias.png")); print("OK c2_s04_consecuencias.png")

# ── SLIDE 5/6 — Cierre Vendedor con Tickia ────────────────────────────────
# Archetype: GLOW purple — "No al reves." como hero
img = grad(S, S, BLACK, (12, 8, 28))
img = ambient(img, S//2, S//2+60, 440, PURPLE, alpha=26, blur=140)
img = deco_circle(img, S+80, S//2, 380, PURPLE, stroke=2, alpha=25)
progress(img, 6/6, PURPLE)

f_b = F("bold",44)
img, bot = txt_c(img,
    "El dinero del comprador deberia estar retenido antes de que toques la entrada.",
    f_b, 225, WHITE, max_w=S-90)

img = hline(img, 60, bot+22, S-60, PURPLE, w=3, gr=12)

img, b2 = txt_c(img, "No al reves.", F("impact",130),
                bot+110, WHITE, glow_col=PURPLE, glow_r=32, max_w=S-60)

img = hline(img, 60, b2+18, S-60, PURPLE, w=1, gr=6)

img, b3 = txt_c(img, "Estamos construyendo ese sistema.", F("bold",38),
                b2+70, PURPLE, glow_col=PURPLE, glow_r=10, max_w=S-100)

f_brand = F("bold",44)
t_tick = "Tickia."
ImageDraw.Draw(img).text((S//2-tw(t_tick,f_brand)//2, b3+20), t_tick, font=f_brand, fill=BLUE)
f_cta = F("regular",30)
t_cta = "Entra a la lista. Link en bio."
ImageDraw.Draw(img).text((S//2-tw(t_cta,f_cta)//2, b3+76), t_cta, font=f_cta, fill=GRAY)

img.save(os.path.join(OUT, "c2_s05_cierre.png")); print("OK c2_s05_cierre.png")

print("--- CARRUSEL 2 completo (6 slides) ---")
print("DONE: 13 slides generados.")
