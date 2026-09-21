"""Minimal structural database ports used by management persistence adapters."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeAlias

DatabaseRow: TypeAlias = tuple[object, ...]
SqlParams: TypeAlias = tuple[object, ...]


class QueryResult(Protocol):
    def fetchone(self) -> DatabaseRow | None: ...

    def fetchall(self) -> list[DatabaseRow]: ...


class DatabaseConnection(Protocol):
    def execute(self, query: str, params: SqlParams = ()) -> QueryResult: ...

    def transaction(self) -> AbstractContextManager[object]: ...

    def close(self) -> None: ...


ConnectionFactory: TypeAlias = Callable[..., DatabaseConnection]
