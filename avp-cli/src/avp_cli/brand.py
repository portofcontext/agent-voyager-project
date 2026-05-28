"""AVP branding for the terminal: the ship logo + the palette.

The logo is the same monospace ASCII ship as `assets/logo.svg` (the `<avp>`
sail on a mast, over a hull). Palette matches the logo and the constellation
viz: sail gold, mast/light, hull, keel.
"""

from __future__ import annotations

from rich.text import Text

# Brand palette (hex), shared with the trajectory constellation.
SAIL = "#f3d28a"
MAST = "#e6eef3"
HULL = "#c98b4a"
KEEL = "#8a5b2c"
SKY = "#9fd6e7"

# A compact sailboat mark for prompts (the brand ship's one-glyph proxy).
SAILBOAT = "⛵"

# (text, color) per line, reconstructed from assets/logo.svg's row layout.
_SHIP: list[list[tuple[str, str]]] = [
    [("           _", SAIL)],
    [("        |", MAST), ("<avp>", SAIL)],
    [("        |", MAST), ("  ‾", SAIL)],
    [("        |", MAST), ("\\", SAIL)],
    [("        |", MAST), ("_\\", SAIL)],
    [("        |", MAST), ("__\\", SAIL)],
    [("        |", MAST), ("___\\", SAIL)],
    [("        |", MAST), ("____\\", SAIL)],
    [("        |", MAST), ("_____\\", SAIL)],
    [("\\______________/", HULL)],
    [(" \\____________/", KEEL)],
]


def logo() -> Text:
    """The AVP ship as a colored rich Text block."""
    out = Text()
    for i, line in enumerate(_SHIP):
        for span, color in line:
            out.append(span, style=color)
        if i < len(_SHIP) - 1:
            out.append("\n")
    return out
