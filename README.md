# Project Context Dumper

![Main window](docs/screenshot_main.png)

A desktop app (and CLI) that consolidates a project's **source code** and/or
a collection of **PDF documents** into a single UTF‑8 text file — the kind
of thing you feed to an AI assistant as background context, or keep as a
point‑in-time archive/review artifact.

Drop a folder onto the window (or pick one with a button), the app
auto-detects whether it's a source-code project, a PDF collection, or a mix
of both, and writes one clean `.txt` file with a directory tree followed by
every file's contents.

---

## Why this exists

This started from two ad-hoc PowerShell/Python one-off scripts (dump source
tree → txt, dump PDF text → txt). This project turns that into an actual
application: a GUI, a config system, a background thread so the UI never
freezes, and — the bulk of the engineering effort — **a scanner and two
writers that have been hardened against the many ways a real filesystem and
real PDFs go wrong.**

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
# optional, better encoding detection for non-UTF-8 source files:
pip install -r requirements-optional.txt
```

Requires Python 3.9+.

## Run

**GUI:**
```bash
python main.py
```

**CLI** (for automation, CI, or headless boxes without a display):
```bash
python -m app.cli /path/to/project -o out.txt
python -m app.cli /path/to/project --mode pdf --overwrite
python -m app.cli --help
```

## Package as a standalone executable

```bash
pip install pyinstaller
pyinstaller pyinstaller.spec
# -> dist/ProjectContextDumper  (or .exe / .app)
```

---

## Architecture

```
app/
  config.py          Config dataclass: excludes, extensions, size limits,
                      hidden/symlink policy. JSON-persisted per-OS.
  detector.py         scan_directory(): ONE filesystem walk that classifies
                      every file as source / pdf / ignored, and records
                      every structural problem (permissions, broken
                      symlinks, cycles, depth) as a SkipRecord instead of
                      raising.
  source_dumper.py    Streams the "source code" section straight into the
                      output file handle: builds the tree, then per file
                      does binary-sniffing, size-limiting, and a UTF-8 ->
                      UTF-8-sig -> charset-normalizer -> replace-errors
                      decode ladder.
  pdf_dumper.py       Streams the "PDF" section: per-file AND per-page
                      try/except (pdfplumber), encrypted/corrupt/0-page/
                      empty-file handling, and cache-flushing so huge PDFs
                      don't balloon memory.
  dumper.py           run_dump(): the public API. Resolves AUTO/SOURCE/
                      PDF/MIXED mode, streams into an atomic, optionally
                      chunked writer — a crash or cancellation never
                      corrupts a previous good dump.
  output_writer.py    ChunkedDumpWriter: character counting, optional
                      size-based rotation into `_partN_ofM` files (only
                      ever between whole files), and atomic finalize/
                      cleanup including detection of stale leftover parts
                      from a differently-sized previous run.
  worker.py           QObject + moveToThread wrapper so the GUI thread
                      never blocks.
  gui.py              PySide6 window: drag-and-drop, folder picker, mode
                      selector, an embedded Settings page (a QStackedWidget
                      page swap, not a separate popup window), progress
                      bar, cancel, "open containing folder", "copy to
                      clipboard", and a Help → About dialog.
  cli.py              argparse-based headless interface, same engine, plus
                      `--stdout` (clean, pipeable output) and
                      `--max-chunk-chars` / `--chunk-for`.
tests/                79 tests covering the engine end-to-end (see below).
```

Both the GUI and the CLI are thin shells around `dumper.run_dump()` — there
is exactly one code path that actually reads the filesystem and writes the
output, so behavior is identical whether you use a mouse or a script.

### Why PySide6 instead of PyQt5

The original design sketch suggested PyQt5. This build uses **PySide6**
(Qt 6, official Qt-for-Python bindings) instead: it's LGPL-licensed, so this
tool (or anything built on it) can be distributed without a commercial Qt
license or GPL copyleft obligations, and it gets Qt 6's rendering/HiDPI
improvements for free.

### Visual design

The look is deliberately not a generic SaaS skin — the tool's entire job is
turning a sprawling project into one precise document, so the interface
borrows from technical drawings: a deep blueprint-navy base, a single brass
accent used only for primary actions and highlights, flat zero-radius
controls (no cards, no drop shadows, no gradients), and a monospace face
reserved for anything that's genuinely path/code-like — the folder path,
the output field, the exclude/extension lists, and the results readout —
rather than used decoratively. Settings are grouped into labeled sections
(Exclusions, Size Limits, Traversal, Output Splitting) instead of one long
scrolling form. Tokens and rationale live in `app/theme.py`.

![Settings page](docs/screenshot_settings.png)

---

## Edge cases handled (and why each matters)

| Category | Handling |
|---|---|
| **Re-running on the same project** | Previous `*_context_utf8.txt` output files are excluded from the scan by glob pattern *and* the exact current output/temp path is excluded by resolved path — re-running never recursively ingests an earlier dump. |
| **Crash / cancel mid-write** | Output is written to `<name>.tmp` first; only `os.replace()`d to the final name on success. A cancelled or crashed run leaves the *previous* good output untouched and cleans up its own temp file. |
| **Symlink cycles** | A symlinked directory pointing back at an ancestor (directly or via a chain) is detected via a visited-real-path set and skipped with a reason, instead of hanging forever. |
| **Symlinked dirs by default** | Not followed by default (matches `os.walk`'s safe default); opt-in via Settings / `--follow-symlinks`, cycle-safe either way. |
| **Broken symlinks** | `DirEntry.is_dir()` silently swallows the stat error for a dangling symlink and returns `False` — this is explicitly detected and reported as "broken symlink" rather than being misread as a normal (unreadable) file. |
| **Permission-denied directories** | Caught per-directory; that subtree is skipped and noted, the rest of the scan continues. |
| **Directory disappears mid-scan** | `FileNotFoundError` from a TOCTOU race is caught, not fatal. |
| **Pathological deep nesting** | Iterative (stack-based) traversal — never hits Python's recursion limit — plus a configurable `max_depth` circuit-breaker. |
| **Binary files with a "text" extension** | First 8 KB sniffed for null bytes / high non-text-byte ratio before reading; skipped with a note rather than dumping garbage. |
| **Oversized files** | Per-file (default 2 MB) and per-PDF (default 300 MB) size ceilings, configurable; oversized files are skipped with the actual size shown, not silently truncated. |
| **Non-UTF-8 source files** | Decode ladder: UTF-8 → UTF-8-with-BOM → `charset-normalizer` (if installed) → UTF-8 with `errors='replace'` as a last resort — each fallback is annotated in the output so it's clear where the text may be imperfect. |
| **Lockfiles / generated files** | `package-lock.json`, `yarn.lock`, `poetry.lock`, etc. excluded by default (huge, near-zero value as AI context); fully configurable in Settings. |
| **Hidden files/dirs** | Excluded by default; `.gitignore`/`.editorconfig`/etc. are explicitly whitelisted even while hidden-exclusion is on; a checkbox/flag re-enables all dotfiles. |
| **Encrypted / password-protected PDFs** | Detected from the underlying error and reported clearly instead of crashing the whole run. |
| **Corrupt / non-PDF-despite-extension files** | Caught at `pdfplumber.open()`; reported per-file, rest of the batch continues. |
| **One bad page in an otherwise-good PDF** | Page-level try/except — a single malformed page is reported inline; the other 500 pages still extract normally. |
| **0-page / 0-byte PDFs** | Explicitly detected and reported rather than raising deep inside pdfplumber. |
| **Large multi-hundred-page PDFs** | `page.flush_cache()` after each page to bound memory growth. |
| **Huge repos (memory)** | Nothing is ever built as one giant in-memory string — both dumpers stream directly into the open output file handle. |
| **Output path is a directory / unwritable / already exists** | Each is checked explicitly with a clear error before any work starts; existing-file requires an explicit overwrite (confirmed in the GUI, `--overwrite` flag in the CLI). |
| **Nothing found at all** | Clear `NoSupportedFilesError` instead of silently writing an empty/near-empty file. |
| **Corrupt settings file** | `Config.load()` falls back to defaults on any JSON/type error rather than crashing app startup. |
| **User cancels mid-run** | Cooperative cancellation via a `threading.Event` checked between every file (and every PDF page); GUI and CLI both surface it as "cancelled", not an error. |
| **Closing the GUI mid-run** | Confirms with the user, cancels the worker, waits for the background thread to actually stop before the window closes (verified with a real `QApplication.exec()` lifecycle — no "thread destroyed while running" issues). |
| **Dropping the wrong thing on the drop zone** | Multiple folders, individual files, or non-local URLs are rejected with a specific message rather than silently doing the wrong thing. |
| **Chunked output re-run producing fewer parts than before** | Stale leftover parts from a larger previous run (e.g. old `_part3_of_3.txt` when this run only makes 2 parts) are detected and cleaned up during finalize, never orphaned. |
| **`--stdout` mixed with progress/summary output** | All diagnostics move to stderr in this mode; stdout carries only the dump text, so `... --stdout \| pbcopy` never picks up a progress bar or summary line by accident. |
| **Chunk size smaller than a single file** | A file's content is never split mid-write — only checkpointed between files — so a part may legitimately exceed the requested chunk size when one file is larger than the limit. |

All of the above (except the couple of GUI-specific rows) are covered by
automated tests, including real symlink loops, real permission-denied
directories (run as a non-root user), a real corrupt PDF, and a real
Latin‑1-encoded source file — not just mocked-out assumptions.

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
```

79 tests, well under a second, covering config persistence, the scanner,
both dumpers, the chunked/atomic output writer, the orchestrator (mode
resolution, cancellation, overwrite protection, chunking), and the CLI
(including `--stdout` and chunk presets). GUI logic (drag-and-drop validation, settings
round-trip, the full threaded run-and-cancel lifecycle) was additionally
smoke-tested against a real `QApplication` using Qt's offscreen platform
plugin (`QT_QPA_PLATFORM=offscreen`), including a full `app.exec()` start-to
-quit cycle to confirm clean thread teardown.

## Configuration

Settings are stored as JSON at the OS-appropriate location
(`~/.config/project-context-dumper/config.json` on Linux,
`~/Library/Application Support/ProjectContextDumper/config.json` on macOS,
`%APPDATA%\ProjectContextDumper\config.json` on Windows) and are editable
either through the GUI's Settings dialog or by passing `--config path.json`
to the CLI. Fields: `excluded_dirs`, `include_ext`, `special_filenames`,
`excluded_filenames`, `output_glob_patterns`, `include_hidden`,
`follow_symlinks`, `max_file_size_bytes`, `max_pdf_size_bytes`,
`binary_sniff_bytes`, `max_depth`, `use_charset_normalizer`,
`max_chunk_chars`.

## Sizing output for chat/context limits

Every summary (GUI and CLI) now reports a character count and a rough,
model-agnostic token estimate (`chars / 4`, a common heuristic — real
tokenizers vary, especially for code and non-Latin text, so treat it as a
ballpark for sizing against a context window, not an exact count).

**Piping straight into another tool or clipboard (CLI):**
```bash
python -m app.cli . --stdout | pbcopy                       # macOS
python -m app.cli . --stdout | clip                         # Windows
python -m app.cli . --stdout | xclip -selection clipboard   # Linux
python -m app.cli . --stdout > /tmp/context.txt              # or just redirect
```
In `--stdout` mode, *only* the dump content goes to stdout — all progress
and summary output moves to stderr, so the pipe stays clean. Nothing is
written to the project directory either. (`--stdout` can't be combined with
chunking below — pick one output shape.)

**Copy to clipboard (GUI):** a "Copy to Clipboard" button appears after a
run completes, enabled whenever the result is a single file.

**Splitting output that's too big to paste in one go:**
```bash
python -m app.cli . --max-chunk-chars 100000              # custom size
python -m app.cli . --chunk-for chatgpt                     # rough preset, ~100k chars
python -m app.cli . --chunk-for claude                       # rough preset, ~350k chars
```
This produces `name_part1_of_3.txt`, `name_part2_of_3.txt`, etc. Splitting
only ever happens *between* whole files — a single file's content is never
divided across two parts, so a part may run a little over the target size
if it ends on a large file. The same option is available in the GUI's
Settings dialog, with the same two presets. Presets are deliberately
conservative starting points, not guaranteed platform limits, since those
change over time — check the platform's current limit if it matters.


## Known limitations / possible future work

- No `.gitignore`-aware filtering (uses its own exclude list instead).
- No password-prompt flow for encrypted PDFs (reported as skipped instead).
- No OCR fallback for scanned/image-only PDF pages (reported as
  "no extractable text" instead — wiring in an OCR engine would be a
  reasonable extension).
- No resume-from-checkpoint for cancelled runs on extremely large trees.

## About

Project Context Dumper is developed by **Chipu_Data_Labs**. The same
information is available in the app under Help → About.

