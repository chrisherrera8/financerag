"""Seed Company nodes and static relationships from config/companies.json."""

import json
from pathlib import Path

from graph.session import driver

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "companies.json"


def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def seed_companies(config: dict) -> None:
    with driver.session() as session:
        for company in config["companies"]:
            session.run(
                """
                MERGE (c:Company {ticker: $ticker})
                SET c.name = $name, c.sector = $sector, c.fiscal_year_end = $fiscal_year_end
                """,
                ticker=company["ticker"],
                name=company["name"],
                sector=company["sector"],
                fiscal_year_end=company["fiscal_year_end"],
            )


def seed_competitor_relationships(config: dict) -> None:
    with driver.session() as session:
        for rel in config["competitor_relationships"]:
            session.run(
                """
                MATCH (a:Company {ticker: $from_ticker})
                MATCH (b:Company {ticker: $to_ticker})
                MERGE (a)-[r:COMPETITOR_OF {segment: $segment}]->(b)
                """,
                from_ticker=rel["from"],
                to_ticker=rel["to"],
                segment=rel.get("segment"),
            )


def seed_subsidiary_relationships(config: dict) -> None:
    """Seed OWNS_SUBSIDIARY edges.

    Subsidiaries that are not in the five tracked companies are created as bare
    Company nodes (no sector/fiscal_year_end) so traversal queries still work.
    """
    with driver.session() as session:
        for rel in config["subsidiary_relationships"]:
            session.run(
                """
                MATCH (parent:Company {ticker: $parent_ticker})
                MERGE (sub:Company {name: $subsidiary_name})
                  ON CREATE SET sub.ticker = $subsidiary_name
                MERGE (parent)-[r:OWNS_SUBSIDIARY]->(sub)
                SET r.since_year = $since_year,
                    r.ownership_pct = $ownership_pct
                """,
                parent_ticker=rel["parent"],
                subsidiary_name=rel["subsidiary"],
                since_year=rel.get("since_year"),
                ownership_pct=rel.get("ownership_pct"),
            )


def seed_all() -> None:
    config = _load_config()
    seed_companies(config)
    seed_competitor_relationships(config)
    seed_subsidiary_relationships(config)


if __name__ == "__main__":
    seed_all()
    print("Neo4j seed data loaded.")
