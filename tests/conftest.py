import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.config import Config


@pytest.fixture
def config():
    return Config()


def make_pdf(path: Path, text: str = "Hello PDF world", pages: int = 1):
    """Create a tiny real PDF with extractable text using reportlab."""
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for i in range(pages):
        c.drawString(100, 700, f"{text} - page {i + 1}")
        c.showPage()
    c.save()
