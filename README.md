# financerag

A dataset of SEC EDGAR filings for 5 major public companies, intended as a knowledge base for testing a RAG (Retrieval-Augmented Generation) system.

## Data

**747 MB** of HTML filings across 5 companies, covering **2015–2026**.

| Company | Folder |
|---|---|
| Apple | `data/apple/` |
| Microsoft | `data/microsoft/` |
| Amazon | `data/amazon/` |
| Alphabet (Google) | `data/alphabet/` |
| Berkshire Hathaway | `data/berkshire/` |

Each company folder is organized as:

```
data/<company>/<FORM_TYPE>/<accession-number>/<filename>.htm
```

**Form types included:**
- `10-K` — Annual report (full year financials + MD&A)
- `10-Q` — Quarterly report (Q1, Q2, Q3)
- `8-K` — Current report (material events, filed as they happen)
- `DEF_14A` — Proxy statement (executive compensation, board votes)

## Scripts

### `scripts/download_filings.py`

Downloads filings from the [SEC EDGAR API](https://www.sec.gov/developer) for all configured companies.

**Usage:**
```bash
python scripts/download_filings.py
```

Already-downloaded files are skipped automatically, so re-running is safe.

**Key settings at the top of the script:**

| Variable | Default | Description |
|---|---|---|
| `COMPANIES` | 5 companies | List of `{name, slug, cik}` dicts — add/remove companies here |
| `EARLIEST_DATE` | `"2015-01-01"` | How far back to go |
| `TARGET_FORMS` | 10-K, 10-Q, 8-K, DEF 14A | Which filing types to download |
| `MAX_PER_FORM` | `None` | Cap per form type per company (`None` = no limit) |

**EDGAR API rules followed:**
- `User-Agent` header set (required by EDGAR)
- Max ~8 requests/sec (EDGAR limit is 10)
- No authentication required
