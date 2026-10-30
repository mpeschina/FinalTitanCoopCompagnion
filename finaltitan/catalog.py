"""Card catalog: metadata CSVs plus image lookup. No Streamlit imports."""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ASSETS = ROOT / "assets"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
TITAN_BACK_STEM = "finalTitanCardBackside"

TITAN_FIELDS = ["id", "name", "max_life", "speed", "armor", "team_power", "advanced", "enemy_usable", "legendary_id", "expansion"]
UPGRADE_FIELDS = ["id", "name", "advanced", "enemy_usable", "legendary", "expansion"]


def norm(text: str) -> str:
    """Lowercase alphanumeric key for matching card names."""
    text = unicodedata.normalize("NFKD", text.replace("&", "and"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class TitanCard:
    id: str
    name: str
    max_life: int
    speed: int
    armor: int = 0
    team_power: bool = False
    advanced: bool = False
    enemy_usable: bool = True
    legendary_id: str = ""
    expansion: str = ""
    image: Path | None = None


@dataclass
class UpgradeCard:
    id: str
    name: str
    advanced: bool = False
    enemy_usable: bool = True
    legendary: bool = False
    expansion: str = ""
    image: Path | None = None


@dataclass
class Catalog:
    titans: dict[str, TitanCard]
    upgrades: dict[str, UpgradeCard]
    titan_back: Path | None = None

    def expansions(self) -> list[str]:
        names = {t.expansion for t in self.titans.values()} | {u.expansion for u in self.upgrades.values()}
        return sorted(n for n in names if n)

    def find_card(self, name: str, kind: str) -> list[str]:
        """Ids of all cards whose name matches, in id order."""
        pool = self.titans if kind == "titan" else self.upgrades
        key = norm(name)
        return sorted(c.id for c in pool.values() if norm(c.name) == key)


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except ValueError:
        return 0


def image_index(folder: Path) -> dict[str, Path]:
    """Maps image stem to path, including the noCoop subfolder."""
    found: dict[str, Path] = {}
    for base in (folder, folder / "noCoop"):
        if base.is_dir():
            for p in sorted(base.iterdir()):
                if p.is_file() and p.suffix.lower() in IMAGE_EXT:
                    found.setdefault(p.stem, p)
    return found


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_catalog(data_dir: Path = DATA_DIR, assets: Path = ASSETS) -> Catalog:
    t_images = image_index(assets / "titans")
    u_images = image_index(assets / "upgrades")
    titans: dict[str, TitanCard] = {}
    for r in read_rows(data_dir / "titans.csv"):
        card = TitanCard(
            id=r["id"], name=r["name"], max_life=_to_int(r["max_life"]), speed=_to_int(r["speed"]),
            armor=_to_int(r.get("armor", "0")), team_power=_to_bool(r.get("team_power", "")),
            advanced=_to_bool(r.get("advanced", "")), enemy_usable=_to_bool(r.get("enemy_usable", "true")),
            legendary_id=r.get("legendary_id", "") or "", expansion=r.get("expansion", ""),
            image=t_images.get(r["id"]),
        )
        titans.setdefault(card.id, card)
    upgrades: dict[str, UpgradeCard] = {}
    for r in read_rows(data_dir / "upgrades.csv"):
        card = UpgradeCard(
            id=r["id"], name=r["name"], advanced=_to_bool(r.get("advanced", "")),
            enemy_usable=_to_bool(r.get("enemy_usable", "true")), legendary=_to_bool(r.get("legendary", "")),
            expansion=r.get("expansion", ""), image=u_images.get(r["id"]),
        )
        upgrades.setdefault(card.id, card)
    return Catalog(titans, upgrades, t_images.get(TITAN_BACK_STEM))


def _b(value: bool) -> str:
    return "true" if value else "false"


def save_catalog(catalog: Catalog, data_dir: Path = DATA_DIR) -> None:
    data_dir.mkdir(exist_ok=True)
    with open(data_dir / "titans.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(TITAN_FIELDS)
        for t in catalog.titans.values():
            w.writerow([t.id, t.name, t.max_life, t.speed, t.armor, _b(t.team_power), _b(t.advanced), _b(t.enemy_usable), t.legendary_id, t.expansion])
    with open(data_dir / "upgrades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(UPGRADE_FIELDS)
        for u in catalog.upgrades.values():
            w.writerow([u.id, u.name, _b(u.advanced), _b(u.enemy_usable), _b(u.legendary), u.expansion])


def validate(data_dir: Path = DATA_DIR, assets: Path = ASSETS) -> list[str]:
    """Problems found in the metadata files versus the image folders."""
    issues: list[str] = []
    for kind, fname, folder in (("Titan", "titans.csv", "titans"), ("Upgrade", "upgrades.csv", "upgrades")):
        rows = read_rows(data_dir / fname)
        images = image_index(assets / folder)
        seen: set[str] = set()
        for r in rows:
            if r["id"] in seen:
                issues.append(f"{kind} id '{r['id']}' is duplicated")
            seen.add(r["id"])
            if r["id"] not in images:
                issues.append(f"{kind} '{r['id']}' has no image")
        ignore = {TITAN_BACK_STEM} if kind == "Titan" else set()
        for stem in sorted(set(images) - seen - ignore):
            issues.append(f"{kind} image '{stem}' has no metadata row")
    return issues
