#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_rain_gl — lluvia digital FQ en Pygame (versión SHOW de alto rendimiento).

Adaptación de la arquitectura de StanislavPetrovV/MATRIX-Digital-Rain (glifos
pre-renderizados + estela por buffer con alfa) a la identidad de la casa. Pygame
usa SDL2 con aceleración por hardware para el blit → miles de glifos a 60 fps.

Lo NUESTRO sobre esa base:
  * Glifos pre-renderizados una sola vez y cacheados por (carácter, color) →
    el bucle solo hace blits (el "instancing" de caracteres que pediste).
  * ~9%% de columnas caen DORADAS a velocidad φ (0.618×) deletreando Fibonacci.
  * ~7%% llevan el degradado Solana (violeta → verde menta) en la estela.
  * El resto: lluvia clásica verde fósforo con katakana + φ Φ Σ λ Ξ ₿.
  * Mensajes de la casa que se materializan en oro letra a letra y se disuelven
    (FQ CAPITAL, φ = 1.6180339887, DSR>0.95·CPCV·PBO, MEDIDA O MUERTE...).
  * Marca de agua institucional abajo: FQ CAPITAL · Fibonacci Quantum Framework.

VANIDAD DECLARADA para clips y demos — NO toca al motor, stdlib + pygame, aparte.

Uso:
    python3 tools/matrix_rain_gl.py                    # ventana 1600×900, ESC/q sale
    python3 tools/matrix_rain_gl.py --fullscreen
    python3 tools/matrix_rain_gl.py --seconds 30 --record clip_%04d.png   # grabar
    python3 tools/matrix_rain_gl.py --screenshot still.png --warmup 140    # 1 still
    python3 tools/matrix_rain_gl.py --self-test        # headless (CI, sin pantalla)
"""
import argparse
import os
import sys

# Glifos de la casa: katakana de ancho medio (firma Matrix) + símbolos FQ.
KATAKANA = [chr(0x30A1 + i) for i in range(86)]
SYMBOLS = list("0123456789φΦΣλΞπΔ∑√₿◎")
GLYPHS = KATAKANA + SYMBOLS
FIB = "1123581321345589144233377610987159725844181676510946177112865746368"
PHI_INV = 0.6180339887                                   # 1/φ: la caída dorada

KIND_GREEN, KIND_GOLD, KIND_SOL = 0, 1, 2

# Paleta (la validada por el skill dataviz): oro de marca, verde fósforo, Solana.
HEAD = {KIND_GREEN: (200, 255, 205), KIND_GOLD: (255, 244, 214),
        KIND_SOL: (233, 240, 255)}
BODY = {KIND_GREEN: (58, 214, 107), KIND_GOLD: (201, 162, 39),
        KIND_SOL: (153, 69, 255)}                         # #9945FF Solana violeta
SOL_END = (20, 245, 149)                                  # #14F195 Solana verde

MESSAGES = ("FQ CAPITAL", "FIBONACCI QUANTUM FRAMEWORK", "φ = 1.6180339887",
            "DSR > 0.95 · CPCV · PBO", "SOL · BTC · ETH", "MEDIDA O MUERTE",
            "ORDER-FLOW CONFIRMADO", "FUNDING FAVORABLE")

FONT_CANDIDATES = ("wenquanyizenheimono", "unifont", "notosanscjkjp",
                   "dejavusansmono", "freemono")


def _pick_font(pg, size):
    for name in FONT_CANDIDATES:
        path = pg.font.match_font(name)
        if path:
            try:
                return pg.font.Font(path, size), name
            except Exception:
                continue
    return pg.font.Font(None, size), "default"


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class GlyphCache(object):
    """Renderiza cada (carácter,color) UNA vez y lo cachea. El bucle solo blitea."""

    def __init__(self, font):
        self.font = font
        self._cache = {}

    def get(self, ch, color):
        key = (ch, color)
        surf = self._cache.get(key)
        if surf is None:
            surf = self.font.render(ch, True, color)
            self._cache[key] = surf
        return surf

    def __len__(self):
        return len(self._cache)


class Column(object):
    """Columna de lluvia en espacio de píxeles. Física pura (testeable headless)."""

    def __init__(self, x, cell, height, rng, kind=KIND_GREEN):
        self.x = x
        self.cell = cell
        self.rows = height // cell + 2
        self.rng = rng
        self.kind = kind
        self._fib_i = rng.randrange(len(FIB)) if kind == KIND_GOLD else 0
        base = rng.uniform(4.0, 9.0)                       # px/frame
        self.speed = base * PHI_INV if kind == KIND_GOLD else base
        self.interval = rng.randrange(2, 9)                # frames por mutación
        self.reset(rng.randrange(-height, 0))

    def reset(self, y_px=None):
        self.y = float(-self.rng.randrange(self.cell, self.rows * self.cell)
                       if y_px is None else y_px)
        self.row = int(self.y // self.cell)
        self.glyph = self._new_glyph()

    def _new_glyph(self):
        if self.kind == KIND_GOLD:                         # el oro deletrea Fibonacci
            self._fib_i = (self._fib_i + 1) % len(FIB)
            return FIB[self._fib_i]
        return self.rng.choice(GLYPHS)

    def advance(self, frame):
        """Avanza; devuelve (row_nueva|None, glifo) cuando cruza a una celda nueva."""
        self.y += self.speed
        stamped = None
        new_row = int(self.y // self.cell)
        if new_row != self.row:
            self.row = new_row
            self.glyph = self._new_glyph()
            stamped = new_row
        elif frame % self.interval == 0:                   # parpadeo en sitio
            self.glyph = self._new_glyph()
        if self.y // self.cell > self.rows:
            self.reset()
        return stamped, self.glyph

    def head_color(self):
        if self.kind == KIND_SOL:                          # degradado por profundidad
            t = max(0.0, min(1.0, (self.y % (self.cell * self.rows)) /
                             (self.cell * self.rows)))
            return _lerp(HEAD[KIND_SOL], SOL_END, t)
        return HEAD[self.kind]

    def body_color(self):
        if self.kind == KIND_SOL:
            t = max(0.0, min(1.0, (self.y % (self.cell * self.rows)) /
                             (self.cell * self.rows)))
            return _lerp(BODY[KIND_SOL], SOL_END, t)
        return BODY[self.kind]


class Message(object):
    """Mensaje de la casa: se escribe letra a letra, sostiene, se disuelve."""

    def __init__(self, text, t0, big):
        self.text = text
        self.t0 = t0
        self.big = big
        self.reveal = 0.05 * len(text)
        self.hold = 2.4
        self.fade = 0.9

    def render(self, t):
        dt = t - self.t0
        total = self.reveal + self.hold + self.fade
        if dt >= total:
            return None
        if dt < self.reveal:
            n = max(1, int(len(self.text) * dt / self.reveal))
            alpha = 255
        elif dt < self.reveal + self.hold:
            n, alpha = len(self.text), 255
        else:
            n = len(self.text)
            k = (dt - self.reveal - self.hold) / self.fade
            alpha = int(255 * (1 - k))
        return self.text[:n], alpha


def build_columns(width, cell, height, rng, gold=0.09, sol=0.07):
    cols = []
    for x in range(0, width, cell):
        r = rng.random()
        kind = KIND_GOLD if r < gold else (KIND_SOL if r < gold + sol else KIND_GREEN)
        cols.append(Column(x, cell, height, rng, kind))
    return cols


# ------------------------------------------------------------------ run -----

def run(args):
    import random
    import pygame as pg

    if args.self_test or args.screenshot or args.record:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy" if args.self_test else
                              os.environ.get("SDL_VIDEODRIVER", ""))
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["SDL_VIDEO_CENTERED"] = "1"
    pg.init()

    W, H = args.width, args.height
    flags = pg.FULLSCREEN | pg.SCALED if args.fullscreen else 0
    screen = pg.display.set_mode((W, H), flags)
    pg.display.set_caption("FQ CAPITAL · Fibonacci Quantum Framework")
    W, H = screen.get_size()
    cell = args.font
    font, fname = _pick_font(pg, cell)
    big_font, _ = _pick_font(pg, int(cell * 1.9))
    cache = GlyphCache(font)
    rng = random.Random(args.seed)

    trail = pg.Surface((W, H))
    trail.fill((0, 0, 0))
    fade = pg.Surface((W, H))                               # velo negro semitransparente
    fade.fill((0, 0, 0))
    fade.set_alpha(max(1, args.fade))                      # ↑ estela más corta

    watermark = big_font  # reutilizamos; marca de agua abajo
    wm_font, _ = _pick_font(pg, max(12, cell // 2))
    wm = wm_font.render("FQ CAPITAL   ·   FIBONACCI QUANTUM FRAMEWORK   ·   φ 1.6180339887",
                        True, (150, 122, 40))
    wm.set_alpha(70)

    cols = build_columns(W, cell, H, rng, args.gold, args.sol)
    clock = pg.time.Clock()
    msg = None
    next_msg_frame = int(args.fps * rng.choice((5, 8)))
    frame = 0
    saved = 0

    while True:
        for e in pg.event.get():
            if e.type == pg.QUIT or (e.type == pg.KEYDOWN and
                                     e.key in (pg.K_ESCAPE, pg.K_q)):
                pg.quit()
                return 0

        trail.blit(fade, (0, 0))                            # desvanece el frame previo
        for col in cols:
            stamped, glyph = col.advance(frame)
            row = col.row
            y = row * cell
            if stamped is not None and 0 <= row < H // cell + 1:
                trail.blit(cache.get(col.glyph, col.body_color()), (col.x, y))
            if 0 <= y < H:
                trail.blit(cache.get(glyph, col.head_color()), (col.x, y))

        screen.blit(trail, (0, 0))
        screen.blit(wm, (W // 2 - wm.get_width() // 2, H - wm.get_height() - 14))

        if not args.no_messages:
            if msg is None and frame >= next_msg_frame:
                msg = Message(rng.choice(MESSAGES), frame / float(args.fps),
                              big_font)
            if msg is not None:
                r = msg.render(frame / float(args.fps))
                if r is None:
                    msg = None
                    next_msg_frame = frame + int(args.fps * rng.choice((5, 8, 13)))
                else:
                    text, alpha = r
                    surf = msg.big.render(text, True, (255, 226, 150))
                    surf.set_alpha(alpha)
                    screen.blit(surf, (W // 2 - surf.get_width() // 2,
                                       H // 3 - surf.get_height() // 2))

        pg.display.flip()
        frame += 1

        if args.record and frame > args.warmup:
            pg.image.save(screen, args.record % saved)
            saved += 1
        if args.screenshot and frame >= args.warmup:
            pg.image.save(screen, args.screenshot)
            pg.quit()
            print("still -> %s (fuente=%s, glifos cacheados=%d)" %
                  (args.screenshot, fname, len(cache)))
            return 0
        if args.self_test and frame >= 30:
            assert len(cache) > 0, "no se cacheó ningún glifo"
            kinds = {c.kind for c in cols}
            assert {KIND_GREEN, KIND_GOLD, KIND_SOL} <= kinds, "faltan castas"
            gold = [c for c in cols if c.kind == KIND_GOLD][0]
            assert gold.speed <= 9.0 * PHI_INV + 1e-9, "el oro no respeta φ"
            g2 = Column(0, cell, H, random.Random(1), KIND_GOLD)
            seq = "".join(g2._new_glyph() for _ in range(len(FIB)))
            assert seq in (FIB + FIB), "el oro no deletrea Fibonacci"
            pg.quit()
            print("self-test OK — %d columnas, %d glifos cacheados, fuente=%s" %
                  (len(cols), len(cache), fname))
            return 0
        if args.seconds and frame / float(args.fps) >= args.seconds:
            pg.quit()
            return 0
        clock.tick(args.fps)


def main(argv=None):
    p = argparse.ArgumentParser(description="Lluvia digital FQ en Pygame (alto rendimiento)")
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--height", type=int, default=900)
    p.add_argument("--font", type=int, default=22, help="tamaño de glifo = tamaño de celda")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--fade", type=int, default=26, help="alfa del velo (↑ = estela corta)")
    p.add_argument("--gold", type=float, default=0.09)
    p.add_argument("--sol", type=float, default=0.07)
    p.add_argument("--seconds", type=float, default=0)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--no-messages", action="store_true")
    p.add_argument("--record", metavar="PATH_%04d.png", help="guarda un PNG por frame")
    p.add_argument("--screenshot", metavar="PATH.png", help="guarda un solo still y sale")
    p.add_argument("--warmup", type=int, default=120, help="frames antes de capturar")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    try:
        import pygame  # noqa: F401
    except ImportError:
        sys.stderr.write("pygame no instalado: pip install pygame  (o usa "
                         "tools/matrix_rain.py, la versión curses sin dependencias)\n")
        return 1
    try:
        return run(args)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
