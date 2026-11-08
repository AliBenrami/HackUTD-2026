"""Document store for swings, bags, hole notes, and caddie runs.

MongoDB Atlas is used when MONGODB_URI is set. Otherwise the same documents
are kept in a local JSON file so the phone still works.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class DocumentStore:
    def kind(self) -> str:
        raise NotImplementedError

    def replace(self, collection: str, key: dict, document: dict) -> dict:
        raise NotImplementedError

    def find(self, collection: str, query: dict) -> list[dict]:
        raise NotImplementedError

    def delete(self, collection: str, query: dict) -> int:
        raise NotImplementedError


def matches(document: dict, query: dict) -> bool:
    for key, expected in query.items():
        value = document.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and value == expected["$ne"]:
                return False
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
        elif value != expected:
            return False
    return True


class FileStore(DocumentStore):
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")

    def kind(self) -> str:
        return "file"

    def _read(self) -> dict[str, list]:
        try:
            data = json.loads(self.path.read_text() or "{}")
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data))

    def replace(self, collection: str, key: dict, document: dict) -> dict:
        with self._lock:
            data = self._read()
            rows = [row for row in data.get(collection, []) if not matches(row, key)]
            stored = {**document}
            rows.append(stored)
            data[collection] = rows
            self._write(data)
        return stored

    def find(self, collection: str, query: dict) -> list[dict]:
        with self._lock:
            return [row for row in self._read().get(collection, []) if matches(row, query)]

    def delete(self, collection: str, query: dict) -> int:
        with self._lock:
            data = self._read()
            rows = data.get(collection, [])
            kept = [row for row in rows if not matches(row, query)]
            data[collection] = kept
            self._write(data)
            return len(rows) - len(kept)


class MongoStore(DocumentStore):
    def __init__(self, database: Any):
        self.database = database
        database["hole_notes"].create_index([("userId", 1), ("savedAt", -1)])
        database["swings"].create_index([("userId", 1), ("videoId", 1)], unique=True)
        database["bags"].create_index("userId", unique=True)

    def kind(self) -> str:
        return "mongo"

    def replace(self, collection: str, key: dict, document: dict) -> dict:
        stored = {key: value for key, value in document.items() if key != "_id"}
        self.database[collection].replace_one(key, stored, upsert=True)
        return stored

    def find(self, collection: str, query: dict) -> list[dict]:
        rows = []
        for row in self.database[collection].find(query, {"_id": 0}):
            rows.append(row)
        return rows

    def delete(self, collection: str, query: dict) -> int:
        return self.database[collection].delete_many(query).deleted_count

    def aggregate(self, collection: str, pipeline: list) -> list:
        return list(self.database[collection].aggregate(pipeline))


_store: DocumentStore | None = None


def open_store() -> DocumentStore:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if uri:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        return MongoStore(client["golfar"])
    path = Path(os.environ.get("GOLF_STORE_PATH", Path(__file__).resolve().parents[1] / "data" / "golfar.json"))
    return FileStore(path)


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = open_store()
    return _store


def set_store(store: DocumentStore | None) -> None:
    global _store
    _store = store
