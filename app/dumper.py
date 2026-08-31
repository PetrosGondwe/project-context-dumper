"""Public orchestration API: run_dump().

Guarantees:
  * Atomic output — every part is written to a `.tmp` name first and only
    renamed into place once the whole run succeeds, so a crash or
    cancellation never leaves a half-written file at a real output name.
  * A cancelled run cleans up every temp part it created and returns a
    summary with `cancelled=True` rather than raising, so the GUI and CLI
    can handle it uniformly.
  * Optional size-based chunking (`config.max_chunk_chars`) splits the
    output into `name_part1_of_3.txt`-style files, always cutting between
    whole files, never mid-file.
  * Every skipped file anywhere in the pipeline ends up in one combined
    list, and is also appended as a visible "SKIPPED / WARNINGS" section.
  * The summary reports a character count and a rough, model-agnostic
    token estimate, useful for sizing the result against a chat paste
    limit or an API context window.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .config import Config
from .detector import DumpCancelled, SkipRecord, scan_directory
from .output_writer import ChunkedDumpWriter, estimate_tokens, find_existing_outputs
from .pdf_dumper import write_pdf_dump
from .source_dumper import write_source_dump


class Mode(str, Enum):
    AUTO = "auto"
    SOURCE = "source"
    PDF = "pdf"
    MIXED = "mixed"


class NoSupportedFilesError(Exception):
    """Raised when the scan finds nothing the requested mode can process."""


class NotADirectoryProvided(Exception):
    """Raised when the given root path is missing or not a directory."""


@dataclass
class DumpSummary:
    mode_used: str
    source_file_count: int
    pdf_file_count: int
    skipped: List[SkipRecord]
    output_path: Optional[Path]          # first (or only) output file, for convenience
    output_paths: List[Path] = field(default_factory=list)   # all parts, in order
    output_size_bytes: int = 0           # summed across all parts
    char_count: int = 0
    estimated_tokens: int = 0
    elapsed_seconds: float = 0.0
    cancelled: bool = False


ProgressCB = Optional[Callable[[int, int, str, str], None]]


def default_output_path(root: Path) -> Path:
    project_name = root.name.lower().replace(" ", "_")
    safe = "".join(c for c in project_name if c.isalnum() or c in "-_") or "project"
    return root.parent / f"{safe}_context_utf8.txt"


def _resolve_output_target(root: Path, output_path: Optional[Path]) -> Tuple[Path, str, str]:
    p = Path(output_path).resolve() if output_path else default_output_path(root).resolve()
    ext = p.suffix or ".txt"
    base_name = p.stem
    return p.parent, base_name, ext


def run_dump(
    root: Path,
    config: Config,
    output_path: Optional[Path] = None,
    mode: Mode = Mode.AUTO,
    overwrite: bool = False,
    cancel_event=None,
    progress_cb: ProgressCB = None,
) -> DumpSummary:
    start_time = time.monotonic()
    root = Path(root)

    if not root.exists():
        raise NotADirectoryProvided(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryProvided(f"Not a directory: {root}")
    if not os.access(root, os.R_OK):
        raise NotADirectoryProvided(f"No read permission for: {root}")

    out_dir, base_name, ext = _resolve_output_target(root, output_path)
    single_target = out_dir / f"{base_name}{ext}"

    if single_target.is_dir():
        raise NotADirectoryProvided(f"Output path is a directory, not a file: {single_target}")

    # Fail fast, before doing any scanning work, if a previous run's output
    # (single-file OR chunked) is sitting at this name and overwrite wasn't
    # requested. finalize() re-checks this authoritatively at the end too,
    # since this run's own chunk count isn't known until it's done.
    existing = find_existing_outputs(out_dir, base_name, ext)
    if existing and not overwrite:
        raise FileExistsError("Output file(s) already exist: " + ", ".join(str(p) for p in existing))

    scan = scan_directory(root, config, output_paths={single_target})

    if mode == Mode.AUTO:
        if scan.source_count > 0 and scan.pdf_count > 0:
            effective_mode = Mode.MIXED
        elif scan.source_count > 0:
            effective_mode = Mode.SOURCE
        elif scan.pdf_count > 0:
            effective_mode = Mode.PDF
        else:
            raise NoSupportedFilesError(
                f"No supported source-code or PDF files were found under {root}. Nothing to dump."
            )
    else:
        effective_mode = mode
        if effective_mode == Mode.SOURCE and scan.source_count == 0:
            raise NoSupportedFilesError(f"No source files found under {root}.")
        if effective_mode == Mode.PDF and scan.pdf_count == 0:
            raise NoSupportedFilesError(f"No PDF files found under {root}.")
        if effective_mode == Mode.MIXED and scan.source_count == 0 and scan.pdf_count == 0:
            raise NoSupportedFilesError(f"No supported files found under {root}.")

    total = 0
    if effective_mode in (Mode.SOURCE, Mode.MIXED):
        total += scan.source_count
    if effective_mode in (Mode.PDF, Mode.MIXED):
        total += scan.pdf_count

    skipped: List[SkipRecord] = list(scan.skipped)
    cancelled = False

    def _src_progress(i, t, r):
        if progress_cb:
            progress_cb(i, total, r, "source")

    def _pdf_progress(i, t, r):
        if progress_cb:
            progress_cb(i, total, r, "pdf")

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"Cannot create output directory {out_dir}: {e}") from e

    writer = ChunkedDumpWriter(out_dir, base_name, ext, config.max_chunk_chars)
    source_written = 0
    pdf_written = 0

    try:
        writer.write("=" * 80 + "\n")
        writer.write(f"PROJECT CONTEXT DUMP: {root.name}\n")
        writer.write(f"Source path : {root}\n")
        writer.write(f"Generated   : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        writer.write(f"Mode        : {effective_mode.value}\n")
        writer.write("=" * 80 + "\n")

        if effective_mode == Mode.MIXED:
            writer.write("\n" + "#" * 80 + "\n# SECTION 1: SOURCE CODE\n" + "#" * 80 + "\n")
        if effective_mode in (Mode.SOURCE, Mode.MIXED):
            source_written = write_source_dump(
                writer, root, scan.dirs, config, skipped,
                progress_cb=_src_progress, cancel_event=cancel_event,
                start_index=0, total=total,
            )

        if effective_mode == Mode.MIXED:
            writer.write("\n\n" + "#" * 80 + "\n# SECTION 2: PDF DOCUMENTS\n" + "#" * 80 + "\n")
        if effective_mode in (Mode.PDF, Mode.MIXED):
            pdf_written = write_pdf_dump(
                writer, root, scan.dirs, config, skipped,
                progress_cb=_pdf_progress, cancel_event=cancel_event,
                start_index=scan.source_count if effective_mode == Mode.MIXED else 0,
                total=total,
            )

        if skipped:
            writer.write("\n\n" + "=" * 80 + "\n")
            writer.write(f"SKIPPED / WARNINGS ({len(skipped)})\n")
            writer.write("=" * 80 + "\n")
            for rec in skipped:
                try:
                    rel = rec.path.relative_to(root)
                except ValueError:
                    rel = rec.path
                writer.write(f"- {rel}: {rec.reason}\n")

    except (DumpCancelled, KeyboardInterrupt):
        cancelled = True
        writer.cleanup()
    except Exception:
        # Any unexpected failure mid-write must not leave partial temp
        # files lying around either.
        writer.cleanup()
        raise

    final_paths: List[Path] = []
    char_count = writer.char_count
    if not cancelled:
        final_paths = writer.finalize(overwrite=overwrite)

    elapsed = time.monotonic() - start_time
    size = sum(p.stat().st_size for p in final_paths) if final_paths else 0

    return DumpSummary(
        mode_used=effective_mode.value,
        source_file_count=source_written,
        pdf_file_count=pdf_written,
        skipped=skipped,
        output_path=final_paths[0] if final_paths else None,
        output_paths=final_paths,
        output_size_bytes=size,
        char_count=char_count if not cancelled else 0,
        estimated_tokens=estimate_tokens(char_count) if not cancelled else 0,
        elapsed_seconds=elapsed,
        cancelled=cancelled,
    )
