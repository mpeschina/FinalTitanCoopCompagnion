"""Builds the static card images and thumbnails served under /app/static/cards.

Run once after adding cards:  python -m presentation.build_static
"""
from __future__ import annotations

from finaltitan.catalog import load_catalog
from presentation.render import STATIC, build_all


def main() -> None:
    count = build_all(load_catalog())
    print(f"{count} card images ready in {STATIC / 'cards'}")


if __name__ == "__main__":
    main()
