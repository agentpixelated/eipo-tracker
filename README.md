# eipo-tracker

Daily tracker for Indonesian IPOs, scraped from [e-ipo.co.id](https://www.e-ipo.co.id)
(IDX electronic IPO system). Built for hunting new IPO opportunities: it watches
the pipeline every day and reports only what's new or changed.

## What it tracks

- **New pipeline entries** — a company appearing on e-ipo.co.id for the first time
- **Status changes** — e.g. moving into Book Building, Offering, or Allotment
- **New/changed price ranges** — book-building price range announcements

Each new or changed IPO is enriched with underwriter (*Penjamin Emisi*) and
listing date (*Tanggal Pencatatan*) from its detail page.

## Usage

No dependencies — Python 3 standard library only.

```bash
# First run: build the baseline snapshot (251 IPOs as of Oct 2026)
python3 eipo_tracker.py --baseline

# Daily run: diff against the snapshot, print changes (or NO_CHANGES)
python3 eipo_tracker.py
```

State lives in `snapshot.json` next to the script (created on first run,
git-ignored by convention — don't commit your local snapshot).

## Scheduling

Example cron (daily 07:00 Asia/Jakarta, alert only on changes):

```cron
0 7 * * * python3 /path/to/eipo_tracker.py
```

## Notes

- The pipeline can be empty for stretches (all historical IPOs show as
  Closed/Canceled) — that's normal; the tracker is armed for the next window.
- Be polite: the script fetches ~21 list pages plus detail pages only for
  new/changed items.

Data source: public pages of e-ipo.co.id. Not affiliated with IDX.
