#!/usr/bin/env python3
"""Extract: scrape the data site into raw JSON files under data/raw/.

Outputs:
  data/raw/verify.json        — the /verify page's raw JSON (reconciliation targets)
  data/raw/reference.json     — all five reference tabs (lookup tables)
  data/raw/reservations.jsonl — one line per reservation: fields + stay_rows
  data/raw/meta.json          — anchor date, pages scraped, id list

Pages are client-rendered; every wait is on a data-testid selector, not a timer.
Any missing page or field is a hard failure — no silent row drops.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import Page, sync_playwright

BASE = "https://otel-hackathon-data-site.vercel.app"
RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"

# tab label -> a column header unique to that tab's table (rendered on demand)
REFERENCE_TABS = {
    "Room types": "number_of_rooms",
    "Markets": "market_name",
    "Channels": "channel_name",
    "Rate plans": "plan_family",
    "Macro history": "valid_from",
}


def parse_visible_table(page: Page) -> list[dict[str, str]]:
    """Parse the currently rendered table in <main> into a list of dicts."""
    return page.evaluate(
        """() => {
            const table = document.querySelector('main table');
            if (!table) return null;
            const heads = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
            return [...table.querySelectorAll('tbody tr')].map(tr => {
                const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                return Object.fromEntries(heads.map((h, i) => [h, cells[i] ?? null]));
            });
        }"""
    )


def scrape_verify(page: Page) -> dict:
    page.goto(f"{BASE}/verify", wait_until="domcontentloaded")
    pre = page.wait_for_selector(
        '[data-testid="checksums-json"]', state="attached", timeout=30_000
    )
    data = json.loads(pre.text_content())
    for key in ("anchor_date", "dataset_revision", "total_reservations", "total_stay_rows"):
        if key not in data:
            raise RuntimeError(f"/verify JSON missing {key}")
    return data


def scrape_reference(page: Page) -> dict[str, list[dict]]:
    page.goto(f"{BASE}/reference", wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="reference-page"]', timeout=30_000)
    tables: dict[str, list[dict]] = {}
    for tab, marker_col in REFERENCE_TABS.items():
        page.get_by_role("tab", name=tab).click()
        page.wait_for_selector(f'main table th:text-is("{marker_col}")', timeout=30_000)
        page.wait_for_selector("main table tbody tr", timeout=30_000)
        rows = parse_visible_table(page)
        if not rows:
            raise RuntimeError(f"reference tab {tab!r} rendered no rows")
        tables[tab] = rows
        print(f"  reference tab {tab!r}: {len(rows)} rows")
    return tables


def scrape_reservation_ids(page: Page) -> tuple[list[str], int]:
    page.goto(f"{BASE}/reservations", wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="reservations-table"]', timeout=30_000)
    indicator = page.locator('[data-testid="page-indicator"]').text_content()
    m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", indicator or "")
    if not m:
        raise RuntimeError(f"cannot parse page indicator: {indicator!r}")
    total_pages = int(m.group(2))

    ids: list[str] = []
    for page_no in range(1, total_pages + 1):
        page.wait_for_selector('[data-testid="page-indicator"]:has-text("Page %d of")' % page_no, timeout=30_000)
        page_ids = page.evaluate(
            """() => [...document.querySelectorAll('[data-testid^="detail-link-"]')]
                    .map(a => a.getAttribute('data-testid').replace('detail-link-', ''))"""
        )
        if not page_ids:
            raise RuntimeError(f"list page {page_no} rendered no reservation links")
        ids.extend(page_ids)
        print(f"  list page {page_no}/{total_pages}: {len(page_ids)} reservations")
        if page_no < total_pages:
            page.locator('[data-testid="next-page"]').click()

    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate reservation ids across list pages")
    return ids, total_pages


def scrape_detail(page: Page, rid: str) -> tuple[dict, Page]:
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            if attempt:
                page.wait_for_timeout(2_000 * attempt)  # backoff before retry
            page.goto(f"{BASE}/reservations/{rid}",
                      wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector('[data-testid="reservation-fields"]', timeout=30_000)
            record = page.evaluate(
                """() => {
                    const fields = {};
                    document.querySelectorAll('[data-testid="reservation-fields"] [data-field]')
                        .forEach(div => {
                            fields[div.getAttribute('data-field')] =
                                div.querySelector('dd').textContent.trim();
                        });
                    const table = document.querySelector('[data-testid="stay-rows-table"]');
                    const heads = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
                    const stay_rows = [...table.querySelectorAll('tbody tr')].map(tr => {
                        const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                        return Object.fromEntries(heads.map((h, i) => [h, cells[i] ?? null]));
                    });
                    return { fields, stay_rows };
                }"""
            )
            if not record["fields"] or not record["stay_rows"]:
                raise RuntimeError(f"{rid}: empty fields or stay rows")
            record["reservation_id"] = rid
            return record, page
        except Exception as exc:  # noqa: BLE001 — retry then re-raise
            last_err = exc
            try:  # a hung navigation can wedge the page — start fresh
                context = page.context
                page.close()
                page = context.new_page()
            except Exception:
                pass
    raise RuntimeError(f"failed to scrape detail page {rid}") from last_err


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        # Skip images/fonts for speed (context-level: survives page recreation).
        context.route(
            re.compile(r"\.(png|jpg|jpeg|svg|woff2?|ico)(\?|$)"),
            lambda route: route.abort(),
        )
        page = context.new_page()

        print("scraping /verify ...")
        verify = scrape_verify(page)
        print(f"  anchor_date={verify['anchor_date']} revision={verify['dataset_revision']} "
              f"reservations={verify['total_reservations']} stay_rows={verify['total_stay_rows']}")

        # Resume support: keep already-scraped details only if they belong to
        # the same anchor date + dataset revision (the dataset regenerates daily).
        out = RAW / "reservations.jsonl"
        done: set[str] = set()
        prior_verify = RAW / "verify.json"
        if out.exists() and prior_verify.exists():
            prior = json.loads(prior_verify.read_text())
            if (prior.get("anchor_date"), prior.get("dataset_revision")) == (
                verify["anchor_date"], verify["dataset_revision"]
            ):
                with out.open(encoding="utf-8") as fh:
                    done = {json.loads(line)["reservation_id"] for line in fh if line.strip()}
                print(f"  resuming: {len(done)} details already scraped")
        if not done and out.exists():
            out.unlink()
        (RAW / "verify.json").write_text(json.dumps(verify, indent=2))

        print("scraping /reference ...")
        reference = scrape_reference(page)

        print("scraping reservation list ...")
        ids, total_pages = scrape_reservation_ids(page)
        if len(ids) != verify["total_reservations"]:
            raise RuntimeError(
                f"list scrape found {len(ids)} ids but /verify says {verify['total_reservations']}"
            )

        todo = [rid for rid in ids if rid not in done]
        print(f"scraping {len(todo)} detail pages ({len(done)} already done) ...")
        with out.open("a", encoding="utf-8") as fh:
            for i, rid in enumerate(todo, 1):
                record, page = scrape_detail(page, rid)
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}")
        browser.close()

    (RAW / "reference.json").write_text(json.dumps(reference, indent=2))
    (RAW / "meta.json").write_text(json.dumps({
        "anchor_date": verify["anchor_date"],
        "dataset_revision": verify["dataset_revision"],
        "scraped_at": scraped_at,
        "source_url": BASE,
        "pages_scraped": total_pages,
        "reservation_ids": ids,
    }, indent=2))
    print("extract complete.")


if __name__ == "__main__":
    sys.exit(main())
