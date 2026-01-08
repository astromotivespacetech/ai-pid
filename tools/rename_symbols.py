"""
Normalize and rename symbol files in static/symbols to a logical convention.

Conventions:
- lowercase
- replace spaces, hyphens, commas with underscores
- remove ISO references (iso_10628-2) and stray "svg" in base names
- collapse repeated underscores
- keep extension (.png/.svg) unchanged

Usage:
  python tools/rename_symbols.py            # dry-run only, writes mapping JSON
  python tools/rename_symbols.py --apply    # apply renames

Outputs:
- output/rename_mapping.json: proposed mapping and duplicates report
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS_DIR = ROOT / "static" / "symbols"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Explicit user overrides: source filename -> target filename (with extension decided per file)
OVERRIDES = {
    # Axial fan vs axial ventilator treated as distinct
    "Axial_fan.svg.png": "axial_fan.png",
    "Axialventilator_Symbol.svg.png": "axial_ventilator.png",

    # Use the 120px check valve as canonical, keep general as separate
    "120px-Check_Valve.svg.png": "check_valve.png",
    "Check_valve_(general)_(ISO_10628-2).svg.png": "check_valve_general.png",

    # Use 'Symbol_plate_heat_exchanger' as canonical and rename to plate_heat_exchanger
    "Symbol_plate_heat_exchanger.svg.png": "plate_heat_exchanger.png",
    # Keep the other as an alt
    "Plate_heat_exchanger.svg.png": "plate_heat_exchanger_alt.png",

    # Three-way ball valve duplicates: keep main and alt
    "Valve,_three_way_ball_type_-_ISO_10628-2.svg.png": "valve_three_way_ball_type.png",
    "Valve,_three_way_ball_type_-_ISO_10628-2.svg (1).png": "valve_three_way_ball_type_alt.png",

    # Three-way globe valve duplicates: keep main and alt
    "Valve,_three_way_globe_type_-_ISO_10628-2.svg.png": "valve_three_way_globe_type.png",
    "Valve,_three_way_globe_type_-_ISO_10628-2.svg (1).png": "valve_three_way_globe_type_alt.png",
}


def normalize_base(name: str) -> str:
    # strip extension and internal trailing .svg in base
    base = name
    # strip extension first
    base = re.sub(r"\.(svg|png)$", "", base, flags=re.IGNORECASE)

    # remove duplicate copy markers like " (1)" at end (after removing extension)
    base = re.sub(r"\s*\(\d+\)$", "", base)

    # strip trailing .svg in base (handles names like "...svg (1).png")
    base = re.sub(r"\.svg$", "", base, flags=re.IGNORECASE)

    # remove leading pixel size like "120px-"
    base = re.sub(r"^\d+px-", "", base, flags=re.IGNORECASE)

    # drop ISO reference variants
    base = re.sub(r"[_\- ]*iso[_\-]?10628\-2", "", base, flags=re.IGNORECASE)
    base = re.sub(r"\(iso[_\-]?10628\-2\)", "", base, flags=re.IGNORECASE)

    # remove the literal word symbol if present at ends or as prefix
    base = re.sub(r"(^symbol[_\-]|[_\-]symbol$)", "", base, flags=re.IGNORECASE)

    # replace punctuation (commas, spaces, hyphens) with underscores
    base = re.sub(r"[\s\-]+", "_", base)
    base = re.sub(r"[,]+", "_", base)

    # remove parentheses by turning into underscores
    base = base.replace("(", "_").replace(")", "_")

    # collapse multiple underscores
    base = re.sub(r"_+", "_", base)

    # trim underscores
    base = base.strip("_")

    # lowercase
    base = base.lower()

    return base


def category_normalize(base: str) -> str:
    # very light touch: map some synonyms to consistent category stems
    synonyms = [
        (r"^axialventilator.*", "axial_fan"),
        (r"^anglosaxon\-fan.*", "fan"),
        (r"^air_cooler$", "air_cooler"),
        (r"^symbol_hex_", "heat_exchanger_"),
        (r"^hex_", "heat_exchanger_"),
        (r"^kettle_reboiler\-symbol$", "reboiler"),
        (r"^stirrer$", "agitator"),
    ]
    for pat, repl in synonyms:
        if re.match(pat, base):
            return re.sub(pat, repl, base)
    return base


def propose_target_name(src_name: str, ext: str) -> str:
    # honor explicit overrides first (override includes extension already)
    if src_name in OVERRIDES:
        target = OVERRIDES[src_name]
        # ensure extension aligns with actual ext
        base = re.sub(r"\.(svg|png)$", "", target, flags=re.IGNORECASE)
        return f"{base}{ext.lower()}"

    base = normalize_base(src_name)
    base = category_normalize(base)

    # simplify common patterns (keep meaningful descriptors)
    base = re.sub(r"^valve[_\-]?", "valve_", base)
    base = re.sub(r"^pump[_\-]?", "pump_", base)
    base = re.sub(r"^compressor[_\-]?", "compressor_", base)
    base = re.sub(r"^heat_exchanger[_\-]?", "heat_exchanger_", base)
    base = re.sub(r"^vessel[_\-]?", "vessel_", base)
    base = re.sub(r"^container[_\-]?", "vessel_", base)
    base = re.sub(r"^tank[_\-]?", "tank_", base)
    base = re.sub(r"^filter[_\-]?", "filter_", base)
    base = re.sub(r"^separator[_\-]?", "separator_", base)
    base = re.sub(r"^column[_\-]?", "column_", base)

    # remove trailing "_general" tokens
    base = re.sub(r"_general(_|$)", "_", base)
    base = base.strip("_")

    return f"{base}{ext.lower()}"


def build_mapping() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    mapping: Dict[str, str] = {}
    collisions: Dict[str, List[str]] = {}

    for entry in sorted(SYMBOLS_DIR.glob("*")):
        if not entry.is_file():
            continue
        ext = entry.suffix  # keep .png or .svg

        target = propose_target_name(entry.name, ext)
        if target in mapping.values():
            # find existing sources that map to this target
            sources = [s for s, t in mapping.items() if t == target]
            collisions.setdefault(target, sources).append(entry.name)
        mapping[entry.name] = target

    # detect near-duplicates that differ only by suffixes like _1 or stray '.svg'
    def canonical_key(filename: str) -> str:
        base = filename
        # remove extension
        base = re.sub(r"\.(svg|png)$", "", base, flags=re.IGNORECASE)
        # drop trailing copy index
        base = re.sub(r"_(\d+)$", "", base)
        # remove trailing .svg if left over after index removal
        base = re.sub(r"\.svg$", "", base, flags=re.IGNORECASE)
        return base

    by_key: Dict[str, List[str]] = {}
    for src, tgt in mapping.items():
        key = canonical_key(tgt)
        by_key.setdefault(key, []).append(src)

    for key, sources in by_key.items():
        if len(sources) > 1:
            # multiple source files normalize to same canonical key → possible duplicates
            # record under the "canonical" target key (add extension back for readability)
            target_display = f"{key}.png"
            existing = collisions.get(target_display, [])
            for s in sources:
                if s not in existing:
                    existing.append(s)
            collisions[target_display] = existing

    return mapping, collisions


def write_report(mapping: Dict[str, str], collisions: Dict[str, List[str]]):
    report = {
        "count": len(mapping),
        "collisions_count": len(collisions),
        "duplicates": collisions,
        "mapping": mapping,
    }
    out_path = OUTPUT_DIR / "rename_mapping.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[OK] Wrote mapping report to {out_path}")


def apply_mapping(mapping: Dict[str, str], collisions: Dict[str, List[str]]):
    # do not apply renames for targets with collisions (let user decide)
    skip_targets = set(collisions.keys())
    applied = 0
    for src, tgt in mapping.items():
        if tgt in skip_targets:
            print(f"[SKIP] collision target: {tgt} <- {src}")
            continue
        if src == tgt:
            continue
        src_path = SYMBOLS_DIR / src
        tgt_path = SYMBOLS_DIR / tgt
        # avoid overwriting
        if tgt_path.exists():
            print(f"[SKIP] target exists: {tgt} (from {src})")
            continue
        src_path.rename(tgt_path)
        applied += 1
        print(f"[RENAMED] {src} -> {tgt}")
    print(f"\n[OK] Applied {applied} renames (collisions left for manual review)")


def main():
    mapping, collisions = build_mapping()
    write_report(mapping, collisions)

    import sys
    do_apply = "--apply" in sys.argv
    if do_apply:
        apply_mapping(mapping, collisions)
    else:
        print("[DRY-RUN] No changes applied. Use --apply to rename.")
        if collisions:
            print(f"[INFO] {len(collisions)} collision targets found. See report for details.")


if __name__ == "__main__":
    main()
