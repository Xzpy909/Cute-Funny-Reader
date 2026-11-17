"""Progress / edits / favourites live in SQLite; the old JSON files are moved in once."""
import json

from app import library as L
from app.store import Db, Store


def test_old_json_is_moved_in_once(tmp_path):
    (tmp_path / "progress.json").write_text(json.dumps({"abc": {"page": 3, "frac": .5}}), "utf-8")
    s = Store(Db.at(tmp_path / "reader.db"), "progress", tmp_path / "progress.json")
    assert s.get("abc") == {"page": 3, "frac": .5}
    assert not (tmp_path / "progress.json").exists()                     # kept aside as a backup …
    assert (tmp_path / "progress.json.before-database").exists()
    (tmp_path / "progress.json").write_text(json.dumps({"zzz": {}}), "utf-8")   # … and never imported twice
    s2 = Store(Db.at(tmp_path / "reader.db"), "progress", tmp_path / "progress.json")
    assert set(s2.all()) == {"abc"}


def test_survives_a_restart(tmp_path):
    db = Db.at(tmp_path / "reader.db")
    s = Store(db, "progress")
    s.put("a", {"page": 1}); s.put_many({"b": {"done": True}, "c": {"seen": True}}); s.delete("c")
    db.close()                                                           # like stopping the container
    s = Store(Db.at(tmp_path / "reader.db"), "progress")
    assert s.all() == {"a": {"page": 1}, "b": {"done": True}}


def test_stores_dont_mix(tmp_path):
    db = Db.at(tmp_path / "reader.db")
    Store(db, "progress").put("x", 1)
    assert Store(db, "edits").all() == {}


def test_a_broken_old_file_doesnt_stop_the_app(tmp_path):
    (tmp_path / "edits.json").write_text("{not json", "utf-8")
    s = Store(Db.at(tmp_path / "reader.db"), "edits", tmp_path / "edits.json")
    assert s.all() == {}
    assert (tmp_path / "edits.json").exists()                            # left alone for a human to look at


def test_library_uses_the_database(lib):
    lib.progress.put("book1", {"page": 2})
    assert (L.CONFIG_DIR / "reader.db").exists()
    assert not (L.CONFIG_DIR / "progress.json").exists()
