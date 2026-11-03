import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


class JsonStore[T]:
    """Transactional fixture state, isolated in one SQLite file per provider."""

    def __init__(self, path: Path, seed: Callable[[], T], decode: Callable[[str], T]):
        self.path = path
        self.decode = decode
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK (id=1), body TEXT NOT NULL)"
            )
            exists = connection.execute("SELECT 1 FROM state WHERE id=1").fetchone()
            if exists is None:
                connection.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(seed()),))

    @contextmanager
    def transaction(self) -> Iterator[T]:
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            connection.execute("BEGIN IMMEDIATE")
            original: str = connection.execute("SELECT body FROM state WHERE id=1").fetchone()[0]
            state = self.decode(original)
            yield state
            serialized = json.dumps(state, ensure_ascii=False)
            if serialized != original:
                connection.execute("UPDATE state SET body=? WHERE id=1", (serialized,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
