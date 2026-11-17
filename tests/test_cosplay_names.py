"""Cosplay names → circle (metadata), cosplayer, set, and — only among siblings — variant."""
from app.library import cosplay_name, split_variant, variant_groups
from app import library as L
from conftest import jpeg, make_cbz


def test_circle_with_cosplayer_in_brackets():
    assert cosplay_name("[Dreva(Solene)]My Lucky Bunny Bonus") == \
        {"circle": "Dreva", "cosplayer": "Solene", "work": "My Lucky Bunny Bonus"}


def test_circle_then_cosplayer_dash_work():
    assert cosplay_name("[DREVA] Bluma - Equinox Lark (Dream Chronicle) Normal Ver") == \
        {"circle": "DREVA", "cosplayer": "Bluma", "work": "Equinox Lark Normal Ver"}


def test_plain_names_and_non_credit_tags():
    assert cosplay_name("Summer Beach") == {"circle": "", "cosplayer": "", "work": "Summer Beach"}
    assert cosplay_name("[Digital] Mirelle - Bunny") == {"circle": "", "cosplayer": "Mirelle", "work": "Bunny"}


def test_split_variant():
    assert split_variant("My Lucky Bunny Bonus") == ("My Lucky Bunny", "Bonus")
    assert split_variant("My Lucky Bunny S version") == ("My Lucky Bunny", "S version")
    assert split_variant("Hi Sol! Version A") == ("Hi Sol!", "Version A")
    assert split_variant("Equinox Lark Normal Ver") == ("Equinox Lark", "Normal Ver")
    assert split_variant("Gears' Frontier HK9") == ("Gears' Frontier HK9", "")
    assert split_variant("Bonus") == ("Bonus", "")                  # a name never becomes only a variant


def test_variants_only_among_siblings():
    works = ["My Lucky Bunny Bonus", "My Lucky Bunny Normal", "My Lucky Bunny S version", "Gears' Frontier HK9"]
    g = variant_groups(works)
    assert g == {0: ("My Lucky Bunny", "Bonus"), 1: ("My Lucky Bunny", "Normal"), 2: ("My Lucky Bunny", "S version")}
    assert variant_groups(["Equinox Lark Normal Ver"]) == {}          # alone: stays a whole set


def test_the_difference_is_the_variant():
    # no word list needed: names that start the same way are one set, what differs is the variant
    g = variant_groups(["Circuit Hunter Mika Normal", "Circuit Hunter Mika SP-version", "A Slow Afternoon"])
    assert g == {0: ("Circuit Hunter Mika", "Normal"), 1: ("Circuit Hunter Mika", "SP-version")}
    g = variant_groups(["Midnight Rain Hotel Crimson", "Midnight Rain Hotel Ivory Lace"])
    assert g == {0: ("Midnight Rain Hotel", "Crimson"), 1: ("Midnight Rain Hotel", "Ivory Lace")}
    assert variant_groups(["Plan A", "Plan B"]) == {0: ("Plan", "A"), 1: ("Plan", "B")}


def test_the_bare_name_is_a_variant_too():
    g = variant_groups(["Sunstay #4", "Sunstay #4 S ver"])
    assert g == {0: ("Sunstay #4", ""), 1: ("Sunstay #4", "S ver")}
    from app.library import sibling_works
    names = ["Kaltara The Shadow of the Moon", "Kaltara The Shadow of the Moon - Normal"]
    assert variant_groups(sibling_works(names)) == {0: (names[0], ""), 1: (names[0], "Normal")}
    assert sibling_works(["Sela Mi-Rae - Sunstay #4"]) == ["Sunstay #4"]      # a real "Cosplayer - Work"


def test_different_works_that_start_alike_stay_apart():
    # a game or series name in front is not a set: these are different characters, not variants
    assert variant_groups(["Arc Fleet HMS Siren", "Arc Fleet USS St. Lucas"]) == {}
    assert variant_groups(["KTX Aria", "KTX Ka'ra"]) == {}
    assert variant_groups(["Gears' Frontier HK9", "Gears' Frontier UMP7"]) == {}
    assert variant_groups(["My Lucky Bunny", "My Lucky Pony"]) == {}
    assert variant_groups(["Catch Me", "Reach Me", "Masked Pilot"]) == {}


def test_a_later_variant_finds_its_set():
    from app.library import joins_existing
    have = {"circuit hunter mika", "cloudy alice", "arc fleet"}
    assert joins_existing("Circuit Hunter Mika Deluxe Edition", have) == "Circuit Hunter Mika"
    assert joins_existing("Cloudy Alice S+ ver", have) == "Cloudy Alice"
    assert joins_existing("Arc Fleet HMS Siren Extra Long Name", have) == ""
    assert joins_existing("Circuit Hunter Mika", have) == ""


def test_scan_credits_in_cosplay_library(lib):
    make_cbz(L.LIB_ROOT / "Cos" / "Set" / "[Dreva(Solene)]My Lucky Bunny Bonus.cbz", {"01.jpg": jpeg()})
    make_cbz(L.LIB_ROOT / "Cos" / "Set" / "[DREVA] Bluma - Equinox Lark Normal Ver.cbz", {"01.jpg": jpeg()})
    lib.create_library("Cos", "Cos", False, "#fff", "cosplay"); lib.scan()
    got = {b["file"]: (b["author"], b["publisher"]) for b in lib.books.values()}
    assert got["[Dreva(Solene)]My Lucky Bunny Bonus.cbz"] == ("Solene", "Dreva")
    assert got["[DREVA] Bluma - Equinox Lark Normal Ver.cbz"] == ("Bluma", "DREVA")


def test_comics_libraries_keep_their_credit_rule(lib):
    make_cbz(L.LIB_ROOT / "Comics" / "[Circle (Artist)] Work.cbz", {"01.jpg": jpeg()})
    lib.create_library("Comics", "Comics", False, "#fff", "comics"); lib.scan()
    b = next(iter(lib.books.values()))
    assert (b["author"], b["publisher"]) == ("Artist", "Circle")
