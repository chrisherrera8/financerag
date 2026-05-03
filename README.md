# financerag

A dataset of SEC EDGAR filings for 5 major public companies, intended as a knowledge base for testing a RAG (Retrieval-Augmented Generation) system.

## Data

Filings are downloaded from [SEC EDGAR](https://www.sec.gov/developer) and stored locally under `data/`. The repository does not include the data — see [`scripts/README.md`](scripts/README.md) to download it.

Once downloaded, files are organized as:

```
data/<company>/<FORM_TYPE>/<accession-number>/<filename>.htm
```

**Form types:**
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

### Services (Postgres + pgvector + Neo4j + pgAdmin)

Start all services:

```bash
podman-compose up -d
```

| Service | URL | Credentials |
|---|---|---|
| Postgres | `localhost:5432` | user: `financerag` / pass: `financerag` / db: `financerag` |
| pgAdmin | http://localhost:5050 | email: `admin@financerag.local` / pass: `admin` |
| Neo4j Browser | http://localhost:7474 | user: `neo4j` / pass: `financerag` |
| Neo4j Bolt | `bolt://localhost:7687` | same credentials |

To connect pgAdmin to the database after first login: add a new server with host `postgres`, port `5432`, and the credentials above.

Stop and remove containers (data volumes are preserved):

```bash
podman-compose down
```

To also wipe all stored data:

```bash
podman-compose down -v
```

### Run Postgres migrations

With the database running, apply all schema migrations:

```bash
uv run alembic upgrade head
```

### Initialize Neo4j schema and seed data

With Neo4j running, apply constraints/indexes and load static company and relationship data:

```bash
uv run python scripts/init_neo4j.py
```

This creates uniqueness constraints and indexes for all node labels, seeds the five `Company` nodes, and seeds `COMPETITOR_OF` and `OWNS_SUBSIDIARY` relationships from `config/companies.json`. The script is idempotent — safe to re-run.

## Scripts

See [`scripts/README.md`](scripts/README.md) for documentation on the available scripts.
