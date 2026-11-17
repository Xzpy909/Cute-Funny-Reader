"""Cosplay uploads land as Cosplayer / Set / variant files."""
from app.library import cosplay_plan, same_case
from conftest import jpeg, make_cbz

BUNNY = ["[Dreva(Solene)]My Lucky Bunny Bonus", "[Dreva(Solene)]My Lucky Bunny Normal",
         "[Dreva(Solene)]My Lucky Bunny S_version"]


def test_three_variants_share_one_set(tmp_path):
    plan = cosplay_plan(tmp_path, BUNNY)
    assert {p["cosplayer"] for p in plan.values()} == {"Solene"}
    assert {p["set"] for p in plan.values()} == {"My Lucky Bunny"}


def test_a_lone_set_keeps_its_whole_name(tmp_path):
    # "Normal" alone could be part of the title — with no sibling we can't tell, so nothing is split
    plan = cosplay_plan(tmp_path, ["[Dreva(Solene)]My Lucky Bunny Normal", "[DREVA] Mirelle - Gears' Frontier HK9"])
    assert plan["[Dreva(Solene)]My Lucky Bunny Normal"] == {"cosplayer": "Solene", "set": "My Lucky Bunny Normal"}
    assert plan["[DREVA] Mirelle - Gears' Frontier HK9"] == {"cosplayer": "Mirelle", "set": "Gears' Frontier HK9"}


def test_a_later_variant_joins_the_existing_set(tmp_path):
    (tmp_path / "solene" / "My Lucky Bunny").mkdir(parents=True)
    plan = cosplay_plan(tmp_path, ["[Dreva(Solene)]My Lucky Bunny Bonus"])
    assert plan["[Dreva(Solene)]My Lucky Bunny Bonus"] == {"cosplayer": "solene", "set": "My Lucky Bunny"}


def test_same_case_reuses_existing_spelling(tmp_path):
    (tmp_path / "DREVA").mkdir()
    assert same_case(tmp_path, "Dreva") == "DREVA"
    assert same_case(tmp_path, "New") == "New"


def test_scanned_variants_show_short_labels(lib):
    from app import library as L
    l = lib.create_library("Cos", "Cos", False, "#fff", "cosplay")
    root = L.LIB_ROOT / l["path"]
    for n in BUNNY:
        make_cbz(root / "Solene" / "My Lucky Bunny" / f"{n}.cbz", {"001.jpg": jpeg()})
    (root / "Solene" / L.COL_MARK).touch()                 # uploads mark the cosplayer folder
    lib.scan()
    books = sorted(lib.books.values(), key=lambda b: b["label"])
    assert [b["label"] for b in books] == ["Bonus", "Normal", "S version"]
    assert {b["series"] for b in books} == {"My Lucky Bunny"}
    assert {(b["author"], b["publisher"]) for b in books} == {("Solene", "Dreva")}
