"""Thin wrapper around the Neo4j driver."""
from __future__ import annotations

from typing import Any, Callable

from ..config import Settings


class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    @classmethod
    def from_settings(cls, s: Settings) -> "Neo4jClient":
        s.require_neo4j()
        return cls(s.neo4j_uri, s.neo4j_username, s.neo4j_password, s.neo4j_database)

    def verify(self) -> None:
        self._driver.verify_connectivity()

    def write(self, work: Callable[[Any], Any]) -> Any:
        """Run `work(tx)` in one managed write transaction (atomic, retried on transient errors)."""
        with self._driver.session(database=self.database) as session:
            return session.execute_write(work)

    def execute(self, query: str, **params: Any) -> None:
        self.write(lambda tx: tx.run(query, **params).consume())

    def read(self, query: str, **params: Any) -> list[dict]:
        def work(tx):
            return [r.data() for r in tx.run(query, **params)]

        with self._driver.session(database=self.database) as session:
            return session.execute_read(work)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
