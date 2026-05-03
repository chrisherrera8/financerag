"""Apply Neo4j constraints and indexes for all node labels."""

from graph.session import driver

# Uniqueness constraints also create an index on the constrained property.
_CONSTRAINTS = [
    ("Company", "ticker"),
    ("Filing", "accession_number"),
    ("Section", "section_id"),
    ("Chunk", "chunk_id"),
]

# Composite / secondary indexes for query patterns.
_INDEXES = [
    ("TimePeriod", ["fiscal_year", "fiscal_quarter"]),
    ("Filing", ["fiscal_year", "fiscal_quarter"]),
    ("Filing", ["filing_type"]),
]


def init_schema() -> None:
    with driver.session() as session:
        for label, prop in _CONSTRAINTS:
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_{prop}_unique IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )
        for label, props in _INDEXES:
            index_name = f"{label.lower()}_{'_'.join(props)}_idx"
            props_cypher = ", ".join(f"n.{p}" for p in props)
            session.run(
                f"CREATE INDEX {index_name} IF NOT EXISTS "
                f"FOR (n:{label}) ON ({props_cypher})"
            )


if __name__ == "__main__":
    init_schema()
    print("Neo4j schema initialized.")
