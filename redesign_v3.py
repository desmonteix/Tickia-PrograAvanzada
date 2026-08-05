# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, sys

sys.stdout.reconfigure(encoding="utf-8")

FONTS = r"C:\Users\matid\.claude\plugins\cache\anthropic-agent-skills\document-skills\b29e7cf65e5c\skills\canvas-design\canvas-fonts"
OUT   = r"C:\Users\matid\OneDrive\Documentos\TickerTrader\Resultados\Diseno"

# ── SKINS ──────────────────────────────────────────────────────────────────
SKINS = {
    "default": {
        "name":      "Tickia Default",
        "bg_a":      (10, 10, 10),
        "bg_b":      (22, 8, 45),
        "accent":    (139, 92, 246),   # purple
        "energy":    (249, 115, 22),   # electric orange
        "safe":      (16, 185, 129),   # green
        "danger":    (239, 68, 68),    # red
        "label_col": (249, 115, 22),   # orange labels
        "hero_col":  (255, 255, 255),
        "sub_col":   (156, 163, 175),
        "data_col":  (249, 115, 22),   # orange for numbers/money
    }
}

T = SKINS["default"]

# ── HELPERS ────────────────────────────────────────────────────────────────
_sc = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

def fnt(name, size):
    for n in [name]:
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise FileNotFoundError(name)

def F(kind, size):
    if kind == "impact":
        for n in ["BigShoulders-Bold.ttf","Outfit-Bold.ttf"]:
            try: return fnt(n, size)
            except: pass
    if kind == "bold":
        for n in ["Outfit-Bold.ttf","BricolageGrotesque-Regular.ttf"]:
            try: return fnt(n, size)
            except: pass
    if kind == "regular":
        for n in ["Outfit-Regular.ttf","BricolageGrotesque-Regular.ttf"]:
            try: return fnt(n, size)
            except: pass
    if kind == "mono":
        for n in ["GeistMono-Regular.ttf","JetBrainsMono-Regular.ttf"]:
            try: return fnt(n, size)
            except: pass
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
    return lines or [""]

def grad(w, h, top, bot):
    strip = Image.new("RGBA", (1, h))
    strip.putdata([tuple(int(top[i]+(bot[i]-top[i])*y/max(h-1,1)) for i in range(3))+(255,) for y in range(h)])
    return strip.resize((w, h), Image.NEAREST)

def glow_layer(img, draw_fn, blur_r, alpha_mul=1.0):
    gl = Image.new("RGBA", img.size, (0,0,0,0))
    draw_fn(gl)
    gl = gl.filter(ImageFilter.GaussianBlur(blur_r))
    if alpha_mul != 1.0:
        r,g,b,a = gl.split()
        import PIL.ImageEnhance as E
        a = E.Brightness(a).enhance(alpha_mul)
        gl = Image.merge("RGBA", (r,g,b,a))
    return Image.alpha_composite(img, gl)

def txt_c(img, text, font, cy, color, glow_col=None, glow_r=22, max_w=None):
    W = img.width
    mw = max_w or W-80
    lines = wrap(text, font, mw)
    lh = th("Ag", font)
    sp = int(lh * 0.22)
    total = len(lines)*lh + (len(lines)-1)*sp
    y = cy - total//2
    for line in lines:
        x = W//2 - tw(line, font)//2
        if glow_col:
            def _d(gl, x=x, y=y, line=line, glow_col=glow_col, font=font):
                ImageDraw.Draw(gl).text((x, y), line, font=font, fill=glow_col+(150,))
            img = glow_layer(img, _d, glow_r)
        ImageDraw.Draw(img).text((x, y), line, font=font, fill=color)
        y += lh+sp
    return img, cy + total//2

def txt_l(img, text, font, x, y, color):
    ImageDraw.Draw(img).text((x, y), text, font=font, fill=color)
    return img

def hline(img, x1, y, x2, col, w=2, gr=0):
    if gr:
        def _d(gl):
            ImageDraw.Draw(gl).rectangle([x1, y-w*2, x2, y+w*2], fill=col+(100,))
        img = glow_layer(img, _d, gr)
    ImageDraw.Draw(img).rectangle([x1, y, x2, y+w], fill=col)
    return img

def progress(img, frac, col):
    ImageDraw.Draw(img).rectangle([0, 0, img.width, 4], fill=(20,20,20))
    ImageDraw.Draw(img).rectangle([0, 0, int(img.width*frac), 4], fill=col)

def slide_num(img, n, total):
    f = F("mono", 22)
    ImageDraw.Draw(img).text((44, img.height-52), f"{n:02d} / {total:02d}", font=f, fill=T["sub_col"])

def logo(img, col=None, y=None):
    col = col or T["sub_col"]
    f = F("bold", 28)
    W, H = img.size
    y = y or H-46
    t = "Tickia"
    ImageDraw.Draw(img).text((W//2-tw(t,f)//2, y), t, font=f, fill=col)

def corner_bracket(img, col):
    W = img.width
    d = ImageDraw.Draw(img)
    d.rectangle([W-50, 22, W-20, 24], fill=col)
    d.rectangle([W-22, 22, W-20, 52], fill=col)

def ambient_circle(img, cx, cy, r, col, alpha=22, blur=140):
    def _d(gl): ImageDraw.Draw(gl).ellipse([cx-r, cy-r, cx+r, cy+r], fill=col+(alpha,))
    return glow_layer(img, _d, blur)

def color_band(img, y1, y2, col, alpha=255):
    block = Image.new("RGBA", (img.width, y2-y1), col+(alpha,))
    out = img.copy()
    out.paste(block, (0, y1))
    return out

def deco_circle(img, cx, cy, r, col, stroke=6, alpha=60):
    gl = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(gl).ellipse([cx-r, cy-r, cx+r, cy+r], outline=col+(alpha,), width=stroke)
    gl = gl.filter(ImageFilter.GaussianBlur(4))
    return Image.alpha_composite(img, gl)

def pill_tag(img, text, cx, y, bg, fg, border=None):
    f = F("mono", 22)
    tw_ = tw(text, f); th_ = th(text, f)
    x = cx - (tw_+28)//2
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x, y, x+tw_+28, y+th_+16], radius=20, fill=bg,
                         outline=border or bg, width=1)
    d.text((x+14, y+8), text, font=f, fill=fg)

def lock_icon(img, cx, cy, sz=90, col=None):
    col = col or T["safe"]
    gl_img = Image.new("RGBA", img.size, (0,0,0,0))
    gd = ImageDraw.Draw(gl_img)
    bx,by = cx-sz//2, cy
    bw,bh = sz, int(sz*0.65)
    gd.rounded_rectangle([bx,by,bx+bw,by+bh], radius=8, fill=col+(100,))
    sw = int(sz*0.38); sx = cx-sw//2
    gd.arc([sx, cy-sz//2, sx+sw, cy+int(sz*0.25)], 180, 0, fill=col+(100,), width=int(sz*0.14))
    gl_img = gl_img.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, gl_img)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx,by,bx+bw,by+bh], radius=8, fill=col)
    d.arc([sx, cy-sz//2, sx+sw, cy+int(sz*0.25)], 180, 0, fill=col, width=int(sz*0.14))
    d.ellipse([cx-7, by+12, cx+7, by+28], fill=(10,10,10))
    return img

def cta_button(img, text, cy, col):
    f = F("bold", 36)
    W = img.width
    tw_ = tw(text, f); th_ = th(text, f)
    bx = W//2 - (tw_+60)//2
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([bx, cy, bx+tw_+60, cy+th_+22], radius=14, fill=col)
    d.text((bx+30, cy+11), text, font=f, fill=(10,10,10))

# ══════════════════════════════════════════════════════════════════
# CARRUSEL 1 — COMPRADOR (7 slides) — SKIN DEFAULT
# ══════════════════════════════════════════════════════════════════
S = 1080

# ── S1: PORTADA ── archetype: GLOW + deco circles
img = grad(S, S, T["bg_a"], T["bg_b"])
img = ambient_circle(img, S+100, -100, 600, T["accent"], alpha=30, blur=160)
img = deco_circle(img, S-80, -80, 320, T["accent"], stroke=3, alpha=50)
img = deco_circle(img, S-80, -80, 220, T["energy"], stroke=2, alpha=35)
progress(img, 1/7, T["accent"])
corner_bracket(img, T["energy"])

txt_l(img, "CARRUSEL 01 — COMPRADOR", F("mono",21), 60, 52, T["energy"])

img, _ = txt_c(img,
    "Asi se ve comprar una entrada en reventa en Lima hoy.",
    F("impact", 96), S//2-30, T["hero_col"], glow_col=T["accent"], glow_r=16, max_w=S-80)

img = hline(img, 60, S//2+80, S-60, T["energy"], w=3, gr=10)

img, _ = txt_c(img, "(No es bonito.)", F("regular", 30), S//2+122, T["sub_col"])

img, _ = txt_c(img, "Desliza  ->", F("regular", 24), S-75, T["sub_col"])
logo(img)
img.save(os.path.join(OUT, "carrusel4_portada.png")); print("OK carrusel4_portada.png")

# ── S2: VENDEDOR FACEBOOK ── archetype: GLOW
img = grad(S, S, T["bg_a"], (20, 10, 8))
img = ambient_circle(img, -100, S//2, 400, T["energy"], alpha=14, blur=120)
img = deco_circle(img, S+60, S//2+100, 350, T["energy"], stroke=2, alpha=30)
progress(img, 2/7, T["accent"])
corner_bracket(img, T["accent"])
slide_num(img, 2, 7)

txt_l(img, "// ESCENA 01", F("mono",22), 60, 52, T["energy"])

img, bot = txt_c(img, "Encuentras al vendedor en un grupo de Facebook.",
                 F("bold", 60), S//2-70, T["hero_col"], max_w=S-100)

img = hline(img, 60, bot+22, S-60, (45,25,10), w=1, gr=0)

f_s = F("regular", 34)
for i, (t, c) in enumerate([
    ("Parece confiable.", T["sub_col"]),
    ("Tiene fotos. Comentarios. Historia.", T["sub_col"]),
]):
    img, _ = txt_c(img, t, f_s, bot+55+i*52, c)

pill_tag(img, "RIESGO EN CAMINO", S//2, S-75, (40,22,5), T["energy"], border=T["energy"])
logo(img)
img.save(os.path.join(OUT, "c1_s02_vendedor_facebook.png")); print("OK c1_s02")

# ── S3: LE TRANSFIERES ── archetype: SPLIT (dark top / orange bottom)
img = grad(S, S, T["bg_a"], (18,10,5))
# Orange band bottom 44%
split_y = int(S * 0.56)
img = color_band(img, split_y, S, T["energy"])
progress(img, 3/7, T["energy"])
corner_bracket(img, T["energy"])
slide_num(img, 3, 7)

txt_l(img, "// ESCENA 02", F("mono",22), 60, 52, T["energy"])

f_b = F("bold", 58)
img, _ = txt_c(img, "Le transfieres.", f_b, 200, T["hero_col"])

img = hline(img, 60, 265, S-60, (45,25,5), w=1, gr=0)

# Hero amount: white on orange
img, _ = txt_c(img, "S/. 500", F("impact", 160), split_y + (S-split_y)//2 - 30,
               (10,10,10), glow_col=(10,10,10), glow_r=5)

# "Y esperas." on dark zone, near split
f_r = F("regular", 38)
img, _ = txt_c(img, "Y esperas.", f_r, split_y - 42, T["sub_col"])

logo(img, col=(10,10,10))
img.save(os.path.join(OUT, "c1_s03_transferiste.png")); print("OK c1_s03")

# ── S4: PDF NOMBRE OTRO ── archetype: GLOW + panel
img = grad(S, S, T["bg_a"], (28,6,6))
img = ambient_circle(img, S//2, S//2, 420, T["danger"], alpha=16, blur=120)
progress(img, 4/7, T["danger"])
corner_bracket(img, T["danger"])
slide_num(img, 4, 7)

txt_l(img, "// ESCENA 03", F("mono",22), 60, 52, T["danger"])

f_g = F("regular", 36)
img, bot = txt_c(img, "A veces llega el PDF.", F("bold",50), 190, T["sub_col"])
img, bot = txt_c(img, "A veces no llega nadie.", F("bold",50), bot+14, T["sub_col"])

# Red panel
px1,px2,py1,py2 = 50, S-50, bot+30, bot+250
def _panel(gl): ImageDraw.Draw(gl).rounded_rectangle([px1,py1,px2,py2], radius=14, outline=T["danger"]+(160,), width=3)
img = glow_layer(img, _panel, 10)
ImageDraw.Draw(img).rounded_rectangle([px1,py1,px2,py2], radius=14, fill=(55,8,8), outline=T["danger"], width=1)

f_r = F("bold", 40)
cy_w = py1+28
for line in ["A veces el PDF llega —", "y tiene el nombre de", "otra persona."]:
    img, _ = txt_c(img, line, f_r, cy_w, T["danger"])
    cy_w += th(line, f_r)+16

img = hline(img, 60, py2+30, S-60, (60,12,12), w=1, gr=0)
img, _ = txt_c(img, "Tu dinero ya salio. La entrada, no.", F("regular",34), py2+66, T["sub_col"])

logo(img)
img.save(os.path.join(OUT, "c1_s04_pdf_nombre_otro.png")); print("OK c1_s04")

# ── S5: LUZ ROJA ── archetype: IMPACT (full color fill)
img = Image.new("RGBA", (S,S), (180, 12, 12, 255))
# Darker vignette on edges
vig = grad(S, S, (140,8,8), (200,20,20))
mask = Image.new("L", (S,S), 0)
ImageDraw.Draw(mask).ellipse([S//2-600, S//2-600, S//2+600, S//2+600], fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(200))
img.paste(vig, mask=mask)
progress(img, 5/7, (255,80,80))
slide_num(img, 5, 7)

txt_l(img, "// EL PEOR ESCENARIO", F("mono",22), 60, 52, (255,120,120))
img, _ = txt_c(img, "Llegas a la puerta.", F("bold",44), 155, (255,200,200))

img, _ = txt_c(img, "LUZ", F("impact",200), S//2-80, (255,255,255), glow_col=(255,255,255), glow_r=30)
img, _ = txt_c(img, "ROJA.", F("impact",200), S//2+110, (255,255,255), glow_col=(255,255,255), glow_r=30)

ImageDraw.Draw(img).rectangle([0, S-130, S, S], fill=(120,5,5))
img, _ = txt_c(img, "Alguien mas ya entro con ese QR.", F("regular",36), S-78, (255,255,255))

logo(img, col=(255,160,160))
img.save(os.path.join(OUT, "c1_s05_luz_roja.png")); print("OK c1_s05")

# ── S6: MERCADO SIN GARANTIA ── archetype: GLOW + big text
img = grad(S, S, T["bg_a"], (12,8,28))
img = ambient_circle(img, S//2, S//2+80, 450, T["accent"], alpha=22, blur=140)
img = deco_circle(img, -80, S+80, 380, T["accent"], stroke=2, alpha=30)
progress(img, 6/7, T["accent"])
corner_bracket(img, T["accent"])
slide_num(img, 6, 7)

txt_l(img, "// LA REALIDAD", F("mono",22), 60, 52, T["accent"])

f_b = F("bold", 46)
img, bot = txt_c(img, "Esto le pasa a cientos de personas cada fin de semana en Lima.",
                 f_b, 250, T["hero_col"], max_w=S-100)

img = hline(img, 60, bot+22, S-60, T["accent"], w=3, gr=12)

img, _ = txt_c(img, "un mercado sin garantia.", F("impact", 100),
               S//2+130, T["accent"], glow_col=T["accent"], glow_r=28, max_w=S-60)

img = hline(img, 60, S-115, S-60, T["accent"], w=1, gr=4)
img, _ = txt_c(img, "Hasta ahora.", F("regular",34), S-88, T["sub_col"])

logo(img)
img.save(os.path.join(OUT, "c1_s06_mercado_sin_garantia.png")); print("OK c1_s06")

# ── S7: CIERRE ── archetype: SAFE
img = grad(S, S, T["bg_a"], (5,22,15))
img = ambient_circle(img, S//2, S//2, 400, T["safe"], alpha=20, blur=140)
progress(img, 7/7, T["safe"])

img = lock_icon(img, S//2, 140, sz=100, col=T["safe"])

img, bot = txt_c(img,
    "Existe una forma en que tu dinero no le llegue al vendedor hasta que la entrada este verificada a tu nombre.",
    F("bold", 44), S//2+20, T["hero_col"], max_w=S-90)

img = hline(img, 80, bot+24, S-80, T["safe"], w=2, gr=8)

img, bot2 = txt_c(img, "Todavia no abrimos.", F("regular",30), bot+58, T["sub_col"])

cta_button(img, "Entra a la lista  ->", bot2+30, T["safe"])
logo(img, col=(59,130,246))
img.save(os.path.join(OUT, "carrusel4_cierre.png")); print("OK carrusel4_cierre.png")


# ══════════════════════════════════════════════════════════════════
# CARRUSEL 2 — VENDEDOR (6 slides)
# ══════════════════════════════════════════════════════════════════

# ── C2 S1: PORTADA VENDEDOR ──
img = grad(S, S, T["bg_a"], T["bg_b"])
img = ambient_circle(img, -100, S+100, 500, T["accent"], alpha=25, blur=150)
img = deco_circle(img, S+60, -60, 320, T["energy"], stroke=3, alpha=40)
# Left orange bar
gl = Image.new("RGBA", img.size, (0,0,0,0))
ImageDraw.Draw(gl).rectangle([0,0,4,S], fill=T["energy"]+(200,))
img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(10)))
ImageDraw.Draw(img).rectangle([0,0,3,S], fill=T["energy"])
progress(img, 1/6, T["accent"])
corner_bracket(img, T["energy"])

txt_l(img, "CARRUSEL 02 — VENDEDOR", F("mono",21), 60, 52, T["energy"])

img, bot = txt_c(img, "Intentaste vender una entrada por redes.",
                 F("bold",62), S//2-80, T["hero_col"], max_w=S-100)

img = hline(img, 60, bot+18, S-60, T["accent"], w=3, gr=10)

img, _ = txt_c(img, "Aqui esta lo que en realidad paso.",
               F("bold",42), bot+72, T["danger"], glow_col=T["danger"], glow_r=10, max_w=S-100)

img, _ = txt_c(img, "Desliza  ->", F("regular",26), S-78, T["sub_col"])
logo(img)
img.save(os.path.join(OUT, "c2_s01_portada.png")); print("OK c2_s01")

# ── C2 S2: MENSAJES ── archetype: DATA (giant number hero)
img = grad(S, S, T["bg_a"], (20,10,5))
img = ambient_circle(img, S//2, S//2, 380, T["energy"], alpha=12, blur=120)
progress(img, 2/6, T["energy"])
corner_bracket(img, T["energy"])
slide_num(img, 2, 6)

txt_l(img, "// 10 MINUTOS DESPUES", F("mono",22), 60, 52, T["energy"])

img, bot = txt_c(img, "Publicaste en tres grupos de Facebook.",
                 F("bold",52), 200, T["hero_col"], max_w=S-90)

# Giant "15" watermark — energy color, very transparent
f_wm = F("impact", 380)
wm = "15"
wm_gl = Image.new("RGBA", img.size, (0,0,0,0))
ImageDraw.Draw(wm_gl).text((S//2-tw(wm,f_wm)//2, S//2-120), wm, font=f_wm, fill=T["energy"]+(35,))
img = Image.alpha_composite(img, wm_gl)

img = hline(img, 60, S-130, S-60, (50,28,5), w=1, gr=0)

f_s = F("regular",34)
img, _ = txt_c(img, "En 10 minutos: 15 mensajes.", f_s, S-170, T["energy"])
img, _ = txt_c(img, "Ninguno era de alguien que iba a comprar.", f_s, S-112, T["sub_col"])

logo(img)
img.save(os.path.join(OUT, "c2_s02_mensajes.png")); print("OK c2_s02")

# ── C2 S3: CHAT SPAM ── archetype: GLOW + panel
img = grad(S, S, T["bg_a"], (22,8,8))
img = ambient_circle(img, S//2, S//2, 380, T["danger"], alpha=12, blur=110)
progress(img, 3/6, T["danger"])
corner_bracket(img, T["danger"])
slide_num(img, 3, 6)

txt_l(img, "// LOS MENSAJES", F("mono",22), 60, 52, T["danger"])

def _panel(gl): ImageDraw.Draw(gl).rounded_rectangle([50,115,S-50,830], radius=16, outline=T["danger"]+(150,), width=3)
img = glow_layer(img, _panel, 10)
ImageDraw.Draw(img).rounded_rectangle([50,115,S-50,830], radius=16, fill=(20,8,8), outline=T["danger"], width=1)

chat = [
    ("Sigue disponible?",             T["sub_col"]),
    ("Sigue disponible? [leido]",     T["sub_col"]),
    ("Te doy 200 menos, me conviene?",T["sub_col"]),
    ("Cuando puedes renominar?",      T["sub_col"]),
    ("Ya te mande el comprobante.",   T["hero_col"]),
    ("<- nunca llego.",               T["danger"]),
]
f_ch = F("mono", 28)
cy_c = 148
for line, col in chat:
    txt_l(img, line, f_ch, 82, cy_c, col)
    cy_c += th(line, f_ch)+26

logo(img)
img.save(os.path.join(OUT, "c2_s03_chat_spam.png")); print("OK c2_s03")

# ── C2 S4: DESAPARECIO ── archetype: IMPACT (full purple)
img = grad(S, S, (12,8,30), (25,12,60))
img = ambient_circle(img, S//2, S//2, 500, T["accent"], alpha=30, blur=150)
img = deco_circle(img, S//2, S//2, 460, T["accent"], stroke=2, alpha=25)
img = deco_circle(img, S//2, S//2, 350, T["accent"], stroke=1, alpha=20)
progress(img, 4/6, T["accent"])
slide_num(img, 4, 6)

txt_l(img, "// EL RIESGO", F("mono",22), 60, 52, T["accent"])

f_b = F("bold", 44)
img, bot = txt_c(img, "Decidiste arriesgar. Renominaste la entrada.", f_b, 220, (180,160,220), max_w=S-100)
img = hline(img, 80, bot+16, S-80, (60,40,100), w=1, gr=0)

f_s = F("regular",34)
img, _ = txt_c(img, "El comprador leyo tu mensaje.", f_s, bot+50, T["sub_col"])

img = hline(img, 60, S//2+50, S-60, T["accent"], w=3, gr=14)

img, _ = txt_c(img, "Y no volviste a saber de el.", F("impact",110),
               S-180, T["hero_col"], glow_col=T["accent"], glow_r=24, max_w=S-60)

logo(img)
img.save(os.path.join(OUT, "c2_s04_desaparecio.png")); print("OK c2_s04")

# ── C2 S5: CONSECUENCIAS ── archetype: SPLIT (dark / red bottom)
img = grad(S, S, T["bg_a"], (28,6,6))
split_y = int(S * 0.52)
img = color_band(img, split_y, S, T["danger"])
progress(img, 5/6, T["danger"])
corner_bracket(img, T["danger"])
slide_num(img, 5, 6)

txt_l(img, "// EL RESULTADO", F("mono",22), 60, 52, T["danger"])

f_b = F("bold", 52)
img, bot = txt_c(img, "Ahora tienes:", f_b, 200, T["hero_col"])

items = [
    "— La entrada a nombre de alguien que no existe.",
    "— 0 soles recibidos.",
    "— El concierto en 24 horas.",
]
f_list = F("mono", 28)
cy_l = bot+20
for it in items:
    txt_l(img, it, f_list, 70, cy_l, T["sub_col"])
    cy_l += th(it, f_list)+20

img = hline(img, 60, split_y-4, S-60, (255,100,100), w=2, gr=4)

# White big text on red
img, _ = txt_c(img, "Y empiezas de cero.", F("impact",100),
               split_y + (S-split_y)//2, (10,10,10))

logo(img, col=(10,10,10))
img.save(os.path.join(OUT, "c2_s05_consecuencias.png")); print("OK c2_s05")

# ── C2 S6: CIERRE VENDEDOR ──
img = grad(S, S, T["bg_a"], (12,8,28))
img = ambient_circle(img, S//2, S//2+50, 420, T["accent"], alpha=25, blur=140)
progress(img, 6/6, T["accent"])

f_b = F("bold", 46)
img, bot = txt_c(img, "El dinero del comprador deberia estar retenido antes de que toques la entrada.",
                 f_b, 250, T["hero_col"], max_w=S-90)

img = hline(img, 60, bot+18, S-60, T["accent"], w=3, gr=12)

img, bot2 = txt_c(img, "No al reves.", F("impact",130), bot+110, T["hero_col"],
                  glow_col=T["accent"], glow_r=32, max_w=S-60)

img = hline(img, 60, bot2+14, S-60, T["accent"], w=1, gr=5)

img, bot3 = txt_c(img, "Estamos construyendo ese sistema.", F("bold",38), bot2+72,
                  T["accent"], glow_col=T["accent"], glow_r=10, max_w=S-100)

f_brand = F("bold", 44)
t = "Tickia."
ImageDraw.Draw(img).text((S//2-tw(t,f_brand)//2, bot3+16), t, font=f_brand, fill=(59,130,246))

f_cta = F("regular", 30)
t2 = "Entra a la lista. Link en bio."
ImageDraw.Draw(img).text((S//2-tw(t2,f_cta)//2, bot3+72), t2, font=f_cta, fill=T["sub_col"])

img.save(os.path.join(OUT, "c2_s06_cierre.png")); print("OK c2_s06")


# ══════════════════════════════════════════════════════════════════
# STORIES 1080×1920
# ══════════════════════════════════════════════════════════════════
SW, SH = 1080, 1920

# ── STORY 6: SEGURIDAD ── archetype: IMPACT red
img = grad(SW, SH, (12,5,5), (30,8,8))
# Color band bottom 35%
img = color_band(img, int(SH*0.65), SH, (160,10,10))
img = ambient_circle(img, SW//2, int(SH*0.38), 600, T["danger"], alpha=28, blur=160)
# Left bar
gl = Image.new("RGBA", img.size, (0,0,0,0))
ImageDraw.Draw(gl).rectangle([0,0,4,SH], fill=T["danger"]+(180,))
img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(10)))
ImageDraw.Draw(img).rectangle([0,0,3,SH], fill=T["danger"])

f_top = F("mono", 26)
t_top = "Esto le pasa a alguien en Lima cada semana."
txt_l(img, t_top, f_top, SW//2-tw(t_top,f_top)//2, 200, (200,120,120))
img = hline(img, 60, 258, SW-60, (80,20,20), w=1, gr=0)

img, _ = txt_c(img, "TRANSFERISTE.", F("impact",118), int(SH*0.3), T["hero_col"],
               glow_col=(255,80,80), glow_r=20, max_w=SW-60)
img, _ = txt_c(img, "EL VENDEDOR", F("impact",118), int(SH*0.38), T["hero_col"],
               glow_col=(255,80,80), glow_r=20, max_w=SW-60)
img, _ = txt_c(img, "DESAPARECIO.", F("impact",118), int(SH*0.46), (255,120,120),
               glow_col=T["danger"], glow_r=28, max_w=SW-60)
img, bot = txt_c(img, "LA ENTRADA NUNCA LLEGO.", F("impact",100), int(SH*0.535), (255,120,120),
                 glow_col=T["danger"], glow_r=22, max_w=SW-60)

img = hline(img, 60, bot+24, SW-60, (100,20,20), w=1, gr=0)

# Orange amount panel ON the red band — contrast moment
def _p(gl): ImageDraw.Draw(gl).rounded_rectangle([70,bot+44,SW-70,bot+164], radius=14, fill=T["energy"]+(200,))
img = glow_layer(img, _p, 20)
ImageDraw.Draw(img).rounded_rectangle([70,bot+44,SW-70,bot+164], radius=14, fill=T["energy"])
f_amt = F("bold",58)
t_amt = "500 soles. Esfumados."
ImageDraw.Draw(img).text((SW//2-tw(t_amt,f_amt)//2, bot+62), t_amt, font=f_amt, fill=(10,10,10))

img = hline(img, 60, bot+184, SW-60, (80,20,20), w=1, gr=0)

bot_msg = "Tu dinero no deberia llegar al vendedor hasta que la entrada este a tu nombre."
img, bot2 = txt_c(img, bot_msg, F("regular",36), bot+280, T["hero_col"], max_w=SW-90)

img = lock_icon(img, SW//2, SH-230, sz=90, col=T["safe"])
logo(img)
img.save(os.path.join(OUT, "story6_seguridad.png")); print("OK story6")

# ── STORY 7: FOMO ── archetype: GLOW purple
img = grad(SW, SH, T["bg_a"], (16,6,38))
img = ambient_circle(img, SW//2, SH//2, 600, T["accent"], alpha=30, blur=160)
img = deco_circle(img, SW+100, SH//4, 500, T["accent"], stroke=3, alpha=35)
img = deco_circle(img, -100, SH*3//4, 400, T["energy"], stroke=2, alpha=25)
# Left purple bar
gl = Image.new("RGBA", img.size, (0,0,0,0))
ImageDraw.Draw(gl).rectangle([0,0,4,SH], fill=T["accent"]+(180,))
img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(10)))
ImageDraw.Draw(img).rectangle([0,0,3,SH], fill=T["accent"])

f_lbl = F("mono",26)
t_lbl = "PREGUNTA RAPIDA:"
ImageDraw.Draw(img).text((SW//2-tw(t_lbl,f_lbl)//2, 210), t_lbl, font=f_lbl, fill=T["accent"])
img = hline(img, 80, 270, SW-80, T["accent"], w=2, gr=8)

img, bot = txt_c(img, "¿Ya esta tu amigo en la lista de Tickia?",
                 F("impact",108), SH//2-100, T["hero_col"],
                 glow_col=T["accent"], glow_r=24, max_w=SW-80)

img = hline(img, 80, bot+22, SW-80, (40,20,80), w=1, gr=0)

img, bot2 = txt_c(img, "Porque la lista ya avanza.", F("bold",44), bot+68, T["hero_col"])

img, bot3 = txt_c(img, "Tu decides si eres de los primeros o de los ultimos.",
                  F("bold",40), bot2+32, T["accent"], glow_col=T["accent"], glow_r=8, max_w=SW-90)

# Orange energy CTA button
cta_button(img, "Sin costo. Sin compromiso.", bot3+44, T["energy"])

btn_bot = bot3 + 44 + th("A", F("bold",36)) + 42
img = hline(img, 80, btn_bot+20, SW-80, T["accent"], w=1, gr=6)

f_cta = F("regular", 38)
t_cta = "Entra a la lista. Link en bio."
ImageDraw.Draw(img).text((SW//2-tw(t_cta,f_cta)//2, btn_bot+40), t_cta, font=f_cta, fill=T["hero_col"])

logo(img)
img.save(os.path.join(OUT, "story7_fomo.png")); print("OK story7")

print("DONE - 15 archivos generados.")
