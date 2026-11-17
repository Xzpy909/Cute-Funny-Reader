"""The background tidy turns whatever is in a Cosplay library into Cosplayer / Set / variant files."""
from app import library as L
from conftest import jpeg, make_cbz

BUNNY = ["[Dreva(Solene)]My Lucky Bunny Bonus", "[Dreva(Solene)]My Lucky Bunny Normal",
         "[Dreva(Solene)]My Lucky Bunny S_version"]


def cos_lib(lib):
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    return L.LIB_ROOT / l["path"]


def files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != L.COL_MARK)


def test_old_style_uploads_become_variants(lib):
    # exactly what the library looked like after uploading with the previous version
    root = cos_lib(lib)
    for n in BUNNY:
        make_cbz(root / n / f"{n}.cbz", {"001.jpg": jpeg()})
    (root / BUNNY[0] / "cover.jpg").write_bytes(jpeg())       # an extra file travels along with its set
    lib.scan()
    assert files(root) == ["Solene/My Lucky Bunny/" + f for f in
                           [f"{BUNNY[0]}.cbz", f"{BUNNY[1]}.cbz", f"{BUNNY[2]}.cbz", "cover.jpg"]]
    assert (root / "Solene" / L.COL_MARK).exists()
    books = sorted(lib.books.values(), key=lambda b: b["label"])
    assert [b["label"] for b in books] == ["Bonus", "Normal", "S version"]
    assert {(b["collection"], b["series"]) for b in books} == {("Solene", "My Lucky Bunny")}


def test_reading_progress_survives_the_move(lib):
    root = cos_lib(lib)
    for n in BUNNY[:2]:
        make_cbz(root / f"{n}.cbz", {"001.jpg": jpeg(), "002.jpg": jpeg()})
    lib._scan()                                                # scan without tidying, then read a page
    bid = next(b["id"] for b in lib.books.values() if b["file"].startswith(BUNNY[0]))
    lib.progress.put(bid, {"page": 1})
    lib.scan(deep=True)                                        # tidying runs when books changed, or on a deep scan
    moved = next(b for b in lib.books.values() if b["file"].startswith(BUNNY[0]))
    assert moved["rel"].endswith(f"Solene/My Lucky Bunny/{BUNNY[0]}.cbz")
    assert lib.progress.all().get(moved["id"]) == {"page": 1}


def test_hand_copied_cosplayer_folder_is_recognised(lib):
    root = cos_lib(lib)
    for n in BUNNY:
        make_cbz(root / "Solene" / "My Lucky Bunny" / f"{n}.cbz", {"001.jpg": jpeg()})
    lib.scan()
    assert (root / "Solene" / L.COL_MARK).exists()
    assert {(b["collection"], b["series"]) for b in lib.books.values()} == {("Solene", "My Lucky Bunny")}
    assert sorted(b["label"] for b in lib.books.values()) == ["Bonus", "Normal", "S version"]


def test_a_later_variant_joins_its_set(lib):
    root = cos_lib(lib)
    for n in BUNNY[:2]:
        make_cbz(root / "Solene" / "My Lucky Bunny" / f"{n}.cbz", {"001.jpg": jpeg()})
    (root / "Solene" / L.COL_MARK).touch()
    make_cbz(root / BUNNY[2] / f"{BUNNY[2]}.cbz", {"001.jpg": jpeg()})   # weeks later, uploaded the old way
    lib.scan()
    assert files(root) == sorted(f"Solene/My Lucky Bunny/{n}.cbz" for n in BUNNY)


def test_lone_set_moves_into_its_cosplayer_and_keeps_its_name(lib):
    root = cos_lib(lib)
    n = "[DREVA] Mirelle - Gears' Frontier HK9"
    make_cbz(root / n / f"{n}.cbz", {"001.jpg": jpeg()})
    lib.scan()
    assert files(root) == [f"Mirelle/Gears' Frontier HK9/{n}.cbz"]


def test_things_without_a_cosplayer_or_pattern_stay_put(lib):
    root = cos_lib(lib)
    make_cbz(root / "Summer Beach" / "Summer Beach.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Holiday Normal.cbz", {"001.jpg": jpeg()})          # "Normal" alone isn't proof
    make_cbz(root / "Mirelle" / "Bunny Set" / "a.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Mirelle" / "Bunny Set" / "b.cbz", {"001.jpg": jpeg()})
    (root / "Mirelle" / L.COL_MARK).touch()
    before = files(root)
    lib.scan()
    assert files(root) == before


def test_running_again_changes_nothing(lib):
    root = cos_lib(lib)
    for n in BUNNY:
        make_cbz(root / n / f"{n}.cbz", {"001.jpg": jpeg()})
    lib.scan()
    before = files(root)
    assert lib.tidy_cosplay() == 0
    assert files(root) == before


def test_comics_libraries_are_never_touched(lib):
    l = lib.create_library("Comics", "Comics", False, "#fff", "comics")
    root = L.LIB_ROOT / l["path"]
    for n in BUNNY:
        make_cbz(root / n / f"{n}.cbz", {"001.jpg": jpeg()})
    before = files(root)
    lib.scan()
    assert files(root) == before


def test_sets_that_differ_only_at_the_end_become_one_set(lib):
    # two separate sets of one cosplayer, named alike: the shared name is the set, the rest the variant
    root = cos_lib(lib)
    for v in ("Normal", "SP-version"):
        n = f"Circuit Hunter Mika {v}"
        make_cbz(root / "Sela" / n / f"[DREVA] Sela - {n}.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Sela" / "Arc Fleet HMS Siren" / "a.cbz", {"001.jpg": jpeg()})
    make_cbz(root / "Sela" / "Arc Fleet USS St. Lucas" / "b.cbz", {"001.jpg": jpeg()})
    (root / "Sela" / L.COL_MARK).touch()
    lib.scan()
    assert files(root) == ["Sela/Arc Fleet HMS Siren/a.cbz", "Sela/Arc Fleet USS St. Lucas/b.cbz",
                           "Sela/Circuit Hunter Mika/[DREVA] Sela - Circuit Hunter Mika Normal.cbz",
                           "Sela/Circuit Hunter Mika/[DREVA] Sela - Circuit Hunter Mika SP-version.cbz"]
    mika = sorted(b["label"] for b in lib.books.values() if b["series"] == "Circuit Hunter Mika")
    assert mika == ["Normal", "SP-version"]
    before = files(root)
    lib.scan(deep=True)
    assert files(root) == before                              # and it settles: nothing moves again
