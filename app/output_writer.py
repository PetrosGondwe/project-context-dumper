"""Output writing: character counting for token estimates, and optional
size-based chunking into multiple numbered part files.

Both dumper modules only ever call `.write(str)` and, between files,
`.checkpoint()` — so this is a drop-in replacement for a plain file handle
that adds counting and (optionally) rotation, with no changes needed to the
line-by-line writing logic in source_dumper.py / pdf_dumper.py.
"""
from __future__ import annotations

import glob as glob_module
import os
from pathlib import Path
from typing import List, Optional


def find_existing_outputs(out_dir: Path, base_name: str, ext: str) -> List[Path]:
    """Every file already on disk that a run with this base_name/ext could
    plausibly be about to (over)write: the plain single-file name, plus any
    previously chunked part files (possibly with a different part count
    than this run will produce)."""
    found: List[Path] = []
    single = out_dir / f"{base_name}{ext}"
    if single.exists():
        found.append(single)
    escaped = glob_module.escape(base_name)
    found.extend(sorted(out_dir.glob(f"{escaped}_part*_of_*{ext}")))
    return found


def estimate_tokens(char_count: int) -> int:
    """Rough, model-agnostic estimate: ~4 characters per token for
    English-heavy text/code. Real tokenizers vary — this is a ballpark for
    sizing against a context window, not a guarantee."""
    return max(0, char_count // 4)


class ChunkedDumpWriter:
    """A `.write()`-compatible target that can rotate to a new numbered part
    file once the current part exceeds `max_chunk_chars` characters.

    Rotation only happens inside `checkpoint()`, which callers invoke
    between logical units of work (after each source file / PDF is fully
    written) — so a single file's content is never split across two parts.

    Every part is written under a `.tmp` name; nothing gets its real,
    final name until `finalize()` succeeds, so a crash or cancellation
    never leaves a half-written file sitting at a real output path.
    """

    def __init__(self, out_dir: Path, base_name: str, ext: str, max_chunk_chars: Optional[int]):
        self.out_dir = out_dir
        self.base_name = base_name
        self.ext = ext if ext.startswith(".") else f".{ext}"
        self.max_chunk_chars = max_chunk_chars
        self.char_count = 0
        self._chunk_char_count = 0
        self._chunk_index = 1
        self._part_tmp_paths: List[Path] = []
        self._fh = None
        self._open_new_chunk()

    def _tmp_path(self, index: int) -> Path:
        return self.out_dir / f"{self.base_name}.part{index}.tmp"

    def _open_new_chunk(self) -> None:
        path = self._tmp_path(self._chunk_index)
        self._fh = open(path, "w", encoding="utf-8", newline="\n")
        self._part_tmp_paths.append(path)
        self._chunk_char_count = 0
        if self._chunk_index > 1:
            note = (
                f"# --- CONTINUED: part {self._chunk_index} of a multi-part dump "
                f"(split because a single part exceeded {self.max_chunk_chars:,} characters) ---\n\n"
            )
            self._fh.write(note)
            self.char_count += len(note)
            self._chunk_char_count += len(note)

    def write(self, s: str) -> int:
        self._fh.write(s)
        n = len(s)
        self.char_count += n
        self._chunk_char_count += n
        return n

    def flush(self) -> None:
        self._fh.flush()

    def fileno(self) -> int:
        return self._fh.fileno()

    def checkpoint(self) -> None:
        """Call between logical units of work; may rotate to a new part."""
        if self.max_chunk_chars is not None and self._chunk_char_count >= self.max_chunk_chars:
            self._fh.flush()
            os.fsync(self._fh.fileno())
            self._fh.close()
            self._chunk_index += 1
            self._open_new_chunk()

    def finalize(self, overwrite: bool) -> List[Path]:
        """Close the last part and atomically rename every part into place.

        Returns the final output paths, in order. Raises FileExistsError
        (and cleans up this run's own temp parts) if a conflicting output
        exists and `overwrite` is False.
        """
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()

        total = len(self._part_tmp_paths)
        if total == 1:
            targets = [self.out_dir / f"{self.base_name}{self.ext}"]
        else:
            targets = [
                self.out_dir / f"{self.base_name}_part{i}_of_{total}{self.ext}"
                for i in range(1, total + 1)
            ]

        existing = find_existing_outputs(self.out_dir, self.base_name, self.ext)
        conflicts = sorted({p for p in existing if p not in targets} | {p for p in targets if p.exists()}, key=str)

        if conflicts and not overwrite:
            self.cleanup()
            raise FileExistsError("Output file(s) already exist: " + ", ".join(str(p) for p in conflicts))

        for p in conflicts:
            try:
                p.unlink()
            except OSError:
                pass

        for tmp_path, final_path in zip(self._part_tmp_paths, targets):
            os.replace(tmp_path, final_path)

        return targets

    def cleanup(self) -> None:
        """Discard every part written so far (cancellation / error path)."""
        try:
            if self._fh and not self._fh.closed:
                self._fh.close()
        except Exception:
            pass
        for p in self._part_tmp_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
