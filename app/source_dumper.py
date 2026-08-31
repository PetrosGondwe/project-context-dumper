"""Renders the source-code section of the dump.

Everything streams directly into the caller's open file handle — no giant
in-memory string is ever built — so this scales to repositories with tens of
thousands of files without ballooning memory use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .config import Config
from .detector import DirEntry, DumpCancelled, SkipRecord

try:
    from charset_normalizer import from_bytes as _cn_from_bytes
    _HAS_CHARSET_NORMALIZER = True
except ImportError:  # optional dependency
    _HAS_CHARSET_NORMALIZER = False

ProgressCB = Optional[Callable[[int, int, str], None]]

# Bytes considered "plausibly text" for the binary-content heuristic.
_TEXT_BYTES = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})


def _looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    nontext = sum(b not in _TEXT_BYTES for b in sample)
    return (nontext / len(sample)) > 0.30


def read_text_best_effort(path: Path, max_size: int, use_charset_normalizer: bool = True) -> Tuple[Optional[str], Optional[str]]:
    """Read a text file as robustly as possible.

    Returns (content, note). `content` is None when the file was skipped
    entirely (too large / binary / unreadable), in which case `note`
    explains why. Otherwise `content` is a string and `note` is either None
    (clean UTF-8) or a short explanation of a fallback that was applied.
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return None, f"cannot stat file: {e}"

    if size > max_size:
        return None, f"skipped: file too large ({size:,} bytes, limit is {max_size:,} bytes)"
    if size == 0:
        return "", None

    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        return None, f"cannot read file: {e}"

    if _looks_binary(raw[:8192]):
        return None, "skipped: file appears to be binary, not text"

    for enc in ("utf-8", "utf-8-sig"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue

    if use_charset_normalizer and _HAS_CHARSET_NORMALIZER:
        try:
            best = _cn_from_bytes(raw).best()
            if best is not None:
                return str(best), f"note: not valid UTF-8; decoded using detected encoding '{best.encoding}'"
        except Exception:
            pass

    return (
        raw.decode("utf-8", errors="replace"),
        "note: not valid UTF-8 and no reliable encoding could be detected; invalid bytes were replaced",
    )


def build_tree_lines(root_name: str, dirs: List[DirEntry], kind: str) -> List[str]:
    """kind is 'source' or 'pdf' — selects which file list per directory to render."""
    lines = [f"{root_name}/"]
    for d in dirs:
        files = d.source_files if kind == "source" else d.pdf_files
        if not files:
            continue
        if str(d.rel_dir) != ".":
            depth = len(d.rel_dir.parts)
            indent = "  " * (depth - 1)
            lines.append(f"{indent}+-- {d.rel_dir.name}/")
        depth_for_files = len(d.rel_dir.parts) if str(d.rel_dir) != "." else 0
        sub_indent = "  " * depth_for_files
        for f in files:
            lines.append(f"{sub_indent}   +-- {f}")
    return lines


def write_source_dump(
    out_fh,
    root: Path,
    dirs: List[DirEntry],
    config: Config,
    skipped: List[SkipRecord],
    progress_cb: ProgressCB = None,
    cancel_event=None,
    start_index: int = 0,
    total: int = 0,
) -> int:
    """Streams the source-code section into `out_fh`. Returns files written."""
    out_fh.write("=" * 80 + "\n")
    out_fh.write("SOURCE CODE PROJECT STRUCTURE\n")
    out_fh.write("=" * 80 + "\n")
    for line in build_tree_lines(root.name, dirs, "source"):
        out_fh.write(line + "\n")
    out_fh.write("\n" + "=" * 80 + "\n")
    out_fh.write("FILE CONTENTS\n")
    out_fh.write("=" * 80 + "\n")

    written = 0
    idx = start_index
    for d in dirs:
        for fname in d.source_files:
            if cancel_event is not None and cancel_event.is_set():
                raise DumpCancelled()
            idx += 1
            rel = (d.rel_dir / fname) if str(d.rel_dir) != "." else Path(fname)
            fpath = root / rel
            if progress_cb:
                progress_cb(idx, total, str(rel))

            content, note = read_text_best_effort(fpath, config.max_file_size_bytes, config.use_charset_normalizer)
            out_fh.write(f"\n\n--- FILE: {rel} ---\n")
            if content is None:
                skipped.append(SkipRecord(fpath, note or "skipped"))
                out_fh.write(f"[{note}]\n")
                if hasattr(out_fh, "checkpoint"):
                    out_fh.checkpoint()
                continue
            if note:
                out_fh.write(f"[{note}]\n")
            if content == "":
                out_fh.write("[empty file]\n")
            else:
                out_fh.write(content)
                if not content.endswith("\n"):
                    out_fh.write("\n")
            written += 1

            if hasattr(out_fh, "checkpoint"):
                out_fh.checkpoint()
    return written
