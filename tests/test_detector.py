import os
import sys

import pytest

from app.config import Config
from app.detector import scan_directory


def _names(paths, root):
    return sorted(str(p.relative_to(root)) for p in paths)


def all_source_paths(scan):
    return [scan.root / d.rel_dir / f for d in scan.dirs for f in d.source_files]


def all_pdf_paths(scan):
    return [scan.root / d.rel_dir / f for d in scan.dirs for f in d.pdf_files]


def test_basic_classification(tmp_path, config):
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "image.png").write_bytes(b"\x89PNG fake")  # untracked type

    result = scan_directory(tmp_path, config)
    assert result.source_count == 1
    assert result.pdf_count == 1
    assert _names(all_source_paths(result), tmp_path) == ["main.py"]
    assert _names(all_pdf_paths(result), tmp_path) == ["doc.pdf"]


def test_excluded_dirs_are_skipped(tmp_path, config):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("x", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("x", encoding="utf-8")

    result = scan_directory(tmp_path, config)
    assert result.source_count == 1
    assert _names(all_source_paths(result), tmp_path) == ["src/app.js"]


def test_hidden_files_excluded_by_default(tmp_path, config):
    (tmp_path / ".hidden.py").write_text("x", encoding="utf-8")
    (tmp_path / "visible.py").write_text("x", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 1


def test_hidden_files_included_when_enabled(tmp_path, config):
    config.include_hidden = True
    (tmp_path / ".hidden.py").write_text("x", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 1


def test_special_filenames_without_extension_included(tmp_path, config):
    (tmp_path / "Dockerfile").write_text("FROM python", encoding="utf-8")
    (tmp_path / "Makefile").write_text("all:", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 2


def test_gitignore_is_hidden_but_special_so_included(tmp_path, config):
    (tmp_path / ".gitignore").write_text("*.pyc", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 1


def test_excluded_lockfiles_are_skipped_but_recorded(tmp_path, config):
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 0
    assert any("lockfile" in s.reason for s in result.skipped)


def test_output_file_self_exclusion(tmp_path, config):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    out = tmp_path / "tmp_project_context_utf8.txt"
    out.write_text("previous dump contents", encoding="utf-8")
    result = scan_directory(tmp_path, config, output_paths={out})
    assert result.source_count == 1  # only a.py, not the output file
    assert _names(all_source_paths(result), tmp_path) == ["a.py"]


def test_output_glob_pattern_excludes_any_prior_dump(tmp_path, config):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "myproj_context_utf8.txt").write_text("old dump", encoding="utf-8")
    result = scan_directory(tmp_path, config)
    assert result.source_count == 1


def test_empty_directory_yields_zero_counts(tmp_path, config):
    result = scan_directory(tmp_path, config)
    assert result.source_count == 0
    assert result.pdf_count == 0
    assert result.dirs == []


def test_max_depth_guard(tmp_path, config):
    config.max_depth = 2
    d = tmp_path
    for i in range(5):
        d = d / f"level{i}"
        d.mkdir()
    (d / "deep.py").write_text("x", encoding="utf-8")

    result = scan_directory(tmp_path, config)
    assert result.source_count == 0
    assert any("max directory depth" in s.reason for s in result.skipped)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlinks/permissions differ on Windows")
def test_symlink_cycle_does_not_hang(tmp_path, config):
    config.follow_symlinks = True
    real = tmp_path / "real"
    real.mkdir()
    (real / "file.py").write_text("x", encoding="utf-8")
    loop_link = real / "loop"
    os.symlink(tmp_path, loop_link, target_is_directory=True)  # points back up to root

    result = scan_directory(tmp_path, config)
    # Must terminate (no infinite loop) and still find the real file once.
    assert result.source_count == 1
    assert any("cycle" in s.reason for s in result.skipped)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlinks/permissions differ on Windows")
def test_symlinked_dir_not_followed_by_default(tmp_path, config):
    assert config.follow_symlinks is False
    real = tmp_path / "real"
    real.mkdir()
    (real / "file.py").write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    os.symlink(real, link, target_is_directory=True)

    result = scan_directory(tmp_path, config)
    assert result.source_count == 1  # only via 'real', not double-counted via 'link'
    assert _names(all_source_paths(result), tmp_path) == ["real/file.py"]


@pytest.mark.skipif(sys.platform.startswith("win") or os.geteuid() == 0, reason="permission tests need a non-root POSIX user")
def test_permission_denied_directory_is_skipped_not_fatal(tmp_path, config):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "secret.py").write_text("x", encoding="utf-8")
    (tmp_path / "visible.py").write_text("x", encoding="utf-8")
    blocked.chmod(0o000)
    try:
        result = scan_directory(tmp_path, config)
        assert result.source_count == 1
        assert any("permission" in s.reason for s in result.skipped)
    finally:
        blocked.chmod(0o755)


def test_broken_symlink_is_skipped_not_fatal(tmp_path, config):
    if sys.platform.startswith("win"):
        pytest.skip("symlinks differ on Windows")
    target = tmp_path / "gone.py"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "broken_link.py"
    os.symlink(target, link)
    target.unlink()  # now the symlink is broken

    result = scan_directory(tmp_path, config)
    assert result.source_count == 0
    assert any("broken symlink" in s.reason for s in result.skipped)
