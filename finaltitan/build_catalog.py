"""Builds data/titans.csv and data/upgrades.csv from the card database (English rows) and the images present in assets/."""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "assets" / "Final Titan Card Database.csv"
TITAN_DIR = ROOT / "assets" / "titans"
UPGRADE_DIR = ROOT / "assets" / "upgrades"
DATA = ROOT / "data"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# Image stems whose names differ from the database name after normalisation.
TITAN_ALIASES = {
    "arachnidra": "arachnidora",
    "twilith": "twilight",
    "kitsune": "hitsune",
    "genesis10": "genesis1point0",
}

TITAN_FIELDS = ["id", "name", "max_life", "speed", "armor", "team_power", "advanced", "enemy_usable", "legendary_id", "expansion"]
UPGRADE_FIELDS = ["id", "name", "advanced", "enemy_usable", "legendary", "expansion"]


def norm(text: str) -> str:
    text = text.replace("&", "and")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_english_rows() -> list[dict[str, str]]:
    # Encoding is mixed per line: UTF-8 for most, cp1252 for some.
    def decode(line: bytes) -> str:
        try:
            return line.decode("utf-8")
        except UnicodeDecodeError:
            return line.decode("cp1252", errors="replace")

    text = "".join(decode(l) for l in DB.read_bytes().splitlines(keepends=True))
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
    header = [h.replace("\n", " ").strip() for h in rows[0]]
    result = []
    for r in rows[1:]:
        if r and r[0].strip() == "English":
            result.append(dict(zip(header, r)))
    return result


def images(folder: Path) -> list[tuple[Path, bool]]:
    """Image files as (path, in_noCoop_folder)."""
    found = [(p, False) for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    sub = folder / "noCoop"
    if sub.is_dir():
        found += [(p, True) for p in sorted(sub.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    return found


def flag(value: str) -> str:
    return "true" if value.strip() else "false"


def main() -> None:
    rows = read_english_rows()
    titan_rows = [r for r in rows if r["Type"] == "Titan"]
    upgrade_rows = [r for r in rows if r["Type"] == "Upgrade"]

    titan_by_norm = {norm(r["Original Card Name"]): r for r in titan_rows}
    for alias, target in TITAN_ALIASES.items():
        if alias in titan_by_norm:
            titan_by_norm[target] = titan_by_norm[alias]

    titans, unmatched_images = [], []
    for path, nocoop_dir in images(TITAN_DIR):
        if path.stem == "finalTitanCardBackside":
            continue
        row = titan_by_norm.get(norm(path.stem))
        if row is None:
            unmatched_images.append(path.name)
            continue
        titans.append({
            "id": path.stem,
            "name": row["Original Card Name"],
            "max_life": row["Max Life"] or "0",
            "speed": row["Speed"] or "0",
            "armor": row["Armor"] or "0",
            "team_power": flag(row["Team Power"]),
            "advanced": "true" if row["Set Icon"].strip() == "Advanced" else "false",
            "enemy_usable": "false" if (row["Non-Coop"].strip() or nocoop_dir) else "true",
            "legendary_id": "",
            "expansion": "Advanced Set" if row["Set Icon"].strip() == "Advanced" else row["Set"],
        })

    upgrade_by_norm = {norm(r["Original Card Name"]): r for r in upgrade_rows}
    upgrades = []
    for path, _ in images(UPGRADE_DIR):
        row = upgrade_by_norm.get(norm(re.sub(r"\d+$", "", path.stem)))
        if row is None:
            unmatched_images.append(f"upgrades/{path.name}")
            continue
        upgrades.append({
            "id": path.stem,
            "name": row["Original Card Name"],
            "advanced": "true" if row["Set Icon"].strip() == "Advanced" else "false",
            "enemy_usable": "false" if row["Non-Coop"].strip() else "true",
            "legendary": "false",
            "expansion": "Advanced Set" if row["Set Icon"].strip() == "Advanced" else row["Set"],
        })

    DATA.mkdir(exist_ok=True)
    for name, fields, items in (("titans.csv", TITAN_FIELDS, titans), ("upgrades.csv", UPGRADE_FIELDS, upgrades)):
        with open(DATA / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(items)

    print(f"titans: {len(titans)} of {len(titan_rows)} database cards have an image")
    print(f"upgrades: {len(upgrades)} images mapped ({len(upgrade_rows)} database cards)")
    print("images without a database match:", unmatched_images or "none")
    matched = {t["name"] for t in titans}
    print("titan names without image:", sum(1 for r in titan_rows if r["Original Card Name"] not in matched))


if __name__ == "__main__":
    main()
