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

## Environment Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python package management
- [podman-compose](https://github.com/containers/podman-compose) for running containers

### Python dependencies

```bash
uv venv
uv pip install -r requirements.txt
```

### Database (Postgres + pgvector + pgAdmin)

Start the services:

```bash
podman-compose up -d
```

| Service | URL | Credentials |
|---|---|---|
| Postgres | `localhost:5432` | user: `financerag` / pass: `financerag` / db: `financerag` |
| pgAdmin | http://localhost:5050 | email: `admin@financerag.local` / pass: `admin` |

To connect pgAdmin to the database after first login: add a new server with host `postgres`, port `5432`, and the credentials above.

Stop and remove containers (data volumes are preserved):

```bash
podman-compose down
```

To also wipe all stored data:

```bash
podman-compose down -v
```

## Scripts

See [`scripts/README.md`](scripts/README.md) for documentation on the available scripts.
