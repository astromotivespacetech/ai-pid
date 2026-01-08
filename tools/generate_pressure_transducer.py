from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS_DIR = ROOT / "static" / "symbols"

BASE_NAME = "Discrete_instrument_(field).svg.png"
OUTPUT_NAME = "pressure_transducer.png"

def load_font(img_size: tuple[int, int]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    w, h = img_size
    # Try common Windows font, then DejaVu, then default
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/ARIAL.TTF",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    # Set size as a fraction of image height
    size = max(16, int(h * 0.34))
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except Exception:
                pass
    return ImageFont.load_default()

def main():
    base_path = SYMBOLS_DIR / BASE_NAME
    if not base_path.exists():
        raise FileNotFoundError(f"Base symbol not found: {base_path}")
    out_path = SYMBOLS_DIR / OUTPUT_NAME

    img = Image.open(base_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Heuristic: circle occupies the top 3/8 of the image; detect bbox within that region
    alpha = img.split()[3]
    top_frac = 3/8
    top_h = int(H * top_frac)
    region = (0, 0, W, top_h)
    sub = alpha.crop(region)
    sub_box = sub.getbbox()
    if sub_box is not None:
        # translate back to full image coords
        content_box = (sub_box[0], sub_box[1], sub_box[2], sub_box[3])
    else:
        # fallback to the defined top region
        content_box = (0, 0, W, top_h)

    cx = (content_box[0] + content_box[2]) // 2
    cy = (content_box[1] + content_box[3]) // 2
    cw = max(1, content_box[2] - content_box[0])
    ch = max(1, content_box[3] - content_box[1])

    # Choose font size to fit nicely inside the circle (about 55-65% of content width)
    # We’ll adjust down until it fits within 0.65 of content width and height
    base_font = load_font((W, H))
    text = "PT"

    def measure(font: ImageFont.ImageFont) -> tuple[int, int]:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    # If truetype, we can adjust size; if default, we’ll place as-is
    target_w = int(cw * 0.55)
    target_h = int(ch * 0.55)
    font = base_font
    # Try to shrink if too large
    if hasattr(base_font, "size"):
        size = getattr(base_font, "size", max(16, int(H * 0.34)))
        for s in range(size, 8, -2):
            try:
                font = ImageFont.truetype(base_font.path, s)  # type: ignore[attr-defined]
            except Exception:
                # Fallback if .path isn't available
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", s)
                except Exception:
                    font = base_font
            tw, th = measure(font)
            if tw <= target_w and th <= target_h:
                break
    else:
        # Default bitmap font: just measure once
        tw, th = measure(font)

    tw, th = measure(font)
    x = cx - tw // 2
    y = cy - th // 2

    # Draw solid black letters (no white outline)
    draw.text((x, y), text, font=font, fill=(0, 0, 0, 255))

    img.save(out_path)
    print(f"[OK] Wrote {out_path}")

if __name__ == "__main__":
    main()
