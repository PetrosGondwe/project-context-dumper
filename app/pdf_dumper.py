"""Renders the PDF-text-extraction section of the dump.

Each PDF, and each page within it, is wrapped in its own try/except so that
one corrupt file or one malformed page never aborts the whole run — it is
recorded as a skip/warning instead and processing continues.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import pdfplumber

from .config import Config
from .detector import DirEntry, DumpCancelled, SkipRecord
from .source_dumper import build_tree_lines

ProgressCB = Optional[Callable[[int, int, str], None]]


def _extract_pdf_text(fpath: Path, max_size: int, cancel_event=None) -> str:
    try:
        size = fpath.stat().st_size
    except OSError as e:
        return f"[cannot stat file: {e}]"

    if size > max_size:
        return f"[skipped: PDF too large ({size:,} bytes, limit is {max_size:,} bytes)]"
    if size == 0:
        return "[skipped: file is empty (0 bytes)]"

    out: List[str] = []
    try:
        with pdfplumber.open(fpath) as pdf:
            total_pages = len(pdf.pages)
            if total_pages == 0:
                return "[PDF opened successfully but contains 0 pages]"
            for i, page in enumerate(pdf.pages, start=1):
                if cancel_event is not None and cancel_event.is_set():
                    raise DumpCancelled()
                out.append(f"\n--- Page {i}/{total_pages} ---")
                try:
                    text = page.extract_text()
                except Exception as e:  # a single malformed page must not kill the file
                    out.append(f"[ERROR extracting text from page {i}: {e}]")
                    text = None
                if text:
                    out.append(text)
                else:
                    out.append(
                        "[No extractable text on this page — possibly scanned/image-only, "
                        "or a vector/form-only page]"
                    )
                # Large multi-hundred-page PDFs can otherwise accumulate
                # significant cached layout data in memory.
                try:
                    page.flush_cache()
                except Exception:
                    pass
    except DumpCancelled:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg or "encrypt" in msg:
            return f"[ERROR: PDF appears to be password-protected/encrypted and could not be opened: {e}]"
        return f"[ERROR opening/reading PDF — file may be corrupt: {e}]"

    return "\n".join(out)


def write_pdf_dump(
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
    """Streams the PDF section into `out_fh`. Returns files processed."""
    out_fh.write("=" * 80 + "\n")
    out_fh.write("PDF COLLECTION STRUCTURE\n")
    out_fh.write("=" * 80 + "\n")
    for line in build_tree_lines(root.name, dirs, "pdf"):
        out_fh.write(line + "\n")
    out_fh.write("\n" + "=" * 80 + "\n")
    out_fh.write("PDF TEXT EXTRACTION\n")
    out_fh.write("=" * 80 + "\n")

    written = 0
    idx = start_index
    for d in dirs:
        for fname in d.pdf_files:
            if cancel_event is not None and cancel_event.is_set():
                raise DumpCancelled()
            idx += 1
            rel = (d.rel_dir / fname) if str(d.rel_dir) != "." else Path(fname)
            fpath = root / rel
            if progress_cb:
                progress_cb(idx, total, str(rel))

            out_fh.write(f"\n\n--- FILE: {rel} ---\n")
            result = _extract_pdf_text(fpath, config.max_pdf_size_bytes, cancel_event)
            if result.startswith(("[ERROR", "[skipped", "[cannot")):
                skipped.append(SkipRecord(fpath, result.strip("[]")))
            out_fh.write(result + "\n")
            written += 1

            if hasattr(out_fh, "checkpoint"):
                out_fh.checkpoint()
    return written
