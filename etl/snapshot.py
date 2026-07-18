#!/usr/bin/env python3
"""Recon: dump rendered HTML of each data-site page type to data/snapshots/.

Used once to learn the DOM structure before writing the real scraper.
"""
from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "https://otel-hackathon-data-site.vercel.app"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "snapshots"

PAGES = {
    "home.html": "/",
    "reservations_p1.html": "/reservations",
    "reservations_p2.html": "/reservations?page=2",
    "reference.html": "/reference",
    "verify.html": "/verify",
    "changelog.html": "/changelog",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for fname, path in PAGES.items():
            page.goto(BASE + path, wait_until="networkidle")
            page.wait_for_timeout(1500)
            OUT.joinpath(fname).write_text(page.content(), encoding="utf-8")
            print(f"saved {fname} ({len(page.content())} bytes) from {path}")

        # Grab a few detail pages: pull reservation links off the list page.
        page.goto(BASE + "/reservations", wait_until="networkidle")
        page.wait_for_timeout(1500)
        hrefs = page.eval_on_selector_all(
            "a[href*='/reservations/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        detail_hrefs = [h for h in hrefs if h and h.rstrip("/") != "/reservations"][:3]
        print("sample detail hrefs:", detail_hrefs)
        for i, href in enumerate(detail_hrefs, 1):
            page.goto(BASE + href, wait_until="networkidle")
            page.wait_for_timeout(1500)
            OUT.joinpath(f"detail_{i}.html").write_text(page.content(), encoding="utf-8")
            print(f"saved detail_{i}.html from {href}")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
