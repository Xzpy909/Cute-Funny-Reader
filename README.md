# Cute&Funny Reader

A self-hosted, web-based comic / manga / light-novel reader. Runs in Docker and reads straight from your folders.

## Run it

```bash
docker compose up -d --build
```

Then open **http://localhost:9001** (or `http://<server-ip>:9001` from a phone or tablet).

`docker-compose.yml` mounts:

| Host path  | Container | Purpose |
|------------|-----------|---------|
| `./Data`   | `/data` | Library folders (writable, so uploads can be saved) |
| `./config` | `/config` | Index, reading progress, thumbnail + panel cache |

Change `./Data` to wherever your comics should live (e.g. `D:/Comics:/data` on Windows, `/mnt/nas/comics:/data` on Linux).

## Libraries

The app starts empty. Click **Add your first library** (or **+ Add library** in the sidebar) and choose:

- **Name** (e.g. *Manga*, *Comics*, *Light Novels*)
- **Folder** under `/data`. It's created for you, or you can pick a folder that already exists there.
- **Reading direction**: left → right, or right ← left for manga
- **Colour** for the sidebar dot and drop target

Libraries are stored in `config/libraries.json`. **Remove library** (in Library settings) deletes the library's folder if it's empty. If the folder contains files, you choose: tick "Also delete…" to remove the folder and its files, or leave it unticked to keep them (the folder is then not re-added automatically).

**Windows long paths:** browsers can't read dropped files whose full path is longer than 260 characters. If a drop reports "Browser couldn't read it", move the folder closer to the drive root (e.g. `D:\Manga`) or shorten the names.

**Folders become libraries automatically:** any top-level folder you create in `/data` (e.g. `/data/Test`) shows up as a library with a random colour and left-to-right reading. Change it under **Library settings** (top-right): rename it, set the reading direction, pick a colour, or switch between libraries. A library you remove is not re-added automatically. To bring it back, create it again with the same folder.

### Library types

| Type | Reading | Notes |
|---|---|---|
| **Comics** | left → right | also webtoons and light novels |
| **Manga** | right ← left | per-series override in Series settings |
| **Cosplay** | left → right | photo sets: guided panels and reading-direction toggle are disabled; **videos are allowed** |

A series' own settings — reading direction, cards / list, order, and the reader's mode and fit — are kept per account on the server, so they follow you from the PC to the phone (settings a browser remembered from before are taken over the first time you sign in there).

Folders whose name contains "manga" or "cosplay" get that type automatically.

### Series & collections

```
/data/<Library>/
├── <Series>/<chapter>.cbz                    series folder
├── <loose file>.cbz                          one-file series
└── <Collection>/                             collection (has a hidden .collection marker)
    ├── <Series>/<chapter>.cbz
    └── <loose file>.cbz                      one-shot series inside the collection
```

- **+ New collection** (in a library) creates a collection, a folder that groups series. Collections show as stacked-cover cards. Open one to see its series, drop files onto it, or move series in with **⋯ → Move to collection**. A collection's ⋯ menu offers **Rename**, **Ungroup** (moves its series back to the library and keeps them), and **Delete**.
- A series with only **one chapter** opens straight in the reader. Series with more chapters open their chapter list (list view by default; there's a grid toggle above the list).
- Chapters that have a number but no series name (e.g. `Ch.0012 (en) [group].cbz`) are grouped into an **Unsorted** series. Use **⋯ → Rename…** to give it a real name; the app creates the folder and moves the chapters in.
- **☑ Select files** (next to **+ Add files**) turns on multi-select, with **Select all / Select none**:
  - on a shelf it selects series, which you can merge, move to a collection or library, mark read, or delete
  - on a series page it selects chapters, which you can move to another or a new series, move to a library, mark read, or delete

### Photo folders

A folder with photos directly in it (and no archives) is read as **one set / chapter**, no packing needed: `Cosplay/Overwatch/cover.webp, 02.avif, 3.mp4 …` is a one-set series called *Overwatch*. In Cosplay libraries the videos in that folder are part of the set. `cover.*` is always the first page, the rest follow in natural order (`2` before `10`). A lone `cover.jpg` next to chapter subfolders is ignored as artwork.

### Dropping folders

| You drop… | It becomes… |
|---|---|
| a folder of **images** | a series with one chapter. The images are packed into `<folder>.cbz` in your browser before upload |
| a folder whose **subfolders are image folders** | a series with one chapter per subfolder (each packed into a `.cbz`) |
| a folder of **numbered chapters** of one series | a series named after the folder |
| a folder of **unrelated** `.cbz`/`.epub` files | a **collection**, with each file as its own series |
| a folder of **series folders** | a **collection** containing those series |
| loose files | filed by name, as before |

Dropping onto a series page adds everything to that series. Dropping onto a collection page adds the files to that collection.

### Organising

Each series card and chapter row has a **⋯** button. You can also long-press on touch screens or right-click with a mouse:

- **Move to library**: moves the files to another library's folder
- **Move to series** (chapter) or **Merge into series** (series): files move into that series' folder. You can also start a **New series…**
- **Mark as read / unread**
- **Delete chapter / series**: moves it to the **Trash** at once; the message at the bottom has **Undo**

### 🗑 Trash

Deleted files leave the library right away and wait on the **Trash** page (sidebar; it shows how many items and
how much space). Each card says where it was ("Was in: Comics / Starfall") and how many days it has left. Click
cards to select them, then **Restore** or **Delete forever**; group the page by library or by day. **Empty trash**
says how much space it frees and needs a second click.

- Restoring puts files back where they were: a missing collection or series folder is made again, and if the name
  is taken the file gets a free one ("Starfall 01 (2)"). If the whole library is gone, you choose another one.
- How long things stay (7 / 14 / 30 / 90 days, or until emptied) is chosen on the Trash page by the admin. The
  `TRASH_KEEP_DAYS` variable is only the starting value (default 30).
- The files sit in a hidden `.trash` folder of the account; the **Storage** page shows the trash size with
  **Empty trash** too.

Reading progress follows a chapter when it's moved. Empty series folders are cleaned up automatically.

### Adding books

- **Drag & drop** `.cbz`, `.zip`, `.cb7`, `.cbr` or `.epub` files (`.cb7` and `.cbr` are converted to `.cbz` on upload — pages stored uncompressed, so they open instantly) (plus `.mp4`, `.webm`, `.mkv`, `.mov`, `.m4v` videos in Cosplay libraries), or whole folders, anywhere onto the window. With several libraries you drop onto the one you want.
- A drop that creates folders, or holds something to decide, first opens a **review sheet**: what will be created, grouped by where it goes. Images lying next to archives and regular `.zip` / `.rar` / `.7z` archives are toggles there (the plan updates as you flip them); ready-made files dropped on their own go straight in. The plan comes from the server, so the naming rules live in one place
- Or use **+ Add files** in a library.
- Uploaded files are sorted automatically: `Series Name c045.cbz` is saved to `/data/<Library>/Series Name/`. Duplicates are skipped, and non-archive files are rejected.
- Files copied into a library folder by other means are picked up on the next scan (every `SCAN_INTERVAL` seconds) or via **Rescan library**.

```
/data
└── Manga/                               ← library folder
    ├── Starfall/                        ← series
    │   └── Starfall c045 (2026).cbz
    └── Some One-shot.cbz                ← loose file = its own series
```

Chapter/volume numbers are read from filenames (`c049`, `ch.12`, `v01`, `Vol. 3`, `#7`). `ComicInfo.xml` provides titles, series, writer, summary and `Manga=YesAndRightToLeft`. Text EPUBs open in the book reader, and fixed-layout image EPUBs open in the comic reader.

## ✨ Optimize (AVIF)

Right-click (or long-press) a series, set, collection or a selection → **Optimize…** converts its pages to AVIF,
which every current browser shows directly and which is usually much smaller than JPEG / PNG.

- The dialog estimates the size for each preset (from a few sample pages) and can **compare a page** before / after.
- Conversion runs in the background (the **Jobs** panel: pause, resume, cancel) and continues after a restart.
- Each book is written to a temporary file, every converted page is checked, and only then is it swapped in. The file
  keeps its name, so reading progress, favourites and the chosen cover stay.
- **Keep originals** copies the original to `config/originals` for `OPTIMIZE_KEEP_DAYS` (default 14): **Undo optimize**
  in the menu puts it back. A page that wouldn't get smaller, GIFs and videos are left as they are.
- Supported: `.cbz`, `.zip`, `.cb7` and photo folders.
- **A whole library:** right-click the library → **Optimize library…** (also in Library settings, with how much is
  left to convert).
- **New uploads:** Library settings → *New uploads → AVIF · preset* converts whatever is added from then on by itself.
- A HEIC / JPEG XL book offers **Optimize to AVIF** in the reader, so it no longer has to be transcoded to open.
- **Storage** (sidebar): size per library, what was saved and what could still be converted, the biggest series
  not optimized yet (**Optimize the 20 biggest…**), the kept originals (**Delete them now** frees their space; Undo
  is gone then), and **When to optimize**: *Only between 01:00 and 07:00* makes jobs wait for those hours — each
  waiting job has a **Run now** button.

**Presets:** two are built in and can't be deleted — **Default** (AVIF, quality 70, speed 6, full 4:4:4 colour, black-and-white
pages saved as grayscale) is the baseline, and **Lossless** (shown when the selection holds lossless PNG / BMP / TIFF
books) converts those pages to pixel-exact **lossless WebP** — about 30% smaller than PNG, where lossless AVIF barely
beats PNG. JPEG / AVIF pages are never re-encoded losslessly (they would only grow).
Make your own with **+ New preset** in the dialog (name, quality 0–100, speed 0–10: lower is smaller but slower);
its **Advanced** part sets the format (AVIF / lossless WebP), colour (auto = 4:4:4, 4:4:4, 4:2:0) and black-and-white
detection. Delete them with ×. They're kept in `config/optimize-presets.json`. A running job keeps the settings it
started with.
"Shrink huge photos" is off unless you tick it.

## Background work: the pill and the Jobs panel

Anything that takes longer than a moment shows its progress instead of a spinner:

- **The working pill** (bottom centre) — moves, merges, deleting several series, renaming / ungrouping / deleting a
  collection: *"Moving Starfall · 12 of 340 files · ~40 s left · Starfall 013.cbz"*, with **Cancel** (it stops
  between two files; what was already moved stays where it is). Quick changes look as before. A scan, the trash
  mover or a long move started in another tab shows there too while nothing else does: *"Scanning · 1,200 of
  3,400 files"*.
- **The Jobs panel** (bottom right) — ✨ Optimize runs: pause, resume, cancel, **Run now** outside the night
  hours. They continue after a restart.
- JPEG XL / HEIC books show their conversion in the reader while it runs.

The page gets all of this live over one connection (`/api/events`), so nothing polls every few seconds and a
change made in another tab or on another device shows up right away. Behind a reverse proxy that holds such a
connection back, the page notices and checks every few seconds instead. (nginx: `proxy_buffering off;` for
`/api/events` keeps it live.) How it works inside: `docs/JOBS.md`.

## Reader features

**Comics & manga**
- Single, two-page spread (wide pages stay alone) and vertical scroll for webtoons, chosen automatically for tall strips
- **Guided view (G):** automatic panel detection; arrow keys step panel by panel, right-to-left for manga
- Zoom (double-click, Ctrl+wheel, Z) with drag-to-pan, a Shift magnifier, a thumbnail strip (videos show a frame from the video; its scrollbar glows so it's easy to grab — drag it or click along it), and a scrubber with hover preview
- Touch: swipe or tap the edges to turn pages; swipes never bring up the controls; **tap the centre** to show / hide them, **double-tap** to zoom (on a video: play / pause)
- Swipe and tap zones on touch devices, plus an ambient glow and Ink / Slate / Paper backdrops

**Cosplay videos**
- Video files, and videos inside a `.cbz`/`.cb7` between photos, play in a built-in player. The reader's own bottom bar turns into the player controls: previous, page count, seek bar with times, a volume button with a pop-up vertical slider, thumbnails, next. Tap the video (or the big ▶) to play / pause
- Photos and videos flow together: the reader switches between the image viewer and the player, and continues into the next or previous set of the same series or collection
- Keys: Space/K play-pause, M mute, ↑/↓ volume, J/L seek ±10 s, double-click for fullscreen
- Videos inside a `.cbz` should be stored uncompressed (the default when a folder is packed by the app); they stream directly with seeking. Compressed entries are extracted once to the cache.
- MP4 (H.264/AAC) and WebM play in every browser; `.mkv`/`.mov` depend on the codecs your browser supports

**ComicInfo.xml**
- Read from `.cbz` and `.cb7` files: Series, Number, Title, Writer, Publisher, Summary, Year, Manga, Genre, Tags, Format
- Genres (yellow) and tags (`#tag`) appear as chips on each chapter and, combined, on the series page. Click a chip to search for it; the search box also matches tags
- `<Manga>Yes</Manga>` reads that book right to left; `<Format>` (e.g. Web, Digital) shows as a badge

**Accounts**
- On first start the app asks you to create an account (e-mail + password — the form is set up so password managers like Bitwarden offer to save it). That first account is the **admin**
- Each account owns a folder in `/data` (named after the e-mail, e.g. `/data/alex/` for alex@example.com); every folder inside it is one of its libraries. Accounts never see each other's libraries
- Whatever was in `/data` before the first account was created is moved into that account's folder
- The admin can add accounts (🎲 generates a password, which is copied to the clipboard with the e-mail), delete accounts (optionally with their files) and hand the admin role to another account
- Everyone can change their password (other signed-in devices are signed out). Sessions last 60 days; passwords are stored as salted PBKDF2 hashes in `/config/accounts.json`

**Edit details**
- ⋯ → **Edit details…** on a series or set: author, publisher, genres, tags, release format, year, summary, reading direction (and the name, which renames the folder/file)
- In Cosplay libraries the fields are **Cosplayer** and **Photographer / publisher**
- Saved **in the reader** at once (the database in `/config`), whatever the files' size — the same goes for the cover chosen with 🖼 Edit cover
- **💾 Write into files** (in Edit details, when there's something to write) puts them into each file as `metadata.json` — inside `.cbz`/`.zip`/`.cb7` archives (rewritten, images untouched, so it takes a while for big ones) or next to the photos of a folder set. An existing ComicInfo.xml is folded into it and removed; keys the app doesn't know (`id`, `related`, …) are kept. **↺ Reset to file** forgets the saved edits instead
- In the tag box `stockings:f` / `beard:m` become `stockings ♀` / `beard ♂`
- Standalone video files and EPUBs can't hold a metadata.json — their edits always stay in the reader

**metadata.json**
- Read from `.cbz`, `.cb7` and photo folders (metadata.json wins over ComicInfo.xml where both exist; tags are combined)
- Extra keys the app writes: `genres` (full list; `type` = the first), `summary`, `year`, `release`, `direction` (`rtl` / `ltr`), `series`, `number`
- `title` → series name for standalone files, `type` → genre (shown on the cover badge), `artists` → author, `groups` → publisher, `date` → year
- `tags` with `female` / `male` flags become `tag ♀` / `tag ♂`; searching ignores the symbols, so `cute ♀` also finds series tagged plain `cute`

**Light novels (EPUB)**
- Clean reflowable typography (Literata / Manrope) with adjustable size, width and spacing
- Table of contents, illustrations open in a lightbox, internal links work
- Scroll position is saved per chapter

**Everywhere**
- Reading progress is stored on the server, so it follows you between devices
- Continue reading, Unread and Finished views, per-series pages, and mark read / unread
- "Read next" card at the end of each chapter or volume
- Press **?** in the reader for every shortcut

## API (for scripts)

| Endpoint | |
|---|---|
| `GET /api/library` | all books + libraries |
| `GET /api/books/{id}` | details + page dimensions / chapter list |
| `GET /api/books/{id}/pages/{n}` | original page image |
| `GET /api/books/{id}/thumbs/{n}?w=200` | WebP thumbnail (a video: a frame from it) |
| `GET /api/books/{id}/cover?w=480` | cover |
| `GET /api/books/{id}/panels/{n}?rtl=1` | detected panel boxes (0–1) |
| `GET /api/books/{id}/chapters/{i}` | sanitised EPUB chapter HTML |
| `GET/PUT/DELETE /api/progress[/{id}]` | reading progress |
| `GET/POST /api/libraries`, `PATCH/DELETE /api/libraries/{id}` | manage libraries |
| `PUT /api/libraries/{id}/files?name=…` | upload a file (raw body) |
| `GET /api/folders` | existing folders under `/data` |
| `POST /api/books/{id}/move`, `POST /api/series/{id}/move` | move / merge (`library`, `seriesId`, `newSeries`, `into`) |
| `DELETE /api/books/{id}`, `DELETE /api/series/{id}` | move files to the trash |
| `GET /api/trash`, `GET /api/trash/{id}/cover` | what's in the trash (size, days left, where it was) |
| `POST /api/trash/restore`, `POST /api/trash/purge` | restore / delete for good (`ids`, `bin`, `all`; restore: `into`) |
| `PUT /api/trash/settings` | keep time (`keepDays`: 7, 14, 30, 90 or 0 = until emptied; admin) |
| `POST /api/scan` | trigger rescan |
| `GET /api/jobs`, `GET /api/jobs/{id}` | background jobs (yours and the system's) |
| `POST /api/jobs/{id}/{pause\|resume\|cancel\|dismiss}` | control a job |
| `GET /api/events` | live stream (Server-Sent Events): job updates, "library changed" |

## Local development (no Docker)

```bash
pip install -r requirements.txt
LIBRARY_DIR=./Data CONFIG_DIR=./config uvicorn app.main:app --reload --port 9001
```

On Windows PowerShell: `$env:LIBRARY_DIR="./Data"; $env:CONFIG_DIR="./config"; uvicorn app.main:app --reload --port 9001`

## Not supported yet

On-device offline reading.

## Troubleshooting

### Chrome: hero banner flickers, goes blank or shows thin broken lines

**Symptom:** in Chrome (and other Chromium browsers), the big banner at the top of the home page sometimes shows faint 1px broken lines / streaks. It comes back when you hover something and disappears again after switching windows or scrolling. Firefox, and Chrome with graphics acceleration turned off, look fine.

**Cause:** not the reader — Chrome's newer GPU rendering engine ("Skia Graphite") mis-draws cached screen tiles with some graphics drivers (seen with recent NVIDIA drivers on Windows).

**Fix:** open `chrome://flags/#skia-graphite`, set it to **Disabled** and relaunch Chrome. Keep *Settings → System → Use graphics acceleration when available* **on**.
