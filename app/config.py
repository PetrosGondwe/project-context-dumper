"""User-configurable settings for Project Context Dumper.

Everything a user might reasonably want to tweak — exclusion lists, size
limits, hidden-file handling — lives here as a single serializable dataclass
so the GUI, CLI, and test-suite all share one source of truth.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Set

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDED_DIRS: Set[str] = {
    "__pycache__", ".git", ".hg", ".svn", ".vscode", ".idea", ".vs",
    "node_modules", "venv", ".venv", "env", "virtualenv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    "dist", "build", ".next", ".nuxt", ".vercel", "out",
    "target", "bin", "obj", "vendor", ".gradle", ".terraform",
    "coverage", "htmlcov", "site-packages", ".ipynb_checkpoints",
    "__MACOSX", ".cache", ".parcel-cache",
}

DEFAULT_INCLUDE_EXT: Set[str] = {
    ".py", ".pyi", ".ipynb",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx",
    ".java", ".kt", ".kts", ".scala",
    ".cs", ".go", ".rs", ".php", ".rb", ".swift", ".m", ".mm",
    ".json", ".jsonc", ".txt", ".md", ".rst", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".csv", ".tsv", ".xml",
    ".sh", ".bash", ".zsh", ".bat", ".ps1", ".sql", ".graphql",
    ".proto", ".vue", ".svelte",
}

# Exact filenames (not extensions) that should always be included, even
# though they either have no extension or an unusual dotted name.
DEFAULT_SPECIAL_FILENAMES: Set[str] = {
    "Dockerfile", "dockerfile", "Makefile", "makefile",
    "CMakeLists.txt", ".gitignore", ".dockerignore", ".editorconfig",
    ".npmrc", ".babelrc", ".eslintrc", ".env.sample", ".env.example",
    "requirements.txt", "Pipfile", "pyproject.toml",
    "package.json", "tsconfig.json", "go.mod", "Cargo.toml",
    "README", "LICENSE", "Procfile",
}

# Filenames that ARE text but are auto-generated, huge, and low context
# value. Excluded by default; the user can remove them in Settings.
DEFAULT_EXCLUDED_FILENAMES: Set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum",
}

# Glob patterns matching this tool's own previous output, so re-running the
# dumper on a project never recursively ingests an earlier dump.
DEFAULT_OUTPUT_GLOB_PATTERNS: Set[str] = {
    "*_context_utf8.txt", "*_context_utf8.txt.tmp",
}

DEFAULT_MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024        # 2 MB per source file
DEFAULT_MAX_PDF_SIZE_BYTES = 300 * 1024 * 1024       # 300 MB per PDF
DEFAULT_BINARY_SNIFF_BYTES = 8192
DEFAULT_MAX_DEPTH = 200


@dataclass
class Config:
    excluded_dirs: Set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRS))
    include_ext: Set[str] = field(default_factory=lambda: set(DEFAULT_INCLUDE_EXT))
    special_filenames: Set[str] = field(default_factory=lambda: set(DEFAULT_SPECIAL_FILENAMES))
    excluded_filenames: Set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_FILENAMES))
    output_glob_patterns: Set[str] = field(default_factory=lambda: set(DEFAULT_OUTPUT_GLOB_PATTERNS))
    include_hidden: bool = False
    follow_symlinks: bool = False
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_pdf_size_bytes: int = DEFAULT_MAX_PDF_SIZE_BYTES
    binary_sniff_bytes: int = DEFAULT_BINARY_SNIFF_BYTES
    max_depth: int = DEFAULT_MAX_DEPTH
    use_charset_normalizer: bool = True
    max_chunk_chars: Optional[int] = None

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, set):
                d[k] = sorted(v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        defaults = cls()
        kwargs = {}
        for name, f in defaults.__dataclass_fields__.items():
            if name in d:
                val = d[name]
                if isinstance(getattr(defaults, name), set) and isinstance(val, (list, set, tuple)):
                    val = set(val)
                kwargs[name] = val
        return cls(**kwargs)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return cls()
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, TypeError):
            # A corrupt or hand-edited config file must never crash the app.
            return cls()


def default_config_path() -> Path:
    """Platform-appropriate location for the persisted settings file."""
    app_name = "ProjectContextDumper"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / app_name / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name / "config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "project-context-dumper" / "config.json"
