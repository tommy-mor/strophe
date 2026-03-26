"""
JsonlStore — append-only typed event log. The file is the source of truth.
Consumers own their in-memory state by replaying events from read().

Usage:
    from evaleval import event, JsonlStore

    @event
    class Deposited:
        amount: str
        wallet: str
        timestamp_ms: int

    store = JsonlStore("/data/ledger.jsonl")

    # read from disk
    events = store.read()

    # append under write lock
    await store.append(Deposited(amount="1.0", wallet="abc", timestamp_ms=now))

    # atomic check-then-write under write lock (fn must be sync)
    def maybe_emit(events):
        if already_done(events):
            return None
        return Deposited(...)

    result = await store.atomic(maybe_emit)

    # migrate: transform raw dicts before deserialization (for schema evolution)
    def migrate(d):
        if d.get("type") == "old_name":
            d["type"] = "new_name"
        return d

    store = JsonlStore("/data/ledger.jsonl", migrate=migrate)
"""

import asyncio
import json
import pathlib
from dataclasses import dataclass, asdict, fields
from typing import Any, Callable, Optional

_registry: dict[str, type] = {}


def event(cls):
    """Decorator: make cls a frozen dataclass and register it for JSONL (de)serialization."""
    registered = dataclass(frozen=True)(cls)
    _registry[cls.__name__.lower()] = registered
    return registered


def to_dict(e: Any) -> dict:
    return {"type": type(e).__name__.lower(), **asdict(e)}


def from_dict(d: dict) -> Any | None:
    t = d.get("type", "")
    if t not in _registry:
        return None
    cls = _registry[t]
    valid = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in valid})


class JsonlStore:
    """
    Append-only JSONL event log. No in-memory cache — the file is the source of truth.

    read() reads from disk on every call. For large files called frequently,
    callers should cache the result themselves (e.g. in a Being or AppState object).

    - asyncio.Lock on append() and atomic() prevents concurrent writes.
    - atomic(fn): fn receives the current event list (read from disk) and returns
      an event or None. The read + fn + optional write happen under the lock.
      fn must be synchronous.
    - write_sync(e): sync write, no lock. Only safe before the event loop starts
      (e.g. during initialization).
    - migrate: optional callable applied to each raw dict during deserialization.
      Use for schema evolution (type renames, field renames, etc.).
    """

    def __init__(self, path: pathlib.Path | str, migrate: Optional[Callable[[dict], dict]] = None):
        self.path = pathlib.Path(path)
        self._lock = asyncio.Lock()
        self._migrate = migrate

    def _deserialize(self) -> list:
        """Read and deserialize the entire file from disk."""
        events = []
        if not self.path.exists():
            return events
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    if self._migrate:
                        d = self._migrate(d)
                    e = from_dict(d)
                    if e is not None:
                        events.append(e)
        return events

    def _write_sync(self, e: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(to_dict(e), default=str) + "\n")

    def write_sync(self, e: Any) -> None:
        """Sync write — only safe when no concurrent coroutines hold a reference to this store.
        Intended for initialization before an event loop is running."""
        self._write_sync(e)

    def read(self) -> list:
        """Read all events from disk and return them."""
        return self._deserialize()

    async def append(self, e: Any) -> None:
        """Append one event to the file under the write lock."""
        async with self._lock:
            self._write_sync(e)

    async def atomic(self, fn: Callable[[list], Any]) -> Any:
        """
        Under the write lock: read events from disk, call fn(events).
        If fn returns a non-None value, append it to the log.
        Returns whatever fn returns (event or None).
        fn must be synchronous — no awaits inside.
        """
        async with self._lock:
            events = self._deserialize()
            result = fn(events)
            if result is not None:
                self._write_sync(result)
            return result
