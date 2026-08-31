from app.output_writer import ChunkedDumpWriter, estimate_tokens, find_existing_outputs


def test_estimate_tokens_heuristic():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(4) == 1
    assert estimate_tokens(4000) == 1000


def test_no_chunking_produces_single_file(tmp_path):
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=None)
    w.write("a" * 500)
    w.checkpoint()
    w.write("b" * 500)
    w.checkpoint()
    paths = w.finalize(overwrite=False)
    assert len(paths) == 1
    assert paths[0] == tmp_path / "proj_context_utf8.txt"
    assert paths[0].read_text() == "a" * 500 + "b" * 500
    assert w.char_count == 1000


def test_chunking_rotates_at_checkpoint(tmp_path):
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=100)
    for i in range(5):
        w.write("x" * 40)
        w.checkpoint()
    paths = w.finalize(overwrite=False)
    assert len(paths) > 1
    for i, p in enumerate(paths, start=1):
        assert p.name == f"proj_context_utf8_part{i}_of_{len(paths)}.txt"
        assert p.exists()
    # No content lost.
    total_chars = sum(len(p.read_text()) for p in paths)
    assert total_chars >= 200  # original content plus small continuation headers


def test_chunking_never_splits_mid_write_only_at_checkpoint(tmp_path):
    # A single write() larger than the limit should NOT be split internally —
    # only checkpoint() (called between files) can trigger rotation.
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=10)
    w.write("y" * 500)  # exceeds max_chunk_chars in one shot, no checkpoint yet
    assert w._chunk_index == 1  # no rotation happened mid-write
    w.checkpoint()  # now it should rotate for the *next* write
    w.write("z" * 5)
    paths = w.finalize(overwrite=False)
    assert len(paths) == 2
    assert paths[0].read_text() == "y" * 500
    assert "z" * 5 in paths[1].read_text()


def test_no_tmp_files_left_after_finalize(tmp_path):
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=50)
    for i in range(4):
        w.write("q" * 30)
        w.checkpoint()
    w.finalize(overwrite=False)
    leftover_tmp = list(tmp_path.glob("*.tmp"))
    assert leftover_tmp == []


def test_cleanup_removes_all_parts(tmp_path):
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=10)
    w.write("a" * 20)
    w.checkpoint()
    w.write("b" * 20)
    w.checkpoint()
    assert len(list(tmp_path.glob("*.tmp"))) >= 2
    w.cleanup()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob("*.txt")) == []


def test_finalize_conflict_without_overwrite(tmp_path):
    (tmp_path / "proj_context_utf8.txt").write_text("old content", encoding="utf-8")
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=None)
    w.write("new content")
    try:
        w.finalize(overwrite=False)
        assert False, "should have raised FileExistsError"
    except FileExistsError as e:
        assert "already exist" in str(e)
    # Own tmp files should be cleaned up, and the old file left untouched.
    assert list(tmp_path.glob("*.tmp")) == []
    assert (tmp_path / "proj_context_utf8.txt").read_text() == "old content"


def test_finalize_overwrite_replaces_existing(tmp_path):
    (tmp_path / "proj_context_utf8.txt").write_text("old content", encoding="utf-8")
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=None)
    w.write("new content")
    paths = w.finalize(overwrite=True)
    assert paths[0].read_text() == "new content"


def test_stale_chunk_files_from_previous_larger_run_are_cleaned_up(tmp_path):
    # Simulate leftovers from an earlier run that produced 3 parts.
    (tmp_path / "proj_context_utf8_part1_of_3.txt").write_text("old1", encoding="utf-8")
    (tmp_path / "proj_context_utf8_part2_of_3.txt").write_text("old2", encoding="utf-8")
    (tmp_path / "proj_context_utf8_part3_of_3.txt").write_text("old3", encoding="utf-8")

    # This run only produces 1 part.
    w = ChunkedDumpWriter(tmp_path, "proj_context_utf8", ".txt", max_chunk_chars=None)
    w.write("fresh content")
    paths = w.finalize(overwrite=True)

    assert len(paths) == 1
    assert paths[0].read_text() == "fresh content"
    # The stale 2nd/3rd parts from the old 3-part run must be gone, or a
    # future scan would pick up orphaned, outdated content.
    assert not (tmp_path / "proj_context_utf8_part2_of_3.txt").exists()
    assert not (tmp_path / "proj_context_utf8_part3_of_3.txt").exists()


def test_find_existing_outputs_detects_both_shapes(tmp_path):
    assert find_existing_outputs(tmp_path, "proj", ".txt") == []
    (tmp_path / "proj.txt").write_text("x", encoding="utf-8")
    assert find_existing_outputs(tmp_path, "proj", ".txt") == [tmp_path / "proj.txt"]
    (tmp_path / "proj.txt").unlink()
    (tmp_path / "proj_part1_of_2.txt").write_text("x", encoding="utf-8")
    (tmp_path / "proj_part2_of_2.txt").write_text("x", encoding="utf-8")
    found = find_existing_outputs(tmp_path, "proj", ".txt")
    assert len(found) == 2


def test_find_existing_outputs_escapes_glob_special_chars(tmp_path):
    # base_name containing glob-special characters must not be treated as a
    # wildcard pattern (e.g. "my[proj]" should not match unrelated files).
    (tmp_path / "myXprojY.txt").write_text("unrelated", encoding="utf-8")
    found = find_existing_outputs(tmp_path, "my[proj]", ".txt")
    assert found == []
