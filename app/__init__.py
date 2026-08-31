"""Project Context Dumper.

A production-grade tool that consolidates a project's source code and/or a
collection of PDF documents into a single UTF-8 text file — typically for
feeding as context to an AI assistant, or for archival/review purposes.

Package layout
--------------
config.py        Persisted user configuration (excludes, extensions, limits).
detector.py       Single-pass filesystem walk + auto content-type detection.
source_dumper.py  Renders the "source code" section of the output.
pdf_dumper.py     Renders the "PDF text extraction" section of the output.
dumper.py         Orchestrates scan -> dump -> atomic write; the public API.
worker.py         Qt background-thread wrapper around dumper.run_dump.
gui.py            PySide6 desktop UI (drag & drop, settings, progress).
cli.py            Headless command-line interface for automation/CI.
"""

__version__ = "1.0.0"
