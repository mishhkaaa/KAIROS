"""Draws the app's icons from the KAIROS mark (four tesserae, the last in ink). Run from apps/mobile:

    uv run --project ../.. python scripts/make-icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
GROUND = (238, 241, 246, 255)
BRAND = (11, 107, 96)
INK = (15, 23, 42)


def mark(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, mono: tuple[int, int, int, int] | None = None) -> None:
    """The 24-unit mark at (x, y), `size` pixels wide."""
    u = size / 24
    tiles = [(2, 2, BRAND, 255), (13, 2, BRAND, 140), (2, 13, BRAND, 140), (13, 13, INK, 217)]
    for tx, ty, rgb, a in tiles:
        fill = mono if mono else (*rgb, a)
        draw.rounded_rectangle([x + tx * u, y + ty * u, x + (tx + 9) * u, y + (ty + 9) * u], radius=2 * u, fill=fill)


def canvas(size: int, bg: tuple[int, int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size, size), bg)
    return img, ImageDraw.Draw(img)


# App icon (iOS, Expo Go, the store): the mark on the desktop's paper, with room around it.
img, d = canvas(1024, GROUND)
mark(d, 212, 212, 600)
img.save(OUT / "icon.png")

# Android adaptive icon: the foreground keeps the mark inside the 66% safe circle; the background is the paper.
img, d = canvas(1024, (0, 0, 0, 0))
mark(d, 322, 322, 380)
img.save(OUT / "android-icon-foreground.png")
canvas(1024, GROUND)[0].save(OUT / "android-icon-background.png")
img, d = canvas(1024, (0, 0, 0, 0))
mark(d, 322, 322, 380, mono=(255, 255, 255, 255))
img.save(OUT / "android-icon-monochrome.png")

# Splash and the web favicon.
img, d = canvas(512, (0, 0, 0, 0))
mark(d, 56, 56, 400)
img.save(OUT / "splash-icon.png")
img, d = canvas(48, GROUND)
mark(d, 4, 4, 40)
img.save(OUT / "favicon.png")

# Notification small icon (Android wants white on transparent).
img, d = canvas(96, (0, 0, 0, 0))
mark(d, 8, 8, 80, mono=(255, 255, 255, 255))
img.save(OUT / "notification-icon.png")
print("icons written to", OUT)
