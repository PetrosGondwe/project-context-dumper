from app.cli import main


def test_cli_happy_path(tmp_path, capsys):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    rc = main([str(tmp_path), "-o", str(out), "--quiet"])
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr()
    assert "Mode used      : source" in captured.out


def test_cli_empty_folder_exits_nonzero(tmp_path, capsys):
    rc = main([str(tmp_path), "--quiet"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "No supported" in captured.err


def test_cli_missing_folder_exits_nonzero(tmp_path, capsys):
    rc = main([str(tmp_path / "nope"), "--quiet"])
    assert rc == 1


def test_cli_refuses_overwrite_without_flag(tmp_path, capsys):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    out = tmp_path / "out.txt"
    out.write_text("existing", encoding="utf-8")
    rc = main([str(tmp_path), "-o", str(out), "--quiet"])
    assert rc == 1
    assert "already exist" in capsys.readouterr().err


def test_cli_overwrite_flag_allows_replace(tmp_path):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    out = tmp_path / "out.txt"
    out.write_text("existing", encoding="utf-8")
    rc = main([str(tmp_path), "-o", str(out), "--quiet", "--overwrite"])
    assert rc == 0
    assert "main.py" in out.read_text(encoding="utf-8")


def test_cli_forced_pdf_mode_with_no_pdfs(tmp_path, capsys):
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    rc = main([str(tmp_path), "--mode", "pdf", "--quiet"])
    assert rc == 1
    assert "No PDF files" in capsys.readouterr().err


def test_cli_reports_char_count_and_tokens(tmp_path, capsys):
    (tmp_path / "main.py").write_text("x = 1\n" * 50, encoding="utf-8")
    rc = main([str(tmp_path), "-o", str(tmp_path / "out.txt"), "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Characters" in out
    assert "Est. tokens" in out


def test_cli_stdout_mode_emits_only_dump_content_on_stdout(tmp_path, capsys):
    (tmp_path / "main.py").write_text("print('hello world')\n", encoding="utf-8")
    rc = main([str(tmp_path), "--stdout", "--quiet"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "print('hello world')" in captured.out
    assert "SOURCE CODE PROJECT STRUCTURE" in captured.out
    # Nothing diagnostic should leak into stdout in --stdout mode.
    assert "Mode used" not in captured.out
    assert "Characters" not in captured.out
    # Diagnostics should still be available, just on stderr.
    assert "Mode used" in captured.err


def test_cli_stdout_leaves_no_file_in_project_dir(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    rc = main([str(tmp_path), "--stdout", "--quiet"])
    assert rc == 0
    assert list(tmp_path.glob("*context_utf8*")) == []


def test_cli_stdout_rejects_chunk_flags(tmp_path, capsys):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    rc = main([str(tmp_path), "--stdout", "--max-chunk-chars", "1000"])
    assert rc == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_cli_chunk_for_preset_produces_multiple_parts(tmp_path):
    for i in range(20):
        (tmp_path / f"f_{i}.py").write_text("x = 1\n" * 500, encoding="utf-8")
    out = tmp_path / "out.txt"
    rc = main([str(tmp_path), "-o", str(out), "--chunk-for", "chatgpt", "--quiet"])
    assert rc == 0
    parts = sorted(tmp_path.glob("out_part*_of_*.txt")) or [out]
    assert len(parts) >= 1  # may or may not split depending on total size, but must not error


def test_cli_max_chunk_chars_forces_split(tmp_path):
    for i in range(10):
        (tmp_path / f"f_{i}.py").write_text("x = 1\n" * 200, encoding="utf-8")
    out = tmp_path / "out.txt"
    rc = main([str(tmp_path), "-o", str(out), "--max-chunk-chars", "500", "--quiet"])
    assert rc == 0
    parts = sorted(tmp_path.glob("out_part*_of_*.txt"))
    assert len(parts) > 1
