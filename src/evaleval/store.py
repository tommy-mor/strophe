"""
JsonlStore — append-only typed event log with in-memory cache and asyncio write lock.

Usage:
    from evaleval import event, JsonlStore

    @event
    class Deposited:
        amount: str
        wallet: str
        timestamp_ms: int

    store = JsonlStore("/data/ledger.jsonl")

    # read (in-memory, no I/O)
    events = store.read()

    # append under write lock
    await store.append(Deposited(amount="1.0", wallet="abc", timestamp_ms=now))

    # atomic check-then-write under write lock (fn must be sync)
    def maybe_emit(events):
        if already_done(events):
            return None
        return Deposited(...)

    result = await store.atomic(maybe_emit)
"""

import asyncio
import json
import pathlib
from dataclasses import dataclass, asdict, fields
from typing import Any, Callable

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
    Append-only JSONL event log.
    - In-memory cache: read() is O(1), no file I/O.
    - asyncio.Lock hidden internally: append() and atomic() are safe across coroutines.
    - atomic(fn): fn receives the current event list and returns an event or None.
      The read + fn + optional write happen under the lock, so fn sees a consistent
      snapshot and no other writer can interleave. fn must be synchronous.
    """

    def __init__(self, path: pathlib.Path | str):
        self.path = pathlib.Path(path)
        self._lock = asyncio.Lock()
        self._events: list = []
        self._replay()

    def _replay(self) -> None:
        if not self.path.exists():
            return
        with open(self.path) as f:
            for line in f:
                if line.strip():
                    e = from_dict(json.loads(line))
                    if e is not None:
                        self._events.append(e)

    def _write_sync(self, e: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(to_dict(e), default=str) + "\n")

    def read(self) -> list:
        """Return a snapshot of all events. In-memory — no I/O."""
        return list(self._events)

    async def append(self, e: Any) -> None:
        """Append one event to the file and cache under the write lock."""
        async with self._lock:
            self._write_sync(e)
            self._events.append(e)

    async def atomic(self, fn: Callable[[list], Any]) -> Any:
        """
        Under the write lock: call fn(current_events).
        If fn returns a non-None value, append it to the log and cache.
        Returns whatever fn returns (event or None).
        fn must be synchronous — no awaits inside.
        """
        async with self._lock:
            result = fn(self._events)
            if result is not None:
                self._write_sync(result)
                self._events.append(result)
            return result
