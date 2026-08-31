import io

from app.config import Config
from app.detector import scan_directory
from app.pdf_dumper import _extract_pdf_text, write_pdf_dump

from conftest import make_pdf


def test_extract_real_pdf_text(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    make_pdf(pdf_path, text="Quarterly Report", pages=2)
    text = _extract_pdf_text(pdf_path, max_size=10_000_000)
    assert "Page 1/2" in text
    assert "Page 2/2" in text
    assert "Quarterly Report" in text


def test_extract_corrupt_pdf_reports_error_not_crash(tmp_path):
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"this is not actually a pdf file at all")
    text = _extract_pdf_text(p, max_size=10_000_000)
    assert text.startswith("[ERROR")


def test_extract_empty_pdf_file(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    text = _extract_pdf_text(p, max_size=10_000_000)
    assert "empty" in text


def test_extract_pdf_too_large(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    make_pdf(pdf_path)
    text = _extract_pdf_text(pdf_path, max_size=10)  # absurdly small limit
    assert "too large" in text


def test_write_pdf_dump_end_to_end(tmp_path):
    (tmp_path / "docs").mkdir()
    make_pdf(tmp_path / "docs" / "report.pdf", text="Annual Summary")

    config = Config()
    scan = scan_directory(tmp_path, config)
    skipped = []
    buf = io.StringIO()
    written = write_pdf_dump(buf, tmp_path, scan.dirs, config, skipped, total=scan.pdf_count)

    output = buf.getvalue()
    assert written == 1
    assert "PDF COLLECTION STRUCTURE" in output
    assert "--- FILE: docs/report.pdf ---" in output
    assert "Annual Summary" in output
    assert skipped == []


def test_write_pdf_dump_records_corrupt_file_as_skip(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    config = Config()
    scan = scan_directory(tmp_path, config)
    skipped = []
    buf = io.StringIO()
    write_pdf_dump(buf, tmp_path, scan.dirs, config, skipped, total=scan.pdf_count)
    assert len(skipped) == 1
    assert "ERROR" in skipped[0].reason or "corrupt" in skipped[0].reason
