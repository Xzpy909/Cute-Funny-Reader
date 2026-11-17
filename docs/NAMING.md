# Naming baseline

The file names the reader is **guaranteed** to understand. The parsers also cope with plenty of other
layouts found in the wild (and keep doing so), but these are the reference: a file named like this must
always land in the right place with the right metadata. Each line below is pinned by
`tests/test_naming_baseline.py` — if a parser change breaks one, the tests say so.

Parts in `[ ]` / `( )` are written literally; *italics* are placeholders. Examples use made-up names.

## Cosplay

```
[Photographer / Publisher] Cosplayer - Set - Variant.zip
Cosplayer - Set - Variant.zip
```

| Part | Becomes | Notes |
|---|---|---|
| `[Photographer / Publisher]` | circle — **metadata only** | optional; one name (the photographer *or* the publisher/studio) |
| `Cosplayer` | top folder | Cosplayer → Set → Variant |
| `Set` | set folder | |
| `- Variant` | variant of the set | optional (`Normal`, `Bonus`, `SP ver`, …) |

Examples:
- `[Lumen Studio] Mirelle - Starfall Bunny - Bonus.zip` → Mirelle / Starfall Bunny, variant Bonus, circle Lumen Studio
- `Mirelle - Starfall Bunny.zip` → Mirelle / Starfall Bunny

A folder dropped in the browser follows the same rule (its name is used; it is packed to `.zip`).

## Manga / comics

When everything is known:

```
(Event) [Circle (Author)] Series - Ch. XX [Language].cbz
```

Otherwise:

```
[Circle (Author)] Series - Ch. 01.cbz
[Author] - Series - Ch. 01.cbz
```

| Part | Becomes | Notes |
|---|---|---|
| `(Event)` | — | optional (`(C105)`); ignored for now |
| `[Circle (Author)]` | publisher = Circle, author = Author | |
| `[Author] -` | author | the ` - ` right after the bracket marks it as the author (a bare `[Name] Series Ch. 05` is more often a scanlation group, so it isn't trusted) |
| `Series` | series | |
| `Ch. XX` | chapter number | `Vol. XX` → volume; a one-shot simply has no number |
| `[Language]` | — | optional (`[English]`); ignored for now |

Examples:
- `(C105) [Moonforge (Mirelle)] Starfall Academy - Ch. 03 [English].cbz` → series Starfall Academy, chapter 3, author Mirelle, publisher Moonforge
- `[Moonforge (Mirelle)] Starfall Academy - Ch. 01.cbz` → same, chapter 1
- `[Mirelle] - Starfall Academy - Ch. 01.cbz` → series Starfall Academy, chapter 1, author Mirelle
