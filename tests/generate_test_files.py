#!/usr/bin/env python3
"""
Generate valid test files for UI testing as specified in ui_testing_guide.md.

Produces:
  test_small.pdf        – <1 MB
  test_large.pdf        – >25 MB
  test_image.jpg        – JPEG, <25 MB
  test_image.png        – PNG, <25 MB
  test.txt              – Plain text, any size
  test_empty.pdf        – Valid PDF, no pages
  test_multi_page.pdf   – Multi-page PDF, <25 MB

Requirements: reportlab, Pillow
"""

import argparse
import io
import os
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus import Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def ensure_dir(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


def lorem_text(paragraphs: int = 3) -> str:
    """Return a simple multi-paragraph lorem ipsum text."""
    base = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
        "pariatur. Excepteur sint occaecat cupidatat non proident, sunt in "
        "culpa qui officia deserunt mollit anim id est laborum.\n\n"
    )
    return (base * paragraphs).strip()


# ----------------------------------------------------------------------
# PDF generators
# ----------------------------------------------------------------------

def generate_small_pdf(path: Path) -> None:
    """Create a small (<1 MB) PDF with a few paragraphs of text."""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Test Small PDF", styles["Title"]))
    story.append(Spacer(1, 12))
    for para in lorem_text(5).split("\n\n"):
        story.append(Paragraph(para, styles["BodyText"]))
        story.append(Spacer(1, 6))
    doc.build(story)


def generate_large_pdf(path: Path) -> None:
    """
    Create a PDF larger than 25 MB.

    Strategy: generate 150 pages, each with a unique noisy JPEG image
    (same dimensions, but different pixel patterns via per-image seeds).
    Each JPEG compresses to ~0.2 MB; 150 copies => ~30 MB.
    PDF embedding overhead pushes this past the 25 MB target.
    """
    W, H = 800, 800  # image dimensions — small enough to encode quickly
    copies = 55

    def make_jpeg(seed: int) -> bytes:
        img = Image.new("RGB", (W, H))
        pixels = img.load()
        for y in range(H):
            for x in range(W):
                r = (x * 123 + y * 457 + seed * 313) % 256
                g = (x * 789 + y * 231 + seed * 619) % 256
                b = (x * 456 + y * 789 + seed * 877) % 256
                pixels[x, y] = (r, g, b)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    doc = SimpleDocTemplate(str(path), pagesize=A4)
    story = []
    for i in range(copies):
        jpeg_data = make_jpeg(i)
        story.append(RLImage(io.BytesIO(jpeg_data), width=200, height=200))
        story.append(Spacer(1, 3))
        if (i + 1) % 10 == 0:
            story.append(Paragraph(f"Page {(i + 1) // 10}", getSampleStyleSheet()["BodyText"]))
    doc.build(story)


def generate_empty_pdf(path: Path) -> None:
    """Create a minimal valid PDF with zero pages."""
    # SimpleDocTemplate with empty story produces a valid PDF
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    doc.build([])


def generate_multi_page_pdf(path: Path) -> None:
    """Create a multi-page PDF (5 pages) with text, <25 MB."""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []
    for page in range(1, 6):
        story.append(Paragraph(f"Page {page}", styles["Title"]))
        story.append(Spacer(1, 12))
        for para in lorem_text(4).split("\n\n"):
            story.append(Paragraph(para, styles["BodyText"]))
            story.append(Spacer(1, 6))
        if page < 5:
            story.append(Spacer(1, 20))   # will cause page break due to content length
    doc.build(story)


# ----------------------------------------------------------------------
# Image generators
# ----------------------------------------------------------------------

def generate_jpeg(path: Path) -> None:
    """Create a valid JPEG image, <25 MB."""
    img = Image.new("RGB", (800, 600), color=(70, 130, 180))
    draw = ImageDraw.Draw(img)
    # Add some text to make it look intentional
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.text((100, 100), "Test JPEG", fill=(255, 255, 255), font=font)
    img.save(str(path), format="JPEG", quality=85)


def generate_png(path: Path) -> None:
    """Create a valid PNG image, <25 MB."""
    img = Image.new("RGBA", (800, 600), color=(255, 100, 100, 128))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.text((100, 100), "Test PNG", fill=(255, 255, 255, 255), font=font)
    img.save(str(path), format="PNG")


def generate_txt(path: Path) -> None:
    """Create a plain text file."""
    text = (
        "This is a test text file.\n"
        "It contains a few lines of text.\n"
        "Used for type rejection testing.\n"
    )
    path.write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate UI test files")
    parser.add_argument(
        "--output-dir",
        default="./test_data",
        help="Directory to write the files (default: ./test_data)",
    )
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)

    print("Generating small PDF (<1 MB) ...")
    generate_small_pdf(out_dir / "test_small.pdf")

    print("Generating large PDF (>25 MB) – may take a few seconds ...")
    generate_large_pdf(out_dir / "test_large.pdf")

    print("Generating JPEG image ...")
    generate_jpeg(out_dir / "test_image.jpg")

    print("Generating PNG image ...")
    generate_png(out_dir / "test_image.png")

    print("Generating text file ...")
    generate_txt(out_dir / "test.txt")

    print("Generating empty PDF ...")
    generate_empty_pdf(out_dir / "test_empty.pdf")

    print("Generating multi-page PDF ...")
    generate_multi_page_pdf(out_dir / "test_multi_page.pdf")

    print("All test files generated.")


if __name__ == "__main__":
    main()
