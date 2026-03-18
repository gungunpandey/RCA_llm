"""
extract_equipment.py
====================
Scans the pdfs/ subdirectories and extracts equipment names from PDF filenames.

Naming convention assumed:
    {EquipmentName}_{Manufacturer}_{DocType}.pdf
    e.g.  "Air Drier_Elgi_OEM Manual.pdf"  →  equipment = "Air Drier"

Output
------
Writes  data_ingestion/equipment_by_division.json
which maps each app division name to a sorted, deduplicated list of equipment names.

Folder → Division mapping
-------------------------
A single pdf folder can apply to multiple app divisions (e.g. 'dri' covers both DRI 1 & DRI 2).
Edit FOLDER_TO_DIVISIONS below to adjust.

Usage
-----
    cd data_ingestion
    python extract_equipment.py
"""

import os
import json
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

# Directory that contains the division sub-folders of PDFs
PDFS_ROOT = Path(__file__).parent / "pdfs"

# Output file path
OUTPUT_FILE = Path(__file__).parent / "equipment_by_division.json"

# Map each subfolder name → list of app division names it covers
FOLDER_TO_DIVISIONS = {
    "bnfc":        ["BNFC"],
    "cpp":         ["CPP", "CPP 2"],
    "dri":         ["DRI 1", "DRI 2"],
    "jigging":     ["BNFC"],          # jigging equipment belongs to BNFC — adjust if needed
    "pdfs_pci":    ["DRI 1", "DRI 2"],# PCI section — adjust if needed
    "pdfs_pellet": ["Pellet 1", "Pellet 2"],
    "pgp":         ["PGP"],
    "sms":         ["SMS 1", "SMS 2"],
}

# ── Extraction ────────────────────────────────────────────────────────────────

def extract_equipment_name(filename: str) -> str | None:
    """Return the equipment name (part before first '_') from a PDF filename."""
    stem = Path(filename).stem          # strip .pdf
    parts = stem.split("_", maxsplit=1)
    name = parts[0].strip()
    return name if name else None


def build_division_map() -> dict:
    """Walk pdfs/ subfolders and return {division: [equipment, ...]}."""
    division_map: dict[str, set] = {}

    for folder_name, divisions in FOLDER_TO_DIVISIONS.items():
        folder_path = PDFS_ROOT / folder_name
        if not folder_path.is_dir():
            print(f"  [WARN] Folder not found: {folder_path}")
            continue

        pdf_files = [f for f in folder_path.iterdir() if f.suffix.lower() == ".pdf"]
        names: set[str] = set()

        for pdf in pdf_files:
            name = extract_equipment_name(pdf.name)
            if name:
                names.add(name)

        print(f"  {folder_name:14s} -> {', '.join(sorted(divisions))}  ({len(names)} unique equipment names)")

        for division in divisions:
            if division not in division_map:
                division_map[division] = set()
            division_map[division].update(names)

    # Convert sets to sorted lists
    return {div: sorted(names) for div, names in sorted(division_map.items())}


def main():
    print(f"Scanning: {PDFS_ROOT}\n")

    if not PDFS_ROOT.is_dir():
        print(f"ERROR: pdfs root not found at {PDFS_ROOT}")
        return

    division_map = build_division_map()

    total = sum(len(v) for v in division_map.values())
    print(f"\nTotal: {len(division_map)} divisions, {total} equipment entries")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(division_map, f, indent=2, ensure_ascii=False)

    print(f"\nSaved -> {OUTPUT_FILE}")

    # Pretty-print summary
    print("\n-- Summary --------------------------------------------------")
    for div, equips in division_map.items():
        print(f"  {div:15s}: {', '.join(equips)}")


if __name__ == "__main__":
    main()
