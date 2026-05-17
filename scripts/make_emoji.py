"""Turn logo.png into ready-to-upload custom-emoji assets.

Trims the transparent border, squares it, and exports the sizes the
common custom-emoji surfaces want (Discord/Slack 128, retina 256, and a
small 64 for inline markdown "emoji"). Run:

    .venv/Scripts/python.exe scripts/make_emoji.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "logo.png"
OUT = ROOT / "assets"
SIZES = (256, 128, 64)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    im = Image.open(SRC).convert("RGBA")

    bbox = im.getbbox()  # drop the fully-transparent margin
    im = im.crop(bbox) if bbox else im

    side = max(im.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))

    for s in SIZES:
        dst = OUT / f"gitbob-emoji-{s}.png"
        square.resize((s, s), Image.LANCZOS).save(dst, optimize=True)
        kb = dst.stat().st_size / 1024
        print(f"  wrote {dst.relative_to(ROOT)}  ({s}x{s}, {kb:.0f} KB)")

    print("\nUpload gitbob-emoji-128.png as a custom emoji on Discord/Slack")
    print("(<=256 KB). Use gitbob-emoji-64.png for inline markdown emoji.")


if __name__ == "__main__":
    main()
