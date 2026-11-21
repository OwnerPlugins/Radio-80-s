"""Generate RadioM 2.0 skin graphics (original artwork) for hd/fhd/wqhd."""
import math
import random
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
PINK = (255, 79, 176)
PURPLE = (124, 58, 237)
CYAN = (56, 220, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def vgradient(w, h, stops):
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        t = y / float(h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                col = lerp(c0, c1, (t - p0) / (p1 - p0 or 1))
                break
        for x in range(w):
            px[x, y] = col
    return img


def synthwave(W, H, darken=0.55, sun=True):
    s = W / 1920.0
    horizon = int(H * 0.63)
    img = vgradient(W, H, [(0, (8, 3, 22)), (0.45, (38, 9, 60)),
                           (0.63, (92, 20, 96)), (0.64, (14, 4, 30)),
                           (1, (6, 2, 14))])
    d = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(80)
    for _ in range(int(260 * s * s) + 60):
        x, y = rnd.randrange(W), rnd.randrange(int(horizon * 0.85))
        a = rnd.randrange(60, 200)
        r = rnd.choice([1, 1, 1, 2]) * max(1, int(s))
        d.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, a))
    if sun:
        # sun with stripes
        R = int(250 * s)
        cx, cy = int(W * 0.68), horizon - int(40 * s)
        sunimg = Image.new('RGBA', (2 * R, 2 * R), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sunimg)
        for y in range(2 * R):
            col = lerp((255, 214, 90), (255, 60, 160), y / (2.0 * R))
            sd.line([(0, y), (2 * R, y)], fill=col + (255,))
        mask = Image.new('L', (2 * R, 2 * R), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=255)
        # stripes on the lower half
        y = int(R * 0.5)
        gap = int(5 * s)
        while y < 2 * R:
            md.rectangle((0, y, 2 * R, y + gap), fill=0)
            y += gap + int(22 * s)
            gap += max(1, int(3 * s))
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse(
            (cx - R - 60 * s,
             cy - R - 60 * s,
             cx + R + 60 * s,
             cy + R + 60 * s),
            fill=(
                255,
                70,
                160,
                90))
        glow = glow.filter(ImageFilter.GaussianBlur(60 * s))
        img.paste(glow, (0, 0), glow)
        img.paste(sunimg, (cx - R, cy - R), mask)
        # cut the sun at the horizon
        d = ImageDraw.Draw(img, 'RGBA')
        d.rectangle((0, horizon, W, H), fill=(14, 4, 30, 255))
        # mountains
        pts = [(0, horizon)]
        x = 0
        rnd2 = random.Random(7)
        while x < W:
            x += rnd2.randint(int(50 * s), int(110 * s))
            pts.append((x, horizon - rnd2.randint(int(10 * s), int(90 * s))))
        pts.append((W, horizon))
        d.polygon(pts, fill=(22, 6, 44, 255))
    # perspective grid
    grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    vx = W // 2
    for i in range(-24, 25):
        x_bottom = vx + i * int(170 * s)
        g.line([(vx + i * int(10 * s), horizon), (x_bottom, H)],
               fill=PINK + (150,), width=max(1, int(2 * s)))
    k = 0.0
    while True:
        k += 1
        y = horizon + int((H - horizon) * (k / 14.0) ** 2.2)
        if y > H:
            break
        g.line([(0, y), (W, y)], fill=PINK + (150,), width=max(1, int(2 * s)))
    grid_glow = grid.filter(ImageFilter.GaussianBlur(4 * s))
    img.paste(grid_glow, (0, 0), grid_glow)
    img.paste(grid, (0, 0), grid)
    # horizon glow line
    d = ImageDraw.Draw(img, 'RGBA')
    d.line([(0, horizon), (W, horizon)], fill=(
        255, 140, 220, 255), width=max(1, int(3 * s)))
    # darken for readability
    dark = Image.new('RGB', (W, H), (6, 2, 14))
    return Image.blend(img, dark, darken)


def rounded_panel(w, h, r, fill, border=None, bw=2):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill,
                        outline=border, width=bw if border else 0)
    return img


def hgradient_bar(w, h, c0, c1, r, alpha=255):
    bar = Image.new('RGBA', (w, h))
    px = bar.load()
    for x in range(w):
        col = lerp(c0, c1, x / float(max(1, w - 1)))
        for y in range(h):
            px[x, y] = col + (alpha,)
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(bar, (0, 0), mask)
    return out


def icon_star(n):
    img = Image.new('RGBA', (n * 4, n * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = n * 2
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = n * 1.9 if i % 2 == 0 else n * 0.8
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=(255, 205, 70, 255))
    return img.resize((n, n), Image.LANCZOS)


def icon_radio(n):
    S = n * 4
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S // 2
    w = max(4, S // 14)
    d.ellipse((c - S * 0.09, c - S * 0.09, c + S *
              0.09, c + S * 0.09), fill=PINK + (255,))
    for r in (0.24, 0.40):
        box = (c - S * r, c - S * r, c + S * r, c + S * r)
        d.arc(box, 135, 225, fill=(190, 160, 240, 255), width=w)
        d.arc(box, -45, 45, fill=(190, 160, 240, 255), width=w)
    return img.resize((n, n), Image.LANCZOS)


def icon_play(n):
    S = n * 4
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bw = S // 7
    heights = [0.55, 0.9, 0.4, 0.75]
    for i, hgt in enumerate(heights):
        x = int(S * 0.12) + i * int(bw * 1.45)
        d.rounded_rectangle((x, S * (0.9 - hgt * 0.8), x + bw, S * 0.9),
                            bw // 3, fill=lerp(PINK, CYAN, i / 3.0) + (255,))
    return img.resize((n, n), Image.LANCZOS)


def title_logo(w, h, s):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    font = ImageFont.truetype(BOLD, int(62 * s))
    small = ImageFont.truetype(BOLD, int(20 * s))
    text = 'RADIO M'
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((int(8 * s), int(2 * s)), text, font=font, fill=PINK + (255,))
    glow = layer.filter(ImageFilter.GaussianBlur(8 * s))
    img.alpha_composite(glow)
    img.alpha_composite(glow)
    # chrome gradient text
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).text(
        (int(8 * s), int(2 * s)), text, font=font, fill=255)
    grad = vgradient(w, h, [(0, (255, 240, 255)), (0.45, (255,
                     170, 230)), (0.5, (255, 79, 176)), (1, (160, 60, 255))])
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.text((int(12 * s),
            int(76 * s)),
           'W E B   R A D I O   ·   S I N C E   1 9 8 0',
           font=small,
           fill=CYAN + (230,
                        ))
    return img


def shadow(w, h, pad, s):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad + int(10 * s), w - pad, h -
                        pad + int(10 * s)), int(20 * s), fill=(0, 0, 0, 200))
    img = img.filter(ImageFilter.GaussianBlur(pad / 2.5))
    d = ImageDraw.Draw(img)
    # neon rim
    d.rounded_rectangle((pad - 3 * s,
                         pad - 3 * s,
                         w - pad + 3 * s,
                         h - pad + 3 * s),
                        int(18 * s),
                        outline=PINK + (170,
                                        ),
                        width=max(2,
                                  int(3 * s)))
    return img


def vignette(W, H):
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    px = img.load()
    for y in range(H):
        t = y / float(H)
        a = 0
        if t > 0.80:
            a = int(230 * min(1, (t - 0.80) / 0.12))
        elif t < 0.17:
            a = int(150 * (1 - t / 0.17))
        for x in range(W):
            px[x, y] = (6, 2, 14, a)
    return img


def button(color, n):
    img = Image.new('RGBA', (n * 4, n * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, n * 4 - 5, n * 4 - 5), n, fill=color + (255,))
    return img.resize((n, n), Image.LANCZOS)


def pill(w, h, s, text):
    img = rounded_panel(w, h, h // 2, (255, 255, 255, 40),
                        (255, 255, 255, 120), max(1, int(2 * s)))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(BOLD, int(19 * s))
    tw = d.textlength(text, font=font)
    d.text(((w - tw) / 2, (h - 19 * s) / 2 - 2 * s),
           text, font=font, fill=(255, 255, 255, 230))
    return img


def icon_genre(n, top):
    S = n * 4
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = (255, 200, 70, 255) if top else (190, 160, 240, 255)
    w = S // 10
    # two beamed notes
    d.ellipse((S * 0.12, S * 0.62, S * 0.42, S * 0.86), fill=col)
    d.ellipse((S * 0.55, S * 0.52, S * 0.85, S * 0.76), fill=col)
    d.rectangle((S * 0.36, S * 0.18, S * 0.36 + w, S * 0.74), fill=col)
    d.rectangle((S * 0.79, S * 0.08, S * 0.79 + w, S * 0.64), fill=col)
    d.polygon([(S * 0.36, S * 0.18), (S * 0.79 + w, S * 0.08),
              (S * 0.79 + w, S * 0.22), (S * 0.36, S * 0.32)], fill=col)
    return img.resize((n, n), Image.LANCZOS)


def qr_card(url, n):
    import qrcode
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        border=2,
        box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    code = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    card = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    mask = Image.new('L', (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, n - 1, n - 1), n // 14, fill=255)
    white = Image.new('RGBA', (n, n), (255, 255, 255, 255))
    card.paste(white, (0, 0), mask)
    inner = int(n * 0.90)
    code = code.resize((inner, inner), Image.NEAREST)
    card.paste(code, ((n - inner) // 2, (n - inner) // 2))
    return card


def build(res, outdir):
    W, H = {'hd': (1280, 720), 'fhd': (1920, 1080), 'wqhd': (2560, 1440)}[res]
    s = W / 1920.0

    def S(v):
        return int(round(v * s))
    synthwave(W, H, 0.42).save(outdir + '/bg_main.jpg', quality=90)
    synthwave(
        W,
        H,
        0.70,
        sun=False).filter(
        ImageFilter.GaussianBlur(
            S(6))).save(
                outdir +
                '/bg_player.jpg',
        quality=90)
    rounded_panel(S(560), S(840), S(26), (12, 4, 28, 200), PINK +
                  (110,), max(1, S(2))).save(outdir + '/panel_left.png')
    rounded_panel(S(1180), S(840), S(26), (12, 4, 28, 200), PINK +
                  (110,), max(1, S(2))).save(outdir + '/panel_right.png')
    hgradient_bar(
        S(1120), S(86), (255, 79, 176), (124, 58, 237), S(16), 215).save(
        outdir + '/sel.png')
    hgradient_bar(
        S(1040), S(10), (255, 79, 176), (255, 190, 80), S(5)).save(
        outdir + '/progress.png')
    rounded_panel(
        S(1040), S(10), S(5), (255, 255, 255, 50)).save(
        outdir + '/progress_bg.png')
    icon_star(S(44)).save(outdir + '/ic_fav.png')
    icon_radio(S(44)).save(outdir + '/ic_radio.png')
    icon_play(S(44)).save(outdir + '/ic_play.png')
    title_logo(S(560), S(110), s).save(outdir + '/title.png')
    shadow(S(640), S(640), S(40), s).save(outdir + '/cover_shadow.png')
    shadow(S(460), S(460), S(30), s).save(outdir + '/logo_shadow.png')
    vignette(W, H).save(outdir + '/vignette.png')
    for name, col in (('red', (230, 40, 60)), ('green', (40, 200, 90)),
                      ('yellow', (240, 200, 40)), ('blue', (50, 110, 240))):
        button(col, S(30)).save(outdir + '/btn_%s.png' % name)
    pill(S(90), S(34), s, 'MENU').save(outdir + '/btn_menu.png')
    pill(S(90), S(34), s, 'INFO').save(outdir + '/btn_info.png')
    pill(S(90), S(34), s, '0').save(outdir + '/btn_0.png')
    icon_genre(S(44), False).save(outdir + '/ic_genre.png')
    icon_genre(S(44), True).save(outdir + '/ic_genre_top.png')
    rounded_panel(S(1100), S(840), S(26), (12, 4, 28, 200), PINK +
                  (110,), max(1, S(2))).save(outdir + '/panel_about.png')
    rounded_panel(S(660), S(840), S(26), (12, 4, 28, 210), CYAN +
                  (110,), max(1, S(2))).save(outdir + '/panel_qr.png')
    qr_card(
        'https://www.paypal.com/paypalme/belfagor2005',
        S(290)).save(
        outdir +
        '/qr_paypal.png')
    qr_card('https://ko-fi.com/lululla', S(290)).save(outdir + '/qr_kofi.png')
    pill(S(90), S(34), s, '◀ ▶').save(outdir + '/btn_lr.png')


if __name__ == '__main__':
    base = sys.argv[1]
    for res in ('hd', 'fhd', 'wqhd'):
        build(res, '%s/%s' % (base, res))
        print('done', res)
