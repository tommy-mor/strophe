import asyncio
import json
import pytest
from pathlib import Path

from evaleval.store import event, JsonlStore, to_dict, from_dict, _registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# @event decorator
# ---------------------------------------------------------------------------

@event
class Thing:
    value: str
    count: int = 0


@event
class Other:
    label: str


def test_event_creates_frozen_dataclass():
    t = Thing(value="x", count=1)
    assert t.value == "x"
    with pytest.raises(Exception):
        t.value = "y"  # frozen


def test_event_registers_by_lowercase_name():
    assert "thing" in _registry
    assert "other" in _registry


# ---------------------------------------------------------------------------
# to_dict / from_dict
# ---------------------------------------------------------------------------

def test_to_dict_includes_type_key():
    d = to_dict(Thing(value="hi", count=3))
    assert d == {"type": "thing", "value": "hi", "count": 3}


def test_from_dict_round_trips():
    original = Thing(value="hi", count=3)
    assert from_dict(to_dict(original)) == original


def test_from_dict_unknown_type_returns_none():
    assert from_dict({"type": "doesnotexist", "x": 1}) is None


def test_from_dict_ignores_extra_keys():
    d = {"type": "thing", "value": "x", "count": 0, "extra": "ignored"}
    assert from_dict(d) == Thing(value="x", count=0)


# ---------------------------------------------------------------------------
# JsonlStore — replay on init
# ---------------------------------------------------------------------------

def test_store_empty_on_missing_file(tmp_path):
    store = JsonlStore(tmp_path / "ledger.jsonl")
    assert store.read() == []


def test_store_replays_existing_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps(to_dict(Thing(value="a", count=1))) + "\n"
        + json.dumps(to_dict(Other(label="b"))) + "\n"
    )
    store = JsonlStore(path)
    events = store.read()
    assert events == [Thing(value="a", count=1), Other(label="b")]


def test_store_skips_unknown_types_on_replay(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps({"type": "ghost", "x": 1}) + "\n"
        + json.dumps(to_dict(Thing(value="kept", count=0))) + "\n"
    )
    store = JsonlStore(path)
    assert store.read() == [Thing(value="kept", count=0)]


def test_store_creates_parent_dirs(tmp_path):
    store = JsonlStore(tmp_path / "deep" / "nested" / "ledger.jsonl")
    run(store.append(Thing(value="x")))
    assert (tmp_path / "deep" / "nested" / "ledger.jsonl").exists()


# ---------------------------------------------------------------------------
# read() returns a snapshot (not the live list)
# ---------------------------------------------------------------------------

def test_read_returns_copy(tmp_path):
    store = JsonlStore(tmp_path / "l.jsonl")
    snapshot = store.read()
    snapshot.append(Thing(value="injected"))
    assert store.read() == []


# ---------------------------------------------------------------------------
# append()
# ---------------------------------------------------------------------------

def test_append_writes_to_file_and_cache(tmp_path):
    path = tmp_path / "l.jsonl"
    store = JsonlStore(path)
    run(store.append(Thing(value="hello", count=7)))

    assert store.read() == [Thing(value="hello", count=7)]
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"type": "thing", "value": "hello", "count": 7}


def test_append_accumulates(tmp_path):
    path = tmp_path / "l.jsonl"
    store = JsonlStore(path)
    run(store.append(Thing(value="a")))
    run(store.append(Other(label="b")))
    assert store.read() == [Thing(value="a", count=0), Other(label="b")]
    assert len(path.read_text().strip().splitlines()) == 2


# ---------------------------------------------------------------------------
# atomic()
# ---------------------------------------------------------------------------

def test_atomic_appends_when_fn_returns_event(tmp_path):
    store = JsonlStore(tmp_path / "l.jsonl")
    result = run(store.atomic(lambda events: Thing(value="new")))
    assert result == Thing(value="new", count=0)
    assert store.read() == [Thing(value="new", count=0)]


def test_atomic_does_not_append_when_fn_returns_none(tmp_path):
    store = JsonlStore(tmp_path / "l.jsonl")
    result = run(store.atomic(lambda events: None))
    assert result is None
    assert store.read() == []
    assert not (tmp_path / "l.jsonl").exists()


def test_atomic_fn_sees_current_state(tmp_path):
    store = JsonlStore(tmp_path / "l.jsonl")
    run(store.append(Thing(value="existing")))

    seen = []
    def capture(events):
        seen.extend(events)
        return None

    run(store.atomic(capture))
    assert seen == [Thing(value="existing", count=0)]


def test_atomic_guards_against_double_write(tmp_path):
    """Simulate epoch_loop pattern: only write if epoch not already present."""
    store = JsonlStore(tmp_path / "l.jsonl")

    def once(events):
        if any(e.value == "epoch-1" for e in events if isinstance(e, Thing)):
            return None
        return Thing(value="epoch-1")

    run(store.atomic(once))
    run(store.atomic(once))  # second call should be a no-op

    assert store.read() == [Thing(value="epoch-1", count=0)]
    assert len((tmp_path / "l.jsonl").read_text().strip().splitlines()) == 1


# ---------------------------------------------------------------------------
# new store instance replays what a previous one wrote
# ---------------------------------------------------------------------------

def test_new_store_replays_previous_writes(tmp_path):
    path = tmp_path / "l.jsonl"
    store1 = JsonlStore(path)
    run(store1.append(Thing(value="x", count=42)))

    store2 = JsonlStore(path)
    assert store2.read() == [Thing(value="x", count=42)]
