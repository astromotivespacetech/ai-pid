"""
Generate a set of instrumentation symbols by overlaying ISA-style tag text
inside the Discrete Instrument (field) circle, using the same centering logic.

Outputs go to static/symbols with descriptive filenames.

Run:
  python tools/generate_instruments.py
"""

from pathlib import Path
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS_DIR = ROOT / "static" / "symbols"
BASE_NAME = "Discrete_instrument_(field).svg.png"

# tag text, output filename
ITEMS: List[Tuple[str, str]] = [
    ("PT", "pressure_transmitter.png"),
    ("PI", "pressure_indicator.png"),
    ("PC", "pressure_controller.png"),
    ("PIC", "pressure_indicating_controller.png"),
    ("DP", "differential_pressure_transmitter.png"),

    ("TT", "temperature_transmitter.png"),
    ("TI", "temperature_indicator.png"),
    ("TC", "temperature_controller.png"),
    ("TIC", "temperature_indicating_controller.png"),

    ("FT", "flow_transmitter.png"),
    ("FI", "flow_indicator.png"),
    ("FC", "flow_controller.png"),
    ("FIC", "flow_indicating_controller.png"),

    ("LT", "level_transmitter.png"),
    ("LI", "level_indicator.png"),
    ("LC", "level_controller.png"),
    ("LIC", "level_indicating_controller.png"),

    ("pH", "ph_analyzer.png"),
    ("ORP", "orp_analyzer.png"),
    ("DO", "dissolved_oxygen_analyzer.png"),
    ("COND", "conductivity_analyzer.png"),
    ("I/P", "ip_transducer.png"),

    # Switches (High/Low)
    ("PSH", "pressure_switch_high.png"),
    ("PSL", "pressure_switch_low.png"),
    ("TSH", "temperature_switch_high.png"),
    ("TSL", "temperature_switch_low.png"),
    ("FSH", "flow_switch_high.png"),
    ("FSL", "flow_switch_low.png"),
    ("LSH", "level_switch_high.png"),
    ("LSL", "level_switch_low.png"),

    # Alarms (High/Low)
    ("PAH", "pressure_alarm_high.png"),
    ("PAL", "pressure_alarm_low.png"),
    ("TAH", "temperature_alarm_high.png"),
    ("TAL", "temperature_alarm_low.png"),
    ("FAH", "flow_alarm_high.png"),
    ("FAL", "flow_alarm_low.png"),
    ("LAH", "level_alarm_high.png"),
    ("LAL", "level_alarm_low.png"),
]


def load_font(img_size: Tuple[int, int]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    w, h = img_size
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/ARIAL.TTF",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    size = max(16, int(h * 0.30))
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_tag(base_img: Image.Image, text: str) -> Image.Image:
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Circle region heuristic: top 3/8 of the image
    alpha = img.split()[3]
    top_h = int(H * 3 / 8)
    region = (0, 0, W, top_h)
    sub = alpha.crop(region)
    sub_box = sub.getbbox()
    if sub_box is not None:
        content_box = (sub_box[0], sub_box[1], sub_box[2], sub_box[3])
    else:
        content_box = (0, 0, W, top_h)

    cx = (content_box[0] + content_box[2]) // 2
    cy = (content_box[1] + content_box[3]) // 2
    cw = max(1, content_box[2] - content_box[0])
    ch = max(1, content_box[3] - content_box[1])

    base_font = load_font((W, H))

    def measure(font: ImageFont.ImageFont) -> Tuple[int, int]:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    target_w = int(cw * 0.55)
    target_h = int(ch * 0.55)
    font = base_font
    if hasattr(base_font, "size"):
        size = getattr(base_font, "size", max(16, int(H * 0.30)))
        for s in range(size, 6, -2):
            try:
                font = ImageFont.truetype(base_font.path, s)  # type: ignore[attr-defined]
            except Exception:
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", s)
                except Exception:
                    font = base_font
            tw, th = measure(font)
            if tw <= target_w and th <= target_h:
                break
    tw, th = measure(font)
    x = cx - tw // 2
    y = cy - th // 2

    draw.text((x, y), text, font=font, fill=(0, 0, 0, 255))
    return img


def main():
    base_path = SYMBOLS_DIR / BASE_NAME
    if not base_path.exists():
        raise FileNotFoundError(f"Base symbol not found: {base_path}")

    base_img = Image.open(base_path).convert("RGBA")

    created = 0
    for text, filename in ITEMS:
        out_path = SYMBOLS_DIR / filename
        img = draw_tag(base_img, text)
        img.save(out_path)
        created += 1
        print(f"[OK] Wrote {out_path.name}")

    print(f"\n[OK] Generated {created} instrument symbols in {SYMBOLS_DIR}")


if __name__ == "__main__":
    main()
