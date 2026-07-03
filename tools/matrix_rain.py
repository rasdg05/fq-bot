#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix_rain — lluvia digital del Fibonacci Quantum Framework (pieza de SHOW).

Lluvia tipo Matrix en la terminal, EN MOVIMIENTO, con la identidad de la casa:

  * ~9%% de las columnas caen DORADAS (φ) a velocidad 0.618× y no llevan glifos
    al azar: deletrean la sucesión de Fibonacci (1 1 2 3 5 8 13 21 34 55 89 ...).
  * ~7%% llevan el degradado Solana (violeta -> verde) en la estela.
  * El resto es la lluvia clásica en verde fósforo con katakana + φ Φ Σ λ Ξ ₿.
  * Cada 5/8/13 segundos (Fibonacci) un mensaje de la casa se materializa en oro
    letra por letra y se disuelve: FQ CAPITAL, φ = 1.6180339887, DSR>0.95, etc.

Es VANIDAD DECLARADA para clips de marketing y demos en vivo — NO toca al motor,
no importa nada del bot, stdlib puro (curses). Si muere, no muere nada más.

Uso:
    python3 tools/matrix_rain.py                 # pantalla completa, q/ESC sale
    python3 tools/matrix_rain.py --seconds 30    # clip de 30 s (para grabar)
    python3 tools/matrix_rain.py --fps 30 --gold 0.13 --no-messages
    python3 tools/matrix_rain.py --self-test     # smoke sin terminal (CI)
"""
import argparse
import random
import sys
import time

# Glifos: katakana de ancho medio (la firma Matrix) + los símbolos de la casa.
GLYPHS = ("ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
          "0123456789φΦΣλΞπΔ∑√₿")
ASCII_GLYPHS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*+=<>|"
# La sucesión de Fibonacci como río de dígitos: 1 1 2 3 5 8 13 21 34 55 89 144...
FIB = "1123581321345589144233377610987159725844181676510946177112865746368"
PHI = 0.6180339887

MESSAGES = (
    "FQ CAPITAL",
    "FIBONACCI QUANTUM FRAMEWORK",
    "φ = 1.6180339887",
    "DSR > 0.95 · CPCV · PBO",
    "SOL · BTC · ETH",
    "MEDIDA O MUERTE",
    "ORDER-FLOW CONFIRMADO",
)

KIND_GREEN, KIND_GOLD, KIND_SOL = 0, 1, 2


class Column(object):
    """Una columna de lluvia: estado puro, sin curses (testeable sin terminal)."""

    def __init__(self, x, height, rng, kind=KIND_GREEN, glyphs=GLYPHS):
        self.x = x
        self.h = height
        self.rng = rng
        self.kind = kind
        self._glyphs = FIB if kind == KIND_GOLD else glyphs
        self._fib_i = rng.randrange(len(FIB)) if kind == KIND_GOLD else 0
        self.reset(first=True)

    def reset(self, first=False):
        base = self.rng.uniform(0.35, 1.0)          # celdas por frame (tope 1: sin huecos)
        self.speed = base * PHI if self.kind == KIND_GOLD else base
        self.trail = 21 if self.kind == KIND_GOLD else self.rng.choice((8, 13))
        start = -self.rng.randrange(1, self.h * 2 if first else self.h)
        self.y = float(start)
        self.head = start
        self.glyphs = {}

    def _new_glyph(self):
        if self.kind == KIND_GOLD:                  # el oro deletrea Fibonacci
            self._fib_i = (self._fib_i + 1) % len(FIB)
            return FIB[self._fib_i]
        return self.rng.choice(self._glyphs)

    def step(self):
        """Avanza un frame; devuelve celdas (y, borrar=True) a limpiar."""
        self.y += self.speed
        new_head = int(self.y)
        for y in range(self.head + 1, new_head + 1):
            self.glyphs[y] = self._new_glyph()
        self.head = new_head
        tail = self.head - self.trail
        dead = [y for y in self.glyphs if y < tail]
        for y in dead:
            del self.glyphs[y]
        # mutación ocasional: la lluvia "vive" aunque la columna sea lenta
        if self.glyphs and self.rng.random() < 0.04:
            y = self.rng.choice(list(self.glyphs))
            self.glyphs[y] = self._new_glyph()
        if tail > self.h:                           # salió por abajo: renace arriba
            self.reset()
        return tail

    def cells(self):
        """[(y, char, i_estela)] con i=0 en la cabeza (para el degradado)."""
        out = []
        for y, ch in self.glyphs.items():
            i = self.head - y
            if 0 <= y < self.h and 0 <= i < self.trail:
                out.append((y, ch, i))
        return out


class Message(object):
    """Mensaje de la casa que se materializa letra a letra y se disuelve."""

    def __init__(self, text, width, height, rng, t0):
        self.text = text
        self.x = max(0, (width - len(text)) // 2)
        self.y = max(1, height // 3 + rng.randrange(-2, 3))
        self.t0 = t0
        self.reveal = 0.045 * len(text)             # ~22 letras/s
        self.hold = 2.5
        self.fade = 0.6

    def phase(self, t):
        dt = t - self.t0
        if dt < self.reveal:
            return "reveal", int(len(self.text) * dt / self.reveal)
        if dt < self.reveal + self.hold:
            return "hold", len(self.text)
        if dt < self.reveal + self.hold + self.fade:
            return "fade", len(self.text)
        return "done", 0


def build_columns(width, height, rng, gold=0.09, sol=0.07, density=0.75,
                  glyphs=GLYPHS):
    cols = []
    for x in range(width - 1):
        if rng.random() > density:
            continue
        r = rng.random()
        kind = KIND_GOLD if r < gold else (KIND_SOL if r < gold + sol else KIND_GREEN)
        cols.append(Column(x, height, rng, kind, glyphs))
    return cols


# ---------------------------------------------------------------- curses ----

def _init_palettes():
    """[(kind, i_estela) -> attr]. 256 colores si hay; si no, 8 con bold/dim."""
    import curses
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    palettes = {}
    if curses.COLORS >= 256:
        ramps = {KIND_GREEN: (231, 46, 40, 34, 28, 22),
                 KIND_GOLD:  (230, 220, 178, 178, 136, 94),
                 KIND_SOL:   (231, 85, 49, 141, 135, 99)}   # blanco->verde->violeta
        pair = 1                                    # un par de color único por peldaño
        for kind, ramp in ramps.items():
            attrs = []
            for fg in ramp:
                curses.init_pair(pair, fg, bg)
                attrs.append(curses.color_pair(pair))
                pair += 1
            palettes[kind] = attrs
    else:
        base = {KIND_GREEN: curses.COLOR_GREEN, KIND_GOLD: curses.COLOR_YELLOW,
                KIND_SOL: curses.COLOR_MAGENTA}
        pair = 1
        for kind, fg in base.items():
            curses.init_pair(pair, fg, bg)
            c = curses.color_pair(pair)
            palettes[kind] = [curses.A_BOLD | c, curses.A_BOLD | c, c, c,
                              curses.A_DIM | c, curses.A_DIM | c]
            pair += 1
    return palettes


def _attr(palettes, kind, i, trail):
    ramp = palettes[kind]
    j = min(len(ramp) - 1, int(i * len(ramp) / max(1, trail)))
    return ramp[j]


def run(scr, args):
    import curses
    curses.curs_set(0)
    scr.nodelay(True)
    scr.timeout(0)
    palettes = _init_palettes()
    gold_head = palettes[KIND_GOLD][1]
    rng = random.Random(args.seed)
    h, w = scr.getmaxyx()
    glyphs = ASCII_GLYPHS if args.ascii else GLYPHS
    cols = build_columns(w, h, rng, args.gold, args.sol, args.density, glyphs)

    t_start = time.monotonic()
    frame_dt = 1.0 / max(1, args.fps)
    msg = None
    next_msg = t_start + rng.choice((5, 8))
    while True:
        t = time.monotonic()
        if args.seconds and t - t_start >= args.seconds:
            return 0
        ch = scr.getch()
        if ch in (ord("q"), ord("Q"), 27):
            return 0
        if ch == curses.KEY_RESIZE:
            h, w = scr.getmaxyx()
            scr.erase()
            cols = build_columns(w, h, rng, args.gold, args.sol, args.density, glyphs)

        for col in cols:
            tail = col.step()
            if 0 <= tail < h:
                try:
                    scr.addstr(tail, col.x, " ")
                except curses.error:
                    pass
            for y, c, i in col.cells():
                try:
                    scr.addstr(y, col.x, c, _attr(palettes, col.kind, i, col.trail))
                except curses.error:
                    pass

        if not args.no_messages:
            if msg is None and t >= next_msg:
                msg = Message(rng.choice(MESSAGES), w, h, rng, t)
            if msg is not None:
                phase, n = msg.phase(t)
                if phase == "done":
                    msg = None
                    next_msg = t + rng.choice((5, 8, 13))
                else:
                    attr = palettes[KIND_GOLD][4] if phase == "fade" else gold_head
                    try:
                        scr.addstr(msg.y, msg.x, msg.text[:n], attr | curses.A_BOLD)
                    except curses.error:
                        pass

        scr.refresh()
        spent = time.monotonic() - t
        if spent < frame_dt:
            time.sleep(frame_dt - spent)


# ------------------------------------------------------------- self-test ----

def self_test():
    """Smoke sin terminal: la física de la lluvia, no el dibujo."""
    rng = random.Random(21)
    cols = build_columns(120, 40, rng, gold=0.2, sol=0.1)
    assert len(cols) > 60, "densidad rota"
    kinds = {c.kind for c in cols}
    assert KIND_GOLD in kinds and KIND_GREEN in kinds, "faltan castas"
    gold = [c for c in cols if c.kind == KIND_GOLD]
    green = [c for c in cols if c.kind == KIND_GREEN]
    # el oro cae a ritmo φ: estrictamente más lento que el tope verde
    assert max(c.speed for c in gold) <= 1.0 * PHI + 1e-9, "el oro no respeta φ"
    assert all(c.trail == 21 for c in gold), "estela dorada != 21 (Fibonacci)"
    for _ in range(600):
        for c in cols:
            c.step()
    c = gold[0]
    assert c.glyphs and all(g in "0123456789" for g in c.glyphs.values()), \
        "el oro debe deletrear Fibonacci"
    assert any(cell[2] == 0 for cell in c.cells()) or c.head < 0 or c.head >= c.h
    seq = "".join(FIB[(c._fib_i + i) % len(FIB)] for i in range(1, 4))
    c2 = Column(0, 40, random.Random(1), KIND_GOLD)
    got = "".join(c2._new_glyph() for _ in range(len(FIB)))
    assert got in (FIB + FIB), "la sucesión no es la de Fibonacci"
    m = Message("FQ CAPITAL", 100, 40, rng, t0=0.0)
    assert m.phase(0.01)[0] == "reveal"
    assert m.phase(m.reveal + 0.1)[0] == "hold"
    assert m.phase(m.reveal + m.hold + 0.1)[0] == "fade"
    assert m.phase(m.reveal + m.hold + m.fade + 0.1)[0] == "done"
    print("self-test OK — lluvia con física φ verificada (%d columnas)" % len(cols))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Lluvia digital FQ (Matrix + φ + Solana)")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--gold", type=float, default=0.09, help="fracción de columnas φ doradas")
    p.add_argument("--sol", type=float, default=0.07, help="fracción con degradado Solana")
    p.add_argument("--density", type=float, default=0.75)
    p.add_argument("--seconds", type=float, default=0, help="salir tras N s (clips)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--ascii", action="store_true", help="glifos ASCII (terminales pobres)")
    p.add_argument("--no-messages", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        import curses
    except ImportError:
        sys.stderr.write("curses no disponible; corre con --self-test o instala ncurses\n")
        return 1
    try:
        return curses.wrapper(run, args) or 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
