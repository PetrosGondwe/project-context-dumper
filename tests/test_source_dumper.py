import io

from app.config import Config
from app.detector import scan_directory
from app.source_dumper import _looks_binary, read_text_best_effort, write_source_dump


def test_looks_binary_detects_null_bytes():
    assert _looks_binary(b"hello\x00world") is True


def test_looks_binary_false_for_plain_text():
    assert _looks_binary(b"def foo():\n    return 42\n") is False


def test_looks_binary_true_for_png_header():
    assert _looks_binary(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR") is True


def test_read_text_best_effort_clean_utf8(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("print('héllo')", encoding="utf-8")
    content, note = read_text_best_effort(p, max_size=10_000)
    assert content == "print('héllo')"
    assert note is None


def test_read_text_best_effort_empty_file(tmp_path):
    p = tmp_path / "empty.py"
    p.write_bytes(b"")
    content, note = read_text_best_effort(p, max_size=10_000)
    assert content == ""
    assert note is None


def test_read_text_best_effort_too_large(tmp_path):
    p = tmp_path / "big.py"
    p.write_bytes(b"x" * 1000)
    content, note = read_text_best_effort(p, max_size=100)
    assert content is None
    assert "too large" in note


def test_read_text_best_effort_binary_skipped(tmp_path):
    p = tmp_path / "binary.dat"
    p.write_bytes(bytes(range(256)))
    content, note = read_text_best_effort(p, max_size=10_000)
    assert content is None
    assert "binary" in note


def test_read_text_best_effort_latin1_fallback(tmp_path):
    p = tmp_path / "latin1.py"
    # 0xe9 = 'é' in Latin-1 but is invalid as a UTF-8 continuation byte here.
    p.write_bytes(b"# coding: latin-1\nname = 'caf\xe9'\n")
    content, note = read_text_best_effort(p, max_size=10_000)
    assert content is not None
    assert note is not None  # some fallback note should be present
    assert "caf" in content


def test_read_text_best_effort_missing_file(tmp_path):
    content, note = read_text_best_effort(tmp_path / "nope.py", max_size=10_000)
    assert content is None
    assert "cannot" in note.lower() or "stat" in note.lower()


def test_write_source_dump_end_to_end(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Title\n", encoding="utf-8")

    config = Config()
    scan = scan_directory(tmp_path, config)
    skipped = []
    buf = io.StringIO()
    written = write_source_dump(buf, tmp_path, scan.dirs, config, skipped, total=scan.source_count)

    output = buf.getvalue()
    assert written == 2
    assert "SOURCE CODE PROJECT STRUCTURE" in output
    assert "--- FILE: README.md ---" in output
    assert "--- FILE: src/app.py ---" in output
    assert "import os" in output
    assert skipped == []


def test_write_source_dump_records_skips(tmp_path):
    (tmp_path / "huge.py").write_bytes(b"x" * 100)
    (tmp_path / "small.py").write_text("ok = 1\n", encoding="utf-8")

    config = Config()
    config.max_file_size_bytes = 50
    scan = scan_directory(tmp_path, config)
    skipped = []
    buf = io.StringIO()
    write_source_dump(buf, tmp_path, scan.dirs, config, skipped, total=scan.source_count)

    assert len(skipped) == 1
    assert "too large" in skipped[0].reason
    assert "too large" in buf.getvalue()


def test_write_source_dump_progress_callback(tmp_path):
    (tmp_path / "a.py").write_text("1", encoding="utf-8")
    (tmp_path / "b.py").write_text("2", encoding="utf-8")
    config = Config()
    scan = scan_directory(tmp_path, config)
    calls = []
    buf = io.StringIO()
    write_source_dump(
        buf, tmp_path, scan.dirs, config, [],
        progress_cb=lambda i, t, r: calls.append((i, t, r)),
        total=scan.source_count,
    )
    assert len(calls) == 2
    assert calls[0][1] == 2 and calls[1][1] == 2
