"""Unit tests for app/utils/pdf.py — PDF text extraction fallback chain."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.utils.pdf import extract_pdf_text


def _build_minimal_pdf(content: str) -> bytes:
    """Build a tiny text-only PDF in memory using fitz as test data."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    return bytes(doc.tobytes())


# ---------------------------------------------------------------------------
# Happy path: pdfplumber succeeds
# ---------------------------------------------------------------------------


class TestExtractPdfTextHappyPath:
    def test_digital_pdf_returns_text(self) -> None:
        pdf_bytes = _build_minimal_pdf("Hello, Citizen!")
        result = extract_pdf_text(pdf_bytes)
        assert "Hello, Citizen!" in result

    def test_returns_utf8_string(self) -> None:
        pdf_bytes = _build_minimal_pdf("Umlaute: äöü ß")
        result = extract_pdf_text(pdf_bytes)
        assert "äöü" in result

    def test_multi_page_pdf(self) -> None:
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((50, 50), "Page one")
        doc.new_page().insert_text((50, 50), "Page two")
        pdf_bytes = doc.tobytes()

        result = extract_pdf_text(pdf_bytes)
        assert "Page one" in result
        assert "Page two" in result


# ---------------------------------------------------------------------------
# Fallback chain: pdfplumber empty → PyMuPDF
# ---------------------------------------------------------------------------


class TestExtractPdfTextFallback:
    def test_fallback_chain(self) -> None:
        """Mock pdfplumber returning empty text; verify PyMuPDF triggers."""
        pdf_bytes = _build_minimal_pdf("Fallback worked!")

        with patch("app.utils.pdf.pdfplumber") as mock_plumber:
            mock_plumber.open.return_value.__enter__ = MagicMock(return_value=MagicMock(pages=[]))
            mock_plumber.open.return_value.__exit__ = MagicMock(return_value=False)

            result = extract_pdf_text(pdf_bytes)
            assert "Fallback worked!" in result

    def test_fallback_on_pdfplumber_exception(self) -> None:
        """Mock pdfplumber raising; verify PyMuPDF triggers."""
        pdf_bytes = _build_minimal_pdf("After exception!")

        with patch(
            "app.utils.pdf._extract_with_pdfplumber",
            side_effect=RuntimeError("simulated pdfplumber failure"),
        ):
            result = extract_pdf_text(pdf_bytes)
            assert "After exception!" in result


# ---------------------------------------------------------------------------
# Both tiers fail → RuntimeError
# ---------------------------------------------------------------------------


class TestExtractPdfTextBothFail:
    def test_both_extractors_fail(self) -> None:
        pdf_bytes = b"not-a-pdf"

        with (
            patch(
                "app.utils.pdf._extract_with_pdfplumber",
                side_effect=RuntimeError("plumber fail"),
            ),
            patch(
                "app.utils.pdf._extract_with_pymupdf",
                side_effect=Exception("fitz fail"),
            ),
            pytest.raises(RuntimeError, match="All PDF text extraction"),
        ):
            extract_pdf_text(pdf_bytes)

    def test_both_return_empty_raises(self) -> None:
        """pdfplumber returns "" and PyMuPDF returns "   " → RuntimeError."""
        with (
            patch("app.utils.pdf._extract_with_pdfplumber", return_value=""),
            patch("app.utils.pdf._extract_with_pymupdf", return_value="   "),
            pytest.raises(RuntimeError, match="returned empty"),
        ):
            extract_pdf_text(b"dummy")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestExtractPdfTextEdgeCases:
    def test_empty_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="file_bytes must not be empty"):
            extract_pdf_text(b"")

    def test_none_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="file_bytes must not be empty"):
            extract_pdf_text(None)  # type: ignore[arg-type]

    def test_whitespace_only_pdf(self) -> None:
        """A minimal PDF that extracts to whitespace → RuntimeError."""
        pdf_bytes = _build_minimal_pdf("")

        # pdfplumber may return empty; PyMuPDF may also return empty
        # Both tiers returning pure whitespace raises RuntimeError
        with (
            patch(
                "app.utils.pdf._extract_with_pdfplumber",
                return_value="   \n  ",
            ),
            patch(
                "app.utils.pdf._extract_with_pymupdf",
                return_value="\t  \n",
            ),
            pytest.raises(RuntimeError, match="returned empty"),
        ):
            extract_pdf_text(pdf_bytes)

    def test_pdfplumber_returns_none_page_text(self) -> None:
        """page.extract_text() can return None for image-only pages."""
        pdf_bytes = _build_minimal_pdf("Real text")

        with patch("app.utils.pdf.pdfplumber") as mock_plumber:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = None
            mock_pages = MagicMock()
            mock_pages.__iter__ = MagicMock(return_value=iter([mock_page]))
            mock_pdf = MagicMock()
            mock_pdf.pages = mock_pages
            mock_plumber.open.return_value.__enter__ = MagicMock(return_value=mock_pdf)
            mock_plumber.open.return_value.__exit__ = MagicMock(return_value=False)

            # pdfplumber returns empty → fallback to PyMuPDF
            result = extract_pdf_text(pdf_bytes)
            assert "Real text" in result
