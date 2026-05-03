import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_URI = os.environ["NEO4J_URI"]
_USER = os.environ["NEO4J_USER"]
_PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(_URI, auth=(_USER, _PASSWORD))
