"""Filesystem scanning and content-type auto-detection.

Design goals:
  * ONE walk of the tree produces everything both the detector and the two
    dumpers need — no redundant IO on large repos.
  * Never crash on a hostile or merely messy filesystem: permission errors,
    broken symlinks, symlink cycles, and unreadable directories are recorded
    as SkipRecords and processing continues.
  * Never re-ingest the tool's own previous output file.
  * Iterative (stack-based) traversal — no recursion-depth limits from
    Python's call stack, only an explicit, configurable max_depth guard.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .config import Config


class DumpCancelled(Exception):
    """Raised internally to unwind processing when the user cancels."""


@dataclass
class SkipRecord:
    path: Path
    reason: str


@dataclass
class DirEntry:
    rel_dir: Path
    source_files: List[str] = field(default_factory=list)
    pdf_files: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    root: Path
    dirs: List[DirEntry]
    source_count: int
    pdf_count: int
    skipped: List[SkipRecord]


def _is_hidden(name: str) -> bool:
    return name.startswith(".") and name not in (".", "..")


def _matches_any_glob(name: str, patterns: Set[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _is_pdf(name: str) -> bool:
    return name.lower().endswith(".pdf")


def _is_source(name: str, config: Config) -> bool:
    if name in config.special_filenames:
        return True
    return Path(name).suffix.lower() in config.include_ext


def scan_directory(
    root: Path,
    config: Config,
    output_paths: Optional[Set[Path]] = None,
) -> ScanResult:
    """Walk `root` once, classifying every file as source / pdf / ignored.

    `output_paths` should contain the resolved final-output and temp-output
    paths for the *current run*, so the dumper never scans/ingests the file
    it is currently writing (or about to write).
    """
    try:
        root = root.resolve()
    except OSError:
        root = Path(root)

    resolved_outputs: Set[Path] = set()
    for p in output_paths or ():
        try:
            resolved_outputs.add(p.resolve())
        except OSError:
            resolved_outputs.add(p)

    dirs: List[DirEntry] = []
    skipped: List[SkipRecord] = []
    source_count = 0
    pdf_count = 0

    visited_real_dirs: Set[Path] = {root}
    # Explicit stack -> DFS without Python recursion limits.
    stack: List[Tuple[Path, Path, int]] = [(root, Path("."), 0)]

    while stack:
        abs_dir, rel_dir, depth = stack.pop()

        if config.max_depth is not None and depth > config.max_depth:
            skipped.append(SkipRecord(abs_dir, f"max directory depth ({config.max_depth}) exceeded"))
            continue

        try:
            entries = list(os.scandir(abs_dir))
        except PermissionError:
            skipped.append(SkipRecord(abs_dir, "permission denied listing directory"))
            continue
        except FileNotFoundError:
            # Directory vanished between being queued and being scanned.
            skipped.append(SkipRecord(abs_dir, "directory disappeared during scan"))
            continue
        except OSError as e:
            skipped.append(SkipRecord(abs_dir, f"cannot list directory: {e}"))
            continue

        entry = DirEntry(rel_dir=rel_dir)
        subdirs: List[Tuple[Path, Path, int]] = []

        for de in sorted(entries, key=lambda e: e.name.lower()):
            name = de.name

            try:
                is_symlink = de.is_symlink()
            except OSError:
                is_symlink = False

            try:
                # follow_symlinks=True here just to learn the *target's*
                # type; whether we actually descend is decided below.
                is_dir = de.is_dir(follow_symlinks=True)
            except OSError as e:
                skipped.append(SkipRecord(Path(de.path), f"broken symlink or inaccessible entry: {e}"))
                continue

            if is_dir:
                if name in config.excluded_dirs:
                    continue
                if _is_hidden(name) and not config.include_hidden:
                    continue
                child_abs = Path(de.path)

                if is_symlink:
                    if not config.follow_symlinks:
                        skipped.append(
                            SkipRecord(child_abs, "symlinked directory not followed (follow_symlinks disabled)")
                        )
                        continue
                    try:
                        child_real = child_abs.resolve()
                    except OSError:
                        skipped.append(SkipRecord(child_abs, "cannot resolve symlink target"))
                        continue
                    if child_real in visited_real_dirs:
                        skipped.append(SkipRecord(child_abs, "symlink cycle detected — not followed again"))
                        continue
                    visited_real_dirs.add(child_real)

                subdirs.append((child_abs, rel_dir / name, depth + 1))
                continue

            # --- it's a file (possibly reached via a symlink) -------------
            file_abs = Path(de.path)

            if is_symlink:
                # DirEntry.is_dir()/is_file() silently return False for a
                # broken symlink rather than raising, so a dangling link
                # would otherwise slip through as an ordinary (unreadable)
                # file. Explicitly confirm the target is reachable first.
                try:
                    os.stat(de.path)
                except OSError as e:
                    skipped.append(SkipRecord(file_abs, f"broken symlink: {e}"))
                    continue

            try:
                file_real = file_abs.resolve()
            except OSError:
                file_real = file_abs
            if file_real in resolved_outputs:
                continue
            if _matches_any_glob(name, config.output_glob_patterns):
                continue

            if _is_hidden(name) and name not in config.special_filenames and not config.include_hidden:
                continue

            if name in config.excluded_filenames:
                skipped.append(SkipRecord(file_abs, "excluded filename (e.g. lockfile) — see Settings"))
                continue

            if _is_pdf(name):
                entry.pdf_files.append(name)
                pdf_count += 1
            elif _is_source(name, config):
                entry.source_files.append(name)
                source_count += 1
            # else: not a tracked type — silently ignored, not an error.

        if entry.source_files or entry.pdf_files:
            dirs.append(entry)

        stack.extend(subdirs)

    dirs.sort(key=lambda d: str(d.rel_dir).lower())

    return ScanResult(
        root=root,
        dirs=dirs,
        source_count=source_count,
        pdf_count=pdf_count,
        skipped=skipped,
    )
