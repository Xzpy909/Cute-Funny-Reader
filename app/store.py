"""The app's own data — reading progress, metadata edits, favourites — in one SQLite file (config/reader.db).

Why not the old JSON files: every save rewrote a whole file (a page turn rewrote all reading progress; renaming
a collection rewrote it about twice per book). Here a save writes one row.

Each store keeps an in-memory copy for reads (as fast as the JSON version was) and writes through to SQLite.
The classic rollback journal is used, not WAL: /config is usually a Windows/macOS folder shared into Docker,
where WAL's shared-memory file isn't reliable. Only this one process ever opens the database.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger("cfreader")

SCHEMA_VERSION = 1


class Db:
    """One connection per database file, shared by every store; a lock keeps threads from interleaving."""
    _open: dict[str, "Db"] = {}
    _open_lock = threading.Lock()

    @classmethod
    def at(cls, path: Path) -> "Db":
        key = str(Path(path).resolve())
        with cls._open_lock:
            db = cls._open.get(key)
            if db is None:
                db = cls._open[key] = cls(Path(path))
            return db

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.con = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.con.execute("PRAGMA journal_mode=TRUNCATE")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA busy_timeout=5000")
        with self.lock:
            self.con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            self.con.execute("CREATE TABLE IF NOT EXISTS kv (store TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
                             " PRIMARY KEY (store, key))")
            self.con.execute("INSERT OR IGNORE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))

    def execute(self, sql: str, args=()):
        with self.lock:
            return self.con.execute(sql, args)

    def many(self, sql: str, rows):
        with self.lock:
            self.con.execute("BEGIN")
            try:
                self.con.executemany(sql, rows)
                self.con.execute("COMMIT")
            except Exception:
                self.con.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.con.close()
        with Db._open_lock:
            Db._open.pop(str(self.path.resolve()), None)


class Store:
    """A named key → JSON value table with the same calls the old JsonStore had (all / get / put / delete),
    plus put_many / delete_many to change many rows in one transaction."""

    def __init__(self, db: Db, name: str, legacy_json: Path | None = None):
        self.db, self.name = db, name
        self.lock = threading.Lock()
        rows = db.execute("SELECT key, value FROM kv WHERE store = ?", (name,)).fetchall()
        self.data = {k: json.loads(v) for k, v in rows}
        if not rows and legacy_json is not None:
            self._import(legacy_json)

    def _import(self, path: Path):
        """First start after the update: copy the old JSON file in, then keep it aside (renamed) as a backup."""
        try:
            data = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return
        except Exception as e:  # noqa: BLE001
            log.warning("couldn't read %s for the move to the database: %s", path.name, e)
            return
        if not isinstance(data, dict):
            return
        self.put_many(data)
        try:
            path.replace(path.with_name(path.name + ".before-database"))
        except OSError as e:
            log.warning("moved %s into the database but couldn't rename it: %s", path.name, e)
        log.info("moved %d entries from %s into the database", len(data), path.name)

    def all(self) -> dict:
        with self.lock:
            return dict(self.data)

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?, ?)", (self.name, key, json.dumps(value, ensure_ascii=False)))

    def put_many(self, items: dict):
        if not items:
            return
        with self.lock:
            self.data.update(items)
            self.db.many("INSERT OR REPLACE INTO kv VALUES (?, ?, ?)",
                         [(self.name, k, json.dumps(v, ensure_ascii=False)) for k, v in items.items()])

    def delete(self, key):
        with self.lock:
            if self.data.pop(key, None) is not None:
                self.db.execute("DELETE FROM kv WHERE store = ? AND key = ?", (self.name, key))

    def delete_many(self, keys):
        keys = list(keys)
        with self.lock:
            gone = [k for k in keys if self.data.pop(k, None) is not None]
            if gone:
                self.db.many("DELETE FROM kv WHERE store = ? AND key = ?", [(self.name, k) for k in gone])


class Identities:
    """Which book is which — a permanent id per book, whatever its path.

    Before this, a book's id *was* its path, so every move/rename produced a "new" book whose progress,
    edits, favourites and date added had to be patched over. Now:
      · a move made by the app updates the path here directly (`moved`);
      · a move made outside the app (Explorer, Finder) is recognised at the next scan: a book that appears at
        a new path takes the id of one that vanished with the same size and modification time (a move or
        rename keeps both);
      · books that vanish are remembered for GRACE days, so a library folder that is briefly unmounted
        comes back with its ids intact.
    Existing ids were make_id(path), and that is what a book seen for the first time gets — so the first
    start after the update keeps every id exactly as it was."""

    GRACE = 30 * 86400

    def __init__(self, db: Db):
        self.db = db
        self.lock = threading.Lock()
        db.execute("CREATE TABLE IF NOT EXISTS ids (id TEXT PRIMARY KEY, rel TEXT NOT NULL UNIQUE,"
                   " size INTEGER, mtime INTEGER, added INTEGER, gone INTEGER)")

    def rows(self) -> dict[str, tuple]:
        return {r[1]: r for r in self.db.execute("SELECT id, rel, size, mtime, added, gone FROM ids").fetchall()}

    def resolve(self, found: dict, new_id, now: int) -> dict:
        """`found`: books from a scan, keyed by anything. Gives each its permanent id (and date added) and
        returns them keyed by that id. `new_id(rel)` proposes an id for a book never seen before."""
        import time as _t
        now = now or int(_t.time())
        with self.lock:
            known = self.rows()
            here = {b["rel"] for b in found.values()}
            vanished: dict[tuple, list] = {}
            for rel, r in known.items():
                if rel not in here:
                    vanished.setdefault((r[2], r[3]), []).append(r)
            taken = {r[0] for r in known.values()}
            out, upserts, deletes = {}, [], []
            for b in sorted(found.values(), key=lambda x: x["rel"]):
                r = known.get(b["rel"])
                if r is None:                                   # a path we haven't seen: moved here, or new
                    cands = vanished.get((b.get("size"), b.get("mtime")), [])
                    name = b["rel"].rsplit("/", 1)[-1]
                    same = [c for c in cands if c[1].rsplit("/", 1)[-1] == name]
                    r = same[0] if same else cands[0] if len(cands) == 1 else None
                    if r is not None:
                        cands.remove(r)
                        deletes.append(r[1])
                        log.info("recognised a moved book: %s → %s", r[1], b["rel"])
                if r is not None:
                    bid, added = r[0], r[4] or b.get("added")
                else:
                    bid = new_id(b["rel"])
                    while bid in taken:                         # another book once lived at this path
                        bid = new_id(b["rel"] + "\x00" + str(len(taken)))
                    added = b.get("added")
                taken.add(bid)
                b["id"], b["added"] = bid, added
                out[bid] = b
                if r is None or r[1] != b["rel"] or r[2] != b.get("size") or r[3] != b.get("mtime") or r[5] or r[4] != added:
                    upserts.append((bid, b["rel"], b.get("size"), b.get("mtime"), added, None))
            gone = []
            for group in vanished.values():
                for r in group:
                    if r[5] is None:
                        gone.append((now, r[0]))
                    elif now - r[5] > self.GRACE:
                        deletes.append(r[1])
            with self.db.lock:
                self.db.con.execute("BEGIN")
                try:
                    self.db.con.executemany("DELETE FROM ids WHERE rel = ?", [(d,) for d in deletes])
                    self.db.con.executemany("DELETE FROM ids WHERE id = ?", [(u[0],) for u in upserts])
                    self.db.con.executemany("INSERT OR REPLACE INTO ids VALUES (?, ?, ?, ?, ?, ?)", upserts)
                    self.db.con.executemany("UPDATE ids SET gone = ? WHERE id = ?", gone)
                    self.db.con.execute("COMMIT")
                except Exception:
                    self.db.con.execute("ROLLBACK")
                    raise
            return out

    def moved(self, old_rel: str, new_rel: str):
        """The app moved/renamed a file or a folder: every book at or under old_rel keeps its id."""
        if old_rel == new_rel:
            return
        with self.lock, self.db.lock:
            rows = self.db.con.execute("SELECT id, rel FROM ids WHERE rel = ? OR substr(rel, 1, ?) = ?",
                                       (old_rel, len(old_rel) + 1, old_rel + "/")).fetchall()
            if not rows:
                return
            self.db.con.execute("BEGIN")
            try:
                for _, rel in rows:                             # clear the targets first (UNIQUE rel)
                    self.db.con.execute("DELETE FROM ids WHERE rel = ?", (new_rel + rel[len(old_rel):],))
                self.db.con.executemany("UPDATE ids SET rel = ?, gone = NULL WHERE id = ?",
                                        [(new_rel + rel[len(old_rel):], bid) for bid, rel in rows])
                self.db.con.execute("COMMIT")
            except Exception:
                self.db.con.execute("ROLLBACK")
                raise

    def forget(self, bid: str):
        """The app deleted the book."""
        self.db.execute("DELETE FROM ids WHERE id = ?", (bid,))


class Names:
    """Permanent ids for sets/series and collections.

    A series is "this name, in this library (and collection)" — that's what groups "Starfall/" with a loose
    "Starfall.cbz" — so its natural key is a hash of those (series_key / collection_key). That key changes on a
    rename or a move; the id kept here doesn't:
      · a key seen for the first time takes the id its books had before, when that old id's key is gone
        (renamed or moved — in the app or in Explorer); otherwise a fresh id;
      · a fresh id is the natural key itself, so the first start after the update keeps every id as it was.
    """

    def __init__(self, db: Db):
        self.db = db
        self.lock = threading.Lock()
        db.execute("CREATE TABLE IF NOT EXISTS names (kind TEXT NOT NULL, key TEXT NOT NULL, id TEXT NOT NULL,"
                   " gone INTEGER, PRIMARY KEY (kind, key), UNIQUE (kind, id))")
        self.map: dict[tuple, list] = {(k, key): [i, g] for k, key, i, g in
                                       db.execute("SELECT kind, key, id, gone FROM names").fetchall()}

    def _ids(self, kind) -> dict:
        return {v[0]: key for (k, key), v in self.map.items() if k == kind}

    def _fresh(self, kind, key, used) -> str:
        import hashlib
        cand, n = key, 0
        while cand in used:
            n += 1
            cand = hashlib.sha1(f"{key}\x00{n}".encode()).hexdigest()[:12]
        return cand

    def id_for(self, kind: str, key: str) -> str:
        """The id for a key, allocating one if it's new (empty series / collections have no books to inherit from)."""
        with self.lock:
            v = self.map.get((kind, key))
            if v:
                return v[0]
            bid = self._fresh(kind, key, self._ids(kind))
            self.map[(kind, key)] = [bid, None]
            self.db.execute("INSERT OR REPLACE INTO names VALUES (?, ?, ?, NULL)", (kind, key, bid))
            return bid

    def rename(self, kind: str, old_key: str, new_key: str):
        """The app renamed something with no books in it (nothing to inherit through): move its id over."""
        with self.lock:
            v = self.map.pop((kind, old_key), None)
            if not v or old_key == new_key:
                if v:
                    self.map[(kind, old_key)] = v
                return
            self.map.pop((kind, new_key), None)
            self.map[(kind, new_key)] = [v[0], None]
            self.db.execute("DELETE FROM names WHERE kind = ? AND (key = ? OR key = ?)", (kind, old_key, new_key))
            self.db.execute("INSERT INTO names VALUES (?, ?, ?, NULL)", (kind, new_key, v[0]))

    def resolve(self, kind: str, present: dict[str, list[str]], before: dict[str, str], now: int,
                keep: set = frozenset()) -> dict[str, str]:
        """present: {natural key: [book ids under it]}; before: {book id: the id it belonged to last scan}.
        keep: keys that exist without books (empty folders) — not "gone". Returns {natural key: id}."""
        with self.lock:
            by_id = self._ids(kind)
            live = set(present) | set(keep)
            vanished_ids = {i for i, key in by_id.items() if key not in live}
            out, writes, deletes = {}, [], []
            for key in sorted(present, key=lambda k: -len(present[k])):    # bigger groups claim first
                v = self.map.get((kind, key))
                if v:
                    out[key] = v[0]
                    if v[1] is not None:
                        v[1] = None; writes.append((kind, key, v[0]))
                    continue
                votes: dict[str, int] = {}
                for bid in present[key]:
                    old = before.get(bid)
                    if old in vanished_ids:
                        votes[old] = votes.get(old, 0) + 1
                if votes:
                    sid = max(votes, key=votes.get)
                    vanished_ids.discard(sid)
                    deletes.append(by_id[sid]); self.map.pop((kind, by_id[sid]), None)
                else:
                    sid = self._fresh(kind, key, set(by_id) | set(out.values()))
                by_id[sid] = key
                self.map[(kind, key)] = [sid, None]
                writes.append((kind, key, sid))
                out[key] = sid
            for key in list(keep):
                if (kind, key) in self.map and self.map[(kind, key)][1] is not None:
                    self.map[(kind, key)][1] = None; writes.append((kind, key, self.map[(kind, key)][0]))
            gone = []
            for (k, key), v in list(self.map.items()):
                if k != kind or key in live:
                    continue
                if v[1] is None:                        # remembered (tiny rows; never purged, so an empty
                    v[1] = now; gone.append((now, kind, key))   # folder keeps its id however long it stays empty)
            if writes or deletes or gone:
                with self.db.lock:
                    self.db.con.execute("BEGIN")
                    try:
                        self.db.con.executemany("DELETE FROM names WHERE kind = ? AND key = ?", [(kind, d) for d in deletes])
                        self.db.con.executemany("DELETE FROM names WHERE kind = ? AND id = ?", [(kind, w[2]) for w in writes])
                        self.db.con.executemany("INSERT OR REPLACE INTO names VALUES (?, ?, ?, NULL)", writes)
                        self.db.con.executemany("UPDATE names SET gone = ? WHERE kind = ? AND key = ?", gone)
                        self.db.con.execute("COMMIT")
                    except Exception:
                        self.db.con.execute("ROLLBACK")
                        raise
            return out
