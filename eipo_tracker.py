#!/usr/bin/env python3
"""Daily e-IPO tracker: scrape e-ipo.co.id pipeline, diff vs snapshot, print report.

Usage:
  eipo_tracker.py            # diff vs snapshot, print changes (empty diff -> "NO_CHANGES")
  eipo_tracker.py --baseline # (re)build snapshot from current data, print summary

Exit 0 always; output is the report for the cron worker.
State: snapshot.json next to this script.
"""
import html as htmllib
import json
import os
import re
import sys
import urllib.request

BASE = "https://www.e-ipo.co.id"
LIST_URL = BASE + "/id/ipo/index?page={page}&per-page=12&view=list"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(HERE, "snapshot.json")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return htmllib.unescape(re.sub(r"\s+", " ", s or "")).strip()


def parse_list(html):
    """Return list of dicts from one list-view page."""
    items = []
    # split on item containers
    blocks = re.split(r'<div data-key="(\d+)">', html)
    # blocks[0] is pre-first-item; then alternating key, body
    for i in range(1, len(blocks), 2):
        key, body = blocks[i], blocks[i + 1]
        # cut body at next item start (already split) - body runs to end of blocks[i+1]
        m = re.search(r"<h3[^>]*>(.*?)</h3>", body, re.S)
        if not m:
            continue
        h3 = m.group(1)
        status_m = re.search(r'<p class="fright[^>]*>([^<]*)</p>', h3)
        status = clean(status_m.group(1)) if status_m else ""
        name_raw = clean(re.sub(r"<p.*", "", h3, flags=re.S))
        # "PT Swayasa Prakarsa Tbk (SWAP-C1)" -> name, ticker
        tm = re.search(r"\(([^)]+)\)\s*$", name_raw)
        ticker = tm.group(1).strip() if tm else ""
        name = re.sub(r"\s*\([^)]+\)\s*$", "", name_raw).strip()

        def field(label):
            fm = re.search(
                r"<h5[^>]*>\s*" + re.escape(label) + r"\s*</h5>\s*<p[^>]*>(.*?)</p>",
                body, re.S | re.I)
            return clean(re.sub(r"<[^>]+>", "", fm.group(1))) if fm else ""

        syariah = "Syariah" if re.search(r">Syariah<", body) else ""
        dm = re.search(r'href="(/id/ipo/' + key + r'/[^"]+)"', body)
        detail = BASE + dm.group(1) if dm else ""
        items.append({
            "id": key,
            "name": name,
            "ticker": ticker,
            "status": status,
            "sector": field("Sektor"),
            "syariah": syariah,
            "book_building": field("Periode Book Building"),
            "price_range": field("Rentang Harga Book Building"),
            "shares_offered": field("Saham Ditawarkan"),
            "detail_url": detail,
        })
    return items


def parse_detail(html):
    """Underwriter + listing date from a detail page."""
    txt = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    txt = re.sub(r"<style.*?</style>", "", txt, flags=re.S)
    txt = re.sub(r"<[^>]+>", "|", txt)
    txt = htmllib.unescape(txt)
    txt = re.sub(r"\|+", "|", txt)
    out = {}
    m = re.search(r"Penjamin Emisi Efek[^|]*\|\s*([^|]+)", txt)
    if m:
        out["underwriter"] = clean(m.group(1))
    m = re.search(r"Tanggal Pencatatan\s*\|\s*([^|]+)", txt)
    if m:
        out["listing_date"] = clean(m.group(1))
    m = re.search(r"Jumlah Saham Ditawarkan\s*\|\s*([^|]+)", txt)
    if m:
        out["shares_detail"] = clean(m.group(1))
    return out


def scrape_all(max_pages=40):
    all_items = {}
    for page in range(1, max_pages + 1):
        try:
            items = parse_list(fetch(LIST_URL.format(page=page)))
        except Exception as e:
            print(f"WARN: page {page} fetch failed: {e}", file=sys.stderr)
            break
        if not items:
            break
        for it in items:
            all_items[it["id"]] = it
    return all_items


def load_snapshot():
    if os.path.exists(SNAPSHOT):
        with open(SNAPSHOT) as f:
            return json.load(f)
    return {}


def save_snapshot(data):
    with open(SNAPSHOT, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def enrich(item):
    """Fetch detail page for underwriter/listing date. Best-effort."""
    if not item.get("detail_url"):
        return
    try:
        item.update(parse_detail(fetch(item["detail_url"])))
    except Exception as e:
        print(f"WARN: detail {item['id']} failed: {e}", file=sys.stderr)


def fmt(item):
    bits = [f"{item['name']} ({item['ticker']})"]
    if item.get("sector"):
        bits.append(item["sector"])
    if item.get("syariah"):
        bits.append("Syariah")
    if item.get("price_range"):
        bits.append(item["price_range"])
    if item.get("book_building"):
        bits.append("BB: " + item["book_building"])
    if item.get("underwriter"):
        bits.append("UW: " + item["underwriter"])
    if item.get("listing_date"):
        bits.append("listing " + item["listing_date"])
    s = " | ".join(bits)
    if item.get("detail_url"):
        s += f"\n  {item['detail_url']}"
    return s


def main():
    baseline = "--baseline" in sys.argv
    current = scrape_all()
    if not current:
        print("ERROR: no data scraped", file=sys.stderr)
        sys.exit(1)
    old = load_snapshot()

    if baseline or not old:
        save_snapshot(current)
        ACTIVE = {"pre-effective", "book building", "offering", "allotment",
                  "waiting for offering"}
        active = [it for it in current.values()
                  if it["status"].lower() in ACTIVE]
        for it in active:
            enrich(it)
        save_snapshot(current)  # persist enrichment
        print(f"BASELINE: tracking {len(current)} IPOs "
              f"({len(active)} active). Snapshot saved.")
        if active:
            print("\nCurrently active pipeline:")
            for it in sorted(active, key=lambda x: x["id"]):
                print("- " + fmt(it))
        return

    new_ids = [i for i in current if i not in old]
    changed = []
    for i in current:
        if i in old:
            o, n = old[i], current[i]
            diffs = [k for k in ("status", "book_building", "price_range",
                                 "shares_offered", "ticker", "name")
                     if o.get(k) != n.get(k)]
            if diffs:
                changed.append((o, n, diffs))

    for i in new_ids:
        enrich(current[i])
    for _, n, _ in changed:
        enrich(n)
    save_snapshot(current)

    if not new_ids and not changed:
        print("NO_CHANGES")
        return

    print(f"E-IPO update {len(new_ids)} new, {len(changed)} changed "
          f"(tracking {len(current)} total)\n")
    for i in sorted(new_ids):
        print("NEW: " + fmt(current[i]))
    for o, n, diffs in changed:
        d = ", ".join(f"{k}: {o.get(k) or '-'} -> {n.get(k) or '-'}" for k in diffs)
        print(f"CHANGED [{n['ticker'] or n['id']}]: {d}")


if __name__ == "__main__":
    main()
