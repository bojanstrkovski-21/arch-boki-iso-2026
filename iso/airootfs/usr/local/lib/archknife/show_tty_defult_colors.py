#!/usr/bin/env python3
"""Show urwid named colors using actual Linux TTY (VGA) hex values.

Rendered with true-color ANSI escape codes so you see the exact colors
archiso displays, regardless of your terminal theme. No urwid palette needed.
"""

# Classic Linux TTY / VGA palette
TTY_HEX = {
    "black":         (0x00, 0x00, 0x00),
    "dark red":      (0xaa, 0x00, 0x00),
    "dark green":    (0x00, 0xaa, 0x00),
    "brown":         (0xaa, 0x55, 0x00),
    "dark blue":     (0x00, 0x00, 0xaa),
    "dark magenta":  (0xaa, 0x00, 0xaa),
    "dark cyan":     (0x00, 0xaa, 0xaa),
    "light gray":    (0xaa, 0xaa, 0xaa),
    "dark gray":     (0x55, 0x55, 0x55),
    "light red":     (0xff, 0x55, 0x55),
    "light green":   (0x55, 0xff, 0x55),
    "yellow":        (0xff, 0xff, 0x55),
    "light blue":    (0x55, 0x55, 0xff),
    "light magenta": (0xff, 0x55, 0xff),
    "light cyan":    (0x55, 0xff, 0xff),
    "white":         (0xff, 0xff, 0xff),
}

FG_COLORS = list(TTY_HEX.keys())
BG_COLORS = FG_COLORS[:8]  # only 8 valid background colors on TTY

def tc_fg(r, g, b): return f"\033[38;2;{r};{g};{b}m"
def tc_bg(r, g, b): return f"\033[48;2;{r};{g};{b}m"
RESET = "\033[0m"
BOLD  = "\033[1m"

# Header
header_fg = tc_fg(0xff, 0xff, 0xff)
header_bg = tc_bg(0x00, 0x00, 0xaa)
print(f"{header_fg}{header_bg}{BOLD}  Linux TTY colors (VGA defaults) — fg rows x bg cols  {RESET}")
print(f"{header_fg}{header_bg}  Exact colors archiso renders, ignoring your terminal theme.  {RESET}")
print()

# Column headers
print(f"{'foreground':>16}", end="")
for bg in BG_COLORS:
    short = bg.replace("dark ", "d.").replace("light ", "l.")
    print(f"  {short:^12}", end="")
print()
print("-" * (16 + len(BG_COLORS) * 14))

# Grid
for fg in FG_COLORS:
    fr, fg2, fb = TTY_HEX[fg]
    print(f"{fg:>16}", end="")
    for bg in BG_COLORS:
        br, bg2, bb = TTY_HEX[bg]
        label = f" {fg[:10]:10} "
        print(f"  {tc_fg(fr,fg2,fb)}{tc_bg(br,bg2,bb)}{label}{RESET}", end="")
    print()

print()
print("Modifiers (append with comma): bold  underline  blink  standout  italics  strikethrough")
