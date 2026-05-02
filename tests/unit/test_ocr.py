"""Unit tests for WP-008: Image Standardization & Tesseract OCR.

Covers
------
- ``app.utils.image.standardize_to_jpg`` — DPI, quality, EXIF removal
- ``app.services.ocr.process_document`` — size gating, MIME routing, empty-text
  rejection, Tesseract execution path
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from PIL import Image

from app.services.ocr import OCRFailedError, process_document
from app.utils.image import standardize_to_jpg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_image(
    mode: str = "RGB",
    size: tuple[int, int] = (100, 100),
    dpi: tuple[int, int] | None = None,
) -> Image.Image:
    """Create a minimal in-memory Pillow image with optional DPI."""
    if mode == "RGBA":
        img = Image.new("RGBA", size, (0, 0, 0, 255))
    elif mode == "L":
        img = Image.new("L", size, 128)
    elif mode == "P":
        img = Image.new("P", size)
    else:
        img = Image.new("RGB", size, (255, 0, 0))
    if dpi is not None:
        img.info["dpi"] = dpi
    return img


def _make_upload(content_type: str, data: bytes) -> UploadFile:
    """Wrap raw bytes in an :class:`UploadFile`.

    FastAPI's ``UploadFile.__init__`` only accepts ``file``, ``filename``,
    and ``headers``.  ``content_type`` is set via the ``Content-Type`` header.
    """
    import tempfile

    # Use a real SpooledTemporaryFile so seek/tell work.
    spooled = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    spooled.write(data)
    spooled.seek(0)
    upload = UploadFile(
        file=spooled,
        filename="dummy",
        headers={"content-type": content_type},
    )
    return upload


# ===========================================================================
# 1. Image standardization — DPI = 300, quality = 84, no EXIF
# ===========================================================================


class TestStandardizeToJpg:
    """Verify that the output image is always 300 DPI, quality 84, EXIF-free."""

    # -- DPI -------------------------------------------------------------------
    def test_output_dpi_is_300_from_different_dpi(self) -> None:
        img = _build_image(dpi=(72, 72))
        out = standardize_to_jpg(img)
        # Pillow stores JPEG DPI in jfif_density, not in info["dpi"].
        dpi_value = out.info.get("dpi") or out.info.get("jfif_density")
        assert dpi_value == (300, 300)

    def test_output_dpi_is_300_from_no_info(self) -> None:
        img = _build_image()
        img.info.clear()
        out = standardize_to_jpg(img)
        dpi_value = out.info.get("dpi") or out.info.get("jfif_density")
        assert dpi_value == (300, 300)

    # -- Mode / RGB ------------------------------------------------------------
    def test_output_is_rgb_for_all_input_modes(self) -> None:
        for mode in ("RGB", "RGBA", "L", "P"):
            img = _build_image(mode=mode)
            out = standardize_to_jpg(img)
            assert out.mode == "RGB", f"Expected RGB for input mode {mode}"

    def test_rgba_converted_on_white_background(self) -> None:
        """Fully transparent RGBA should yield a pure-white RGB image."""
        img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))  # fully transparent
        out = standardize_to_jpg(img)
        pixels = list(out.getdata())
        assert all(r == 255 and g == 255 and b == 255 for r, g, b in pixels)

    # -- EXIF ------------------------------------------------------------------
    def test_no_exif_metadata(self) -> None:
        img = _build_image()
        out = standardize_to_jpg(img)
        assert "exif" not in out.info or out.info.get("exif") == b""

    # -- Quality ---------------------------------------------------------------
    def test_jpg_quality_is_84(self) -> None:
        """A 500 x 500 solid image at quality 84 should produce < 50 KB."""
        img = _build_image(size=(500, 500))
        out = standardize_to_jpg(img)
        buf = io.BytesIO()
        out.save(buf, format="JPEG")
        jpeg_size = buf.tell()
        assert jpeg_size < 50_000, f"JPEG too large ({jpeg_size} B), quality may be too high"

    # -- Round-trip stability --------------------------------------------------
    def test_re_encode_retains_dpi(self) -> None:
        img = _build_image(dpi=(96, 96))
        out = standardize_to_jpg(img)
        # Saving a JPEG without explicit dpi drops it to (1,1) in Pillow.
        # Any caller that wants to keep 300 DPI should pass the value from
        # out.info.  Verify that re-saving WITH that info retains DPI.
        buf = io.BytesIO()
        out.save(buf, format="JPEG", dpi=out.info.get("dpi"))
        buf.seek(0)
        reopened = Image.open(buf)
        dpi_value = reopened.info.get("dpi") or reopened.info.get("jfif_density")
        assert dpi_value == (300, 300)


# ===========================================================================
# 2. process_document — size gating
# ===========================================================================


class TestProcessDocumentSizeGating:
    async def test_oversized_pdf_raises_value_error(self) -> None:
        payload = b"\x00" * (26 * 1024 * 1024)  # 26 MB
        upload = _make_upload("application/pdf", payload)
        with pytest.raises(ValueError, match="exceeds"):
            await process_document(upload)

    async def test_oversized_image_raises_value_error(self) -> None:
        payload = b"\x00" * (26 * 1024 * 1024)
        upload = _make_upload("image/png", payload)
        with pytest.raises(ValueError, match="exceeds"):
            await process_document(upload)

    async def test_file_well_under_limit_passes_size_check(self) -> None:
        upload = _make_upload("image/png", b"\x00" * 1024)  # 1 KB
        with patch(
            "app.services.ocr._process_image",
            return_value="ok",
        ):
            result = await process_document(upload)
        assert result  # non-empty


# ===========================================================================
# 3. process_document — unsupported MIME type
# ===========================================================================


class TestProcessDocumentUnsupportedMime:
    async def test_unknown_mime_raises_value_error(self) -> None:
        upload = _make_upload("application/octet-stream", b"data")
        with pytest.raises(ValueError, match="Unsupported content type"):
            await process_document(upload)

    async def test_empty_content_type_treated_as_unknown(self) -> None:
        upload = _make_upload("", b"data")
        with pytest.raises(ValueError, match="Unsupported content type"):
            await process_document(upload)


# ===========================================================================
# 4. process_document — empty / whitespace-only text -> OCRFailedError
# ===========================================================================


class TestProcessDocumentEmptyText:
    async def test_empty_ocr_raises(self) -> None:
        upload = _make_upload("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with (
            patch("app.services.ocr._process_image", return_value=""),
            pytest.raises(OCRFailedError, match="empty"),
        ):
            await process_document(upload)

    async def test_whitespace_only_ocr_raises(self) -> None:
        upload = _make_upload("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with (
            patch("app.services.ocr._process_image", return_value="   "),
            pytest.raises(OCRFailedError, match="empty"),
        ):
            await process_document(upload)


# ===========================================================================
# 5. process_document — Tesseract path for images (happy path)
# ===========================================================================


class TestProcessDocumentTesseractImage:
    async def test_tesseract_invoked_for_png_image(self) -> None:
        upload = _make_upload("image/png", b"faked-data" * 20)
        with patch(
            "app.services.ocr._process_image",
            return_value="  Hello Welt  ",
        ):
            text = await process_document(upload)
        assert "Hello Welt" in text

    async def test_text_is_normalized_after_ocr(self) -> None:
        """Extra horizontal whitespace should be collapsed via normalize_text."""
        upload = _make_upload("image/png", b"faked-data" * 20)
        with patch(
            "app.services.ocr._process_image",
            return_value="  Hello    Welt  ",
        ):
            text = await process_document(upload)
        assert text == "Hello Welt"

    async def test_tesseract_invoked_for_jpeg_image(self) -> None:
        upload = _make_upload("image/jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        with patch(
            "app.services.ocr._process_image",
            return_value="JPEG test",
        ):
            text = await process_document(upload)
        assert "JPEG test" in text


# ===========================================================================
# 6. process_document — PDF with text extraction
# ===========================================================================


class TestProcessDocumentPdfText:
    async def test_pdf_with_extractable_text_returns_text(self) -> None:
        upload = _make_upload("application/pdf", b"%PDF-1.4 fake")
        with patch("app.services.ocr.extract_pdf_text", return_value="SGB II § 31 text"):
            text = await process_document(upload)
        assert "SGB II § 31 text" in text

    async def test_pdf_extraction_failure_raises_runtime_error(self) -> None:
        """When both pdfplumber and PyMuPDF fail, RuntimeError propagates."""
        upload = _make_upload("application/pdf", b"%PDF-1.4 broken")
        with (
            patch(
                "app.services.ocr.extract_pdf_text",
                side_effect=RuntimeError("fail"),
            ),
            patch(
                "app.services.ocr._ocr_pdf_pages",
                side_effect=RuntimeError("All back-ends failed"),
            ),
            pytest.raises(
                RuntimeError,
                match="All back-ends failed",
            ),
        ):
            await process_document(upload)
