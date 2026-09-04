#!/usr/bin/env python3
"""Regenera los iconos de la PWA a partir de public/logo.png (logotipo PEPITO).

Uso: python3 scripts/gen-icons.py   (requiere Pillow: pip install pillow)
Genera: icons/icon-192.png, icons/icon-512.png, icons/icon-maskable-512.png (zona segura 80 %),
        icons/apple-touch-icon.png (180), favicon.ico y mark.png (cabeza de la mascota para barras y favicon).
"""
from pathlib import Path
from PIL import Image

PUB = Path(__file__).resolve().parent.parent / "public"
BG = (248, 242, 229, 255)  # crema del logotipo
src = Image.open(PUB / "logo.png").convert("RGBA")
w, h = src.size
head = src.crop((int(w * 0.17), 0, int(w * 0.83), int(h * 0.56)))


def square(im: Image.Image, size: int, pad: float) -> Image.Image:
    out = Image.new("RGBA", (size, size), BG)
    inner = int(size * (1 - 2 * pad))
    r = im.copy()
    r.thumbnail((inner, inner), Image.LANCZOS)
    out.paste(r, ((size - r.width) // 2, (size - r.height) // 2), r)
    return out


(PUB / "icons").mkdir(exist_ok=True)
square(src, 192, 0.04).save(PUB / "icons/icon-192.png")
square(src, 512, 0.04).save(PUB / "icons/icon-512.png")
square(src, 512, 0.12).save(PUB / "icons/icon-maskable-512.png")
square(src, 180, 0.04).save(PUB / "icons/apple-touch-icon.png")
square(head, 128, 0.02).save(PUB / "mark.png")
square(head, 64, 0.02).save(PUB / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print("iconos regenerados en", PUB)
