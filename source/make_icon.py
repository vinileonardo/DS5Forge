"""Turn a controller image into a tilted, background-free app icon (app.ico).

Usage:  python make_icon.py <source_image.png> [tilt_degrees]

Removes the white backdrop (flood-filled from the corners so the controller's
own white parts survive), tilts the controller, and writes a transparent
multi-resolution app.ico into the app's resources folder.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dualsense_companion", "resources", "app.ico")
SEED = (255, 0, 255)


def strip_background(img):
    rgb = img.convert("RGB")
    w, h = rgb.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if min(rgb.getpixel(corner)) > 218:
            ImageDraw.floodfill(rgb, corner, SEED, thresh=40)
    alpha = Image.new("L", (w, h), 255)
    alpha.putdata([0 if px == SEED else 255 for px in rgb.getdata()])
    alpha = alpha.filter(ImageFilter.MinFilter(3))  # erode 1px to drop white fringe
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def main():
    if len(sys.argv) < 2:
        print("give a source image path")
        return 1
    src = sys.argv[1]
    tilt = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0

    img = Image.open(src).convert("RGBA")
    # Keep an image's own transparency; only strip a backdrop if it's opaque.
    if img.getchannel("A").getextrema()[0] == 255:
        img = strip_background(img)
    img = img.rotate(-tilt, expand=True, resample=Image.BICUBIC)

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    side = max(img.size) + 24
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)

    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    canvas.save(OUT, format="ICO", sizes=sizes)
    print("wrote", OUT, f"(tilt {tilt}, transparent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
