"""Initialize Neo4j schema and seed static relationship data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph.schema import init_schema
from graph.seed import seed_all

if __name__ == "__main__":
    print("Applying Neo4j schema constraints and indexes...")
    init_schema()
    print("Seeding company nodes and static relationships...")
    seed_all()
    print("Done.")
