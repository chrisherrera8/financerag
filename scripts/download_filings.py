"""
Bulk download SEC EDGAR filings for major public companies.

Storage layout:
  data/<company_slug>/<FORM_TYPE>/<accession-number>/<primary-document>

EDGAR rate limit: 10 req/sec — we stay at ~8 req/sec (0.12 s delay).
User-Agent header is required; omitting it results in blocks.
"""

import json
import time
import re
import sys
from pathlib import Path
import urllib.request
import urllib.error

# ── config ────────────────────────────────────────────────────────────────────

COMPANIES = [
    {"name": "Apple",             "slug": "apple",     "cik": "0000320193"},
    {"name": "Microsoft",         "slug": "microsoft", "cik": "0000789019"},
    {"name": "Amazon",            "slug": "amazon",    "cik": "0001018724"},
    {"name": "Alphabet (Google)", "slug": "alphabet",  "cik": "0001652044"},
    {"name": "Berkshire Hathaway","slug": "berkshire", "cik": "0001067983"},
]

USER_AGENT = "financerag-test chris88herrera@gmail.com"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"

TARGET_FORMS = {"10-K", "10-Q", "8-K", "DEF 14A"}
MAX_PER_FORM = None         # set to an int to cap per form type per company

# Only download filings on or after this date (YYYY-MM-DD).
EARLIEST_DATE = "2015-01-01"

OUTPUT_DIR = Path("data")
DELAY = 0.12                # seconds between HTTP requests (~8 req/sec)

# ── helpers ───────────────────────────────────────────────────────────────────

def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", s)


# ── core ──────────────────────────────────────────────────────────────────────

def fetch_all_submissions(cik: str) -> dict:
    url = f"{SUBMISSIONS_BASE}/CIK{cik}.json"
    data = json.loads(get(url))
    time.sleep(DELAY)

    combined = data["filings"]["recent"]
    for extra in data["filings"].get("files", []):
        page_url = f"{SUBMISSIONS_BASE}/{extra['name']}"
        print(f"  Fetching older page: {extra['filingFrom']} → {extra['filingTo']}")
        page = json.loads(get(page_url))
        time.sleep(DELAY)
        for key in combined:
            combined[key] = combined[key] + page[key]

    return combined


def collect_filings(recent: dict) -> list[dict]:
    keys = ["accessionNumber", "filingDate", "form", "primaryDocument"]
    rows = list(zip(*[recent[k] for k in keys]))

    buckets: dict[str, list] = {f: [] for f in TARGET_FORMS}
    for acc, date, form, primary in rows:
        if form not in TARGET_FORMS:
            continue
        if EARLIEST_DATE and date < EARLIEST_DATE:
            continue
        bucket = buckets[form]
        if MAX_PER_FORM is not None and len(bucket) >= MAX_PER_FORM:
            continue
        bucket.append({"accession": acc, "date": date, "form": form, "primary": primary})

    return [filing for bucket in buckets.values() for filing in bucket]


def download_filing(filing: dict, company_dir: Path, cik_bare: str) -> None:
    acc_nodash = filing["accession"].replace("-", "")
    out_dir = company_dir / sanitize(filing["form"]) / filing["accession"]
    out_dir.mkdir(parents=True, exist_ok=True)

    primary = filing["primary"]
    if not primary:
        print("  [skip] no primary document listed")
        return

    out_path = out_dir / primary
    if out_path.exists():
        print(f"  [skip] {primary}")
        return

    url = f"{ARCHIVE_BASE}/{cik_bare}/{acc_nodash}/{primary}"
    try:
        content = get(url)
        time.sleep(DELAY)
        out_path.write_bytes(content)
        print(f"  [ok]   {primary} ({len(content):,} bytes)")
    except urllib.error.HTTPError as e:
        print(f"  [warn] {primary} — HTTP {e.code}")


def process_company(company: dict) -> None:
    cik = company["cik"]
    cik_bare = str(int(cik))
    company_dir = OUTPUT_DIR / company["slug"]
    company_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  {company['name']}  (CIK {cik})")
    print(f"{'='*60}")

    recent = fetch_all_submissions(cik)
    filings = collect_filings(recent)

    counts = {}
    for f in filings:
        counts[f["form"]] = counts.get(f["form"], 0) + 1
    print(f"  Found {len(filings)} filings: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print()

    for i, filing in enumerate(filings, 1):
        print(f"  [{i}/{len(filings)}] {filing['form']:<10} {filing['date']}  {filing['accession']}")
        download_filing(filing, company_dir, cik_bare)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output : {OUTPUT_DIR.resolve()}")
    print(f"Period : {EARLIEST_DATE} → present")
    print(f"Forms  : {', '.join(sorted(TARGET_FORMS))}")

    for company in COMPANIES:
        process_company(company)

    print(f"\n{'='*60}")
    print("All done.")


if __name__ == "__main__":
    sys.exit(main())
