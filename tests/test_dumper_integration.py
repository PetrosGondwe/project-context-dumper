import threading

import pytest

from app.config import Config
from app.dumper import (
    Mode,
    NoSupportedFilesError,
    NotADirectoryProvided,
    default_output_path,
    run_dump,
)

from conftest import make_pdf


def test_source_only_project(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "util.py").write_text("def f(): pass\n", encoding="utf-8")

    summary = run_dump(tmp_path, Config())
    assert summary.mode_used == "source"
    assert summary.source_file_count == 2
    assert summary.pdf_file_count == 0
    assert summary.output_path.exists()
    content = summary.output_path.read_text(encoding="utf-8")
    assert "SOURCE CODE PROJECT STRUCTURE" in content
    assert "PDF" not in content.split("SKIPPED")[0] or "PDF TEXT EXTRACTION" not in content


def test_pdf_only_project(tmp_path):
    make_pdf(tmp_path / "a.pdf", text="alpha")
    summary = run_dump(tmp_path, Config())
    assert summary.mode_used == "pdf"
    assert summary.pdf_file_count == 1
    content = summary.output_path.read_text(encoding="utf-8")
    assert "PDF TEXT EXTRACTION" in content
    assert "alpha" in content


def test_mixed_project_produces_both_sections(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    make_pdf(tmp_path / "a.pdf", text="alpha-doc")

    summary = run_dump(tmp_path, Config())
    assert summary.mode_used == "mixed"
    content = summary.output_path.read_text(encoding="utf-8")
    assert "SECTION 1: SOURCE CODE" in content
    assert "SECTION 2: PDF DOCUMENTS" in content
    assert "alpha-doc" in content


def test_empty_project_raises(tmp_path):
    with pytest.raises(NoSupportedFilesError):
        run_dump(tmp_path, Config())


def test_forced_source_mode_with_no_source_files_raises(tmp_path):
    make_pdf(tmp_path / "a.pdf")
    with pytest.raises(NoSupportedFilesError):
        run_dump(tmp_path, Config(), mode=Mode.SOURCE)


def test_nonexistent_root_raises(tmp_path):
    with pytest.raises(NotADirectoryProvided):
        run_dump(tmp_path / "does_not_exist", Config())


def test_root_is_a_file_raises(tmp_path):
    f = tmp_path / "not_a_dir.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryProvided):
        run_dump(f, Config())


def test_output_collision_requires_overwrite_flag(tmp_path):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    out = tmp_path / "out.txt"
    out.write_text("existing content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_dump(tmp_path, Config(), output_path=out, overwrite=False)

    # With overwrite=True it should succeed and replace the content.
    summary = run_dump(tmp_path, Config(), output_path=out, overwrite=True)
    assert summary.output_path == out
    assert "main.py" in out.read_text(encoding="utf-8")


def test_no_tmp_file_left_behind_on_success(tmp_path):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    summary = run_dump(tmp_path, Config())
    tmp_file = summary.output_path.with_name(summary.output_path.name + ".tmp")
    assert not tmp_file.exists()


def test_rerun_does_not_ingest_previous_dump(tmp_path):
    (tmp_path / "main.py").write_text("print('v1')\n", encoding="utf-8")
    summary1 = run_dump(tmp_path, Config())
    assert summary1.source_file_count == 1

    # Run again in the same directory (the previous dump file now sits
    # alongside main.py) — it must not be picked up as a source file.
    summary2 = run_dump(tmp_path, Config(), overwrite=True, output_path=summary1.output_path)
    assert summary2.source_file_count == 1


def test_cancellation_cleans_up_and_reports(tmp_path):
    for i in range(10):
        (tmp_path / f"file_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")

    cancel_event = threading.Event()

    def progress_cb(done, total, rel_path, phase):
        if done >= 3:
            cancel_event.set()

    summary = run_dump(tmp_path, Config(), cancel_event=cancel_event, progress_cb=progress_cb)
    assert summary.cancelled is True
    assert summary.output_path is None
    out = default_output_path(tmp_path)
    assert not out.exists()
    assert not out.with_name(out.name + ".tmp").exists()


def test_default_output_path_sanitizes_name(tmp_path):
    project = tmp_path / "My Cool Project!!"
    project.mkdir()
    out = default_output_path(project)
    assert out.name == "my_cool_project_context_utf8.txt"


def test_skipped_section_appears_in_output_when_present(tmp_path):
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    summary = run_dump(tmp_path, Config())
    content = summary.output_path.read_text(encoding="utf-8")
    assert "SKIPPED / WARNINGS" in content
    assert "package-lock.json" in content


def test_summary_reports_char_count_and_token_estimate(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n" * 100, encoding="utf-8")
    summary = run_dump(tmp_path, Config())
    assert summary.char_count > 0
    assert summary.output_path.read_text(encoding="utf-8").__len__() == summary.char_count
    assert summary.estimated_tokens == summary.char_count // 4


def test_cancelled_run_reports_zero_char_count(tmp_path):
    import threading
    for i in range(10):
        (tmp_path / f"f_{i}.py").write_text("x" * 50, encoding="utf-8")
    cancel_event = threading.Event()

    def progress_cb(done, total, rel_path, phase):
        if done >= 2:
            cancel_event.set()

    summary = run_dump(tmp_path, Config(), cancel_event=cancel_event, progress_cb=progress_cb)
    assert summary.cancelled is True
    assert summary.char_count == 0
    assert summary.estimated_tokens == 0
    assert summary.output_paths == []


def test_chunked_output_end_to_end(tmp_path):
    for i in range(6):
        (tmp_path / f"file_{i}.py").write_text("x = 1\n" * 50, encoding="utf-8")

    config = Config()
    config.max_chunk_chars = 200  # deliberately tiny to force multiple parts

    summary = run_dump(tmp_path, config)
    assert len(summary.output_paths) > 1
    assert summary.output_path == summary.output_paths[0]
    total = len(summary.output_paths)
    for i, p in enumerate(summary.output_paths, start=1):
        assert p.exists()
        assert f"_part{i}_of_{total}" in p.name
    # Every source file must appear in exactly one part.
    combined = "".join(p.read_text(encoding="utf-8") for p in summary.output_paths)
    for i in range(6):
        assert f"file_{i}.py" in combined
    assert summary.source_file_count == 6
    # No leftover temp files.
    assert list(tmp_path.glob("*.tmp")) == []


def test_chunked_rerun_does_not_ingest_previous_chunks(tmp_path):
    for i in range(6):
        (tmp_path / f"file_{i}.py").write_text("x = 1\n" * 50, encoding="utf-8")
    config = Config()
    config.max_chunk_chars = 200

    summary1 = run_dump(tmp_path, config)
    assert len(summary1.output_paths) > 1

    summary2 = run_dump(tmp_path, config, overwrite=True)
    assert summary2.source_file_count == 6  # still just the 6 real source files


def test_chunked_output_conflict_requires_overwrite(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n" * 200, encoding="utf-8")
    config = Config()
    config.max_chunk_chars = 50
    run_dump(tmp_path, config)  # first run succeeds, creates part files

    with pytest.raises(FileExistsError):
        run_dump(tmp_path, config, overwrite=False)
