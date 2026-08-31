"""Command-line interface for Project Context Dumper.

Useful for automation/CI, for headless environments without a display, and
as the fastest way to exercise the dumping engine without the GUI.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from .config import Config, default_config_path
from .dumper import Mode, NoSupportedFilesError, NotADirectoryProvided, run_dump

# Rough, deliberately conservative starting points for pasting into a web
# chat UI without file upload. Actual platform limits change over time and
# vary by plan/model — treat these as a reasonable default, not a promise.
CHUNK_PRESETS = {
    "chatgpt": 100_000,
    "claude": 350_000,
}


def _progress_printer(i: int, total: int, rel_path: str, phase: str, stream=sys.stdout) -> None:
    bar_len = 30
    frac = (i / total) if total else 0
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    short = rel_path if len(rel_path) <= 50 else "..." + rel_path[-47:]
    stream.write(f"\r[{bar}] {i}/{total} ({phase}) {short:<50}")
    stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="project-context-dumper",
        description="Dump a project's source code and/or PDF contents into a single UTF-8 text file.",
    )
    parser.add_argument("folder", type=Path, help="Folder to scan")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file path")
    parser.add_argument(
        "-m", "--mode", choices=[m.value for m in Mode], default=Mode.AUTO.value,
        help="auto (default): detect source/pdf/mixed automatically",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the output file(s) if they already exist")
    parser.add_argument("--include-hidden", action="store_true", help="Include dotfiles/dotdirs")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow symlinked directories (cycle-safe)")
    parser.add_argument("--max-file-size-mb", type=float, default=None, help="Per-source-file size limit in MB")
    parser.add_argument("--max-pdf-size-mb", type=float, default=None, help="Per-PDF size limit in MB")
    parser.add_argument("--config", type=Path, default=None, help="Path to a settings config.json to load")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    output_group = parser.add_argument_group("output shape")
    output_group.add_argument(
        "--stdout", action="store_true",
        help="Write the dump to stdout instead of a file, so it can be piped "
             "(e.g. `... --stdout | pbcopy` on macOS, `| clip` on Windows, "
             "`| xclip -selection clipboard` on Linux). All progress/summary "
             "output moves to stderr so stdout contains only the dump. "
             "Cannot be combined with --max-chunk-chars/--chunk-for.",
    )
    output_group.add_argument(
        "--max-chunk-chars", type=int, default=None,
        help="Split output into multiple '<name>_partN_ofM.txt' files, each capped at "
             "roughly this many characters (splits only between whole files, never mid-file).",
    )
    output_group.add_argument(
        "--chunk-for", choices=sorted(CHUNK_PRESETS), default=None,
        help="Shortcut for --max-chunk-chars using a rough preset sized for pasting "
             f"into that platform's web chat without file upload: {CHUNK_PRESETS}. "
             "These are conservative estimates, not guaranteed exact limits.",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.stdout and (args.max_chunk_chars or args.chunk_for):
        print("Error: --stdout cannot be combined with --max-chunk-chars/--chunk-for.", file=sys.stderr)
        return 2

    config = Config.load(args.config or default_config_path())
    if args.include_hidden:
        config.include_hidden = True
    if args.follow_symlinks:
        config.follow_symlinks = True
    if args.max_file_size_mb is not None:
        config.max_file_size_bytes = int(args.max_file_size_mb * 1024 * 1024)
    if args.max_pdf_size_mb is not None:
        config.max_pdf_size_bytes = int(args.max_pdf_size_mb * 1024 * 1024)
    if args.chunk_for:
        config.max_chunk_chars = CHUNK_PRESETS[args.chunk_for]
    elif args.max_chunk_chars is not None:
        config.max_chunk_chars = args.max_chunk_chars

    if args.stdout:
        return _run_stdout_mode(args, config)
    return _run_file_mode(args, config)


def _run_file_mode(args, config: Config) -> int:
    try:
        summary = run_dump(
            args.folder,
            config,
            output_path=args.output,
            mode=Mode(args.mode),
            overwrite=args.overwrite,
            progress_cb=None if args.quiet else _progress_printer,
        )
    except (NotADirectoryProvided, NoSupportedFilesError, FileExistsError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - CLI must always exit cleanly with a message
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 2

    if not args.quiet:
        print()

    if summary.cancelled:
        print("Cancelled — no output file was written.", file=sys.stderr)
        return 130

    _print_summary(summary, stream=sys.stdout)
    return 0


def _run_stdout_mode(args, config: Config) -> int:
    """Write the dump to a private temp location, then stream *only* the
    dump content to stdout — every diagnostic goes to stderr so the piped
    output stays clean (safe for `| pbcopy`, `| xclip`, etc.)."""
    progress = None if args.quiet else (lambda i, t, r, phase: _progress_printer(i, t, r, phase, stream=sys.stderr))
    with tempfile.TemporaryDirectory(prefix="pcd_stdout_") as td:
        temp_out = Path(td) / "dump.txt"
        try:
            summary = run_dump(
                args.folder, config, output_path=temp_out, mode=Mode(args.mode),
                overwrite=True, progress_cb=progress,
            )
        except (NotADirectoryProvided, NoSupportedFilesError) as e:
            print(f"\nError: {e}", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            print(f"\nUnexpected error: {e}", file=sys.stderr)
            return 2

        if not args.quiet:
            print(file=sys.stderr)

        if summary.cancelled:
            print("Cancelled — nothing was written to stdout.", file=sys.stderr)
            return 130

        _print_summary(summary, stream=sys.stderr)
        for part in summary.output_paths:
            sys.stdout.write(part.read_text(encoding="utf-8"))
    return 0


def _print_summary(summary, stream) -> None:
    print(f"Mode used      : {summary.mode_used}", file=stream)
    print(f"Source files   : {summary.source_file_count}", file=stream)
    print(f"PDF files      : {summary.pdf_file_count}", file=stream)
    print(f"Skipped/warned : {len(summary.skipped)}", file=stream)
    for rec in summary.skipped[:20]:
        print(f"  - {rec.path}: {rec.reason}", file=stream)
    if len(summary.skipped) > 20:
        print(f"  ... and {len(summary.skipped) - 20} more (see the output's SKIPPED section)", file=stream)
    print(f"Elapsed        : {summary.elapsed_seconds:.2f}s", file=stream)
    print(f"Characters     : {summary.char_count:,}", file=stream)
    print(f"Est. tokens    : ~{summary.estimated_tokens:,} (rough, ~4 chars/token heuristic)", file=stream)
    if len(summary.output_paths) > 1:
        print(f"Output         : {len(summary.output_paths)} parts, {summary.output_size_bytes:,} bytes total", file=stream)
        for p in summary.output_paths:
            print(f"  - {p}", file=stream)
    else:
        print(f"Output         : {summary.output_path} ({summary.output_size_bytes:,} bytes)", file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
