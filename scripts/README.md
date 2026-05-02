# Scripts

## `download_filings.py`

Downloads SEC EDGAR filings for all configured companies into `data/`.

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
