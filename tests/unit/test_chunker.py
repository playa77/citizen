"""Unit tests for the corpus scraper and hierarchical chunker."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from app.services import corpus as corpus_mod
from app.utils.text import normalize_text

# ===================================================================
# normalize_text (app/utils/text.py)
# ===================================================================


class TestNormalizeText:
    def test_strips_extra_whitespace(self) -> None:
        assert normalize_text("  hello    world  ") == "hello world"

    def test_removes_blank_lines(self) -> None:
        raw = "para one\n\n\n\npara two"
        assert normalize_text(raw) == "para one\npara two"

    def test_removes_zero_width_chars(self) -> None:
        raw = "hello\u200bworld\ufefftest"
        assert "\u200b" not in normalize_text(raw)
        assert "\ufeff" not in normalize_text(raw)

    def test_nfc_normalisation(self) -> None:
        # U+00E9 (é precomposed) vs U+0065 U+0301 (e + combining acute)
        decomposed = "re\u0301sume\u0301"
        result = normalize_text(decomposed)
        assert result == "résumé"

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_text("") == ""

    def test_only_whitespace_returns_empty(self) -> None:
        assert normalize_text("   \n\t  ") == ""


# ===================================================================
# _clean_ocr_artefacts
# ===================================================================


class TestCleanOcrArtefacts:
    def test_replaces_nbsp(self) -> None:
        assert corpus_mod._clean_ocr_artefacts("10\u00a0MB") == "10 MB"

    def test_removes_zero_width(self) -> None:
        assert corpus_mod._clean_ocr_artefacts("text\u200b") == "text"

    def test_collapses_whitespace(self) -> None:
        assert corpus_mod._clean_ocr_artefacts("a    b\n\nc") == "a b c"


# ===================================================================
# _split_into_sentences
# ===================================================================


class TestSplitIntoSentences:
    def test_single_sentence(self) -> None:
        result = corpus_mod._split_into_sentences("This is one sentence.")
        assert result == ["This is one sentence."]

    def test_two_sentences(self) -> None:
        text = "Erste Aussage. Zweite Aussage."
        result = corpus_mod._split_into_sentences(text)
        assert result == ["Erste Aussage.", "Zweite Aussage."]

    def test_exclamation_and_question(self) -> None:
        text = "Achtung! Ist das richtig? Ja."
        result = corpus_mod._split_into_sentences(text)
        assert result == ["Achtung!", "Ist das richtig?", "Ja."]

    def test_german_umlauts(self) -> None:
        text = "Regel eins. Überarbeitung folgt."
        result = corpus_mod._split_into_sentences(text)
        assert result == ["Regel eins.", "Überarbeitung folgt."]

    def test_empty_string(self) -> None:
        assert corpus_mod._split_into_sentences("") == []


# ===================================================================
# _compute_version_hash
# ===================================================================


class TestVersionHash:
    def test_deterministic(self) -> None:
        h1 = corpus_mod._compute_version_hash("hello")
        h2 = corpus_mod._compute_version_hash("hello")
        assert h1 == h2

    def test_different_inputs_produce_different_hashes(self) -> None:
        assert corpus_mod._compute_version_hash("a") != corpus_mod._compute_version_hash("b")

    def test_is_64_char_hex(self) -> None:
        h = corpus_mod._compute_version_hash("any text")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ===================================================================
# _build_hierarchy / _make_chunk (pure helpers)
# ===================================================================


class TestBuildHierarchy:
    def test_full_path(self) -> None:
        result = corpus_mod._build_hierarchy("SGB II", "31", "1", "2")
        assert result == ["SGB II", "§ 31", "Abs. 1", "Satz 2"]

    def test_empty_absatz(self) -> None:
        result = corpus_mod._build_hierarchy("SGB II", "5", "", "1")
        assert result == ["SGB II", "§ 5", "Satz 1"]


class TestMakeChunk:
    def test_contains_required_keys(self) -> None:
        chunk = corpus_mod._make_chunk(
            source_type="sgb2",
            title="SGB II",
            hierarchy=["SGB II", "§ 31", "Abs. 1", "Satz 2"],
            text="Der Anspruch erlischt.",
            unit_type="satz",
            effective_date="2025-01-01",
            source_url="https://example.org",
        )
        required = {
            "id",
            "source_type",
            "title",
            "unit_type",
            "hierarchy_path",
            "text_content",
            "effective_date",
            "source_url",
            "version_hash",
            "chunk_id",
        }
        assert required <= chunk.keys()
        assert chunk["unit_type"] == "satz"
        assert " > " in chunk["hierarchy_path"]


# ===================================================================
# build_sentence_level_chunks
# ===================================================================


class TestBuildSentenceLevelChunks:
    def test_single_sentence_para(self) -> None:
        paras = [{"text": "Ein einzelner Satz.", "paragraph": "1", "absatz": "2"}]
        chunks = corpus_mod.build_sentence_level_chunks(paras, source_type="sgb2", title="SGB II")
        assert len(chunks) == 1
        assert chunks[0]["text_content"] == "Ein einzelner Satz."

    def test_multi_sentence_splits(self) -> None:
        paras = [{"text": "Erste Aussage. Zweite Aussage.", "paragraph": "5", "absatz": ""}]
        chunks = corpus_mod.build_sentence_level_chunks(paras, source_type="sgb2", title="SGB II")
        assert len(chunks) == 2

    def test_empty_para_skipped(self) -> None:
        paras = [{"text": "", "paragraph": "1", "absatz": ""}]
        chunks = corpus_mod.build_sentence_level_chunks(paras, source_type="sgb2", title="SGB II")
        assert chunks == []

    def test_hierarchy_path_contains_satz(self) -> None:
        paras = [{"text": "Ein Satz.", "paragraph": "31", "absatz": "1"}]
        chunks = corpus_mod.build_sentence_level_chunks(paras, source_type="sgb2", title="SGB II")
        assert chunks[0]["hierarchy_path"] == "SGB II > § 31 > Abs. 1 > Satz 1"

    def test_hierarchical_split_sgb2_paragraph_31(self) -> None:
        """Verifies the WP-005 acceptance criterion:
        SGB II > § 31 > Abs. 1 > Satz 2 path is produced.
        """
        paras = [
            {
                "text": "Erste Grundlage. Zweite Begründung.",
                "paragraph": "31",
                "absatz": "1",
                "effective_date": "2025-06-01",
                "source_url": "https://www.gesetze-im-internet.de/sgb_2/",
            }
        ]
        chunks = corpus_mod.build_sentence_level_chunks(paras, source_type="sgb2", title="SGB II")
        assert len(chunks) == 2
        paths = [c["hierarchy_path"] for c in chunks]
        assert "SGB II > § 31 > Abs. 1 > Satz 1" in paths
        assert "SGB II > § 31 > Abs. 1 > Satz 2" in paths


# ===================================================================
# _infer_law_name
# ===================================================================


class TestInferLawName:
    def test_default_fallback(self) -> None:
        mock_tag = MagicMock(spec=[])
        mock_tag.find_parent = MagicMock(return_value=None)
        result = corpus_mod._infer_law_name(mock_tag, "sgb2")
        assert result == "SGB II"

    def test_uses_title_from_html(self) -> None:
        html = """<html><head><title>SGB II Gesetz</title></head>
        <body><p>Test</p></body></html>"""
        soup = BeautifulSoup(html, "lxml")
        p_tag = soup.find("p")
        assert isinstance(p_tag, BeautifulSoup) or p_tag is not None
        result = corpus_mod._infer_law_name(p_tag, "sgb2")
        assert result == "SGB II Gesetz"


# ===================================================================
# _infer_effective_date
# ===================================================================


class TestInferEffectiveDate:
    def test_returns_today_when_no_meta(self) -> None:
        html = "<html><body><p>Text</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        result = corpus_mod._infer_effective_date(soup)
        assert result == date.today()

    def test_parses_meta_date(self) -> None:
        html = """<html>
        <head><meta name="date" content="2025-03-15T00:00:00+01:00"/></head>
        <body><p>Text</p></body></html>"""
        soup = BeautifulSoup(html, "lxml")
        result = corpus_mod._infer_effective_date(soup)
        assert result == date(2025, 3, 15)


# ===================================================================
# scrape_and_chunk — integration with mocked HTTP
# ===================================================================


class TestScrapeAndChunk:
    @pytest.mark.asyncio
    async def test_invalid_source_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown source_type"):
            await corpus_mod.scrape_and_chunk("invalid_type")

    @pytest.mark.asyncio
    async def test_successful_scrape_returns_chunks(self) -> None:
        """Mock a successful HTTP response and verify chunk production."""
        mock_html = """
        <html>
        <head><title>SGB II</title></head>
        <body>
            <content>
                <p>§ 31 Abs. 1 Satz 1 Der Anspruch besteht.</p>
                <p>§ 31 Abs. 1 Satz 2 Er wird gewährt.</p>
                <p>Allgemeiner Text ohne Struktur.</p>
            </content>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.text = mock_html
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            chunks = await corpus_mod.scrape_and_chunk("sgb2")

        assert isinstance(chunks, list)
        assert len(chunks) >= 2

        # Verify required output keys
        for chunk in chunks:
            assert "unit_type" in chunk
            assert "hierarchy_path" in chunk
            assert "text_content" in chunk

    @pytest.mark.asyncio
    async def test_empty_body_returns_no_chunks(self) -> None:
        """If the page has no paragraph content, return empty list."""
        mock_response = MagicMock()
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            chunks = await corpus_mod.scrape_and_chunk("sgb2")

        assert chunks == []

    @pytest.mark.asyncio
    async def test_http_error_propagates(self) -> None:
        """A non-2xx response should raise via httpx.Response.raise_for_status."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await corpus_mod.scrape_and_chunk("sgb2")

    @pytest.mark.asyncio
    async def test_scraper_with_injected_client(self) -> None:
        """Verify scrape_and_chunk accepts an externally provided client."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>§ 5 Test.</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        chunks = await corpus_mod.scrape_and_chunk("sgb2", client=mock_client)
        assert isinstance(chunks, list)


class TestScrapeAllSourceTypes:
    """Ensure all four source types are accepted without error."""

    @pytest.mark.asyncio
    async def test_all_source_types_accepted(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>§ 1 Inhalt.</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        for st in ("sgb2", "sgbx", "weisung", "bsg"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                chunks = await corpus_mod.scrape_and_chunk(st)
            assert isinstance(chunks, list)


class TestEffectiveDateFallbacks:
    """Cover the fundstelle meta-tag fallback path."""

    def test_parses_fundstelle_date(self) -> None:
        html = """<html>
        <head><meta name="fundstelle" content="BGBl I 2025/03-15"/></head>
        <body><p>Text</p></body></html>"""
        soup = BeautifulSoup(html, "lxml")
        result = corpus_mod._infer_effective_date(soup)
        assert result == date(2025, 3, 15)

    def test_invalid_meta_date_falls_through(self) -> None:
        html = """<html>
        <head><meta name="date" content="not-a-date"/></head>
        <body><p>Text</p></body></html>"""
        soup = BeautifulSoup(html, "lxml")
        result = corpus_mod._infer_effective_date(soup)
        assert result == date.today()


class TestNormalizeEdgeCases:
    """Edge cases for normalize_text."""

    def test_collapse_excessive_newlines(self) -> None:
        """Blank lines are removed; remaining newlines collapse to single."""
        raw = "line one\n\n\n\n\nline two"
        # All blank lines stripped, leaving one remaining newline
        assert normalize_text(raw) == "line one\nline two"

    def test_strip_leading_trailing_ws(self) -> None:
        assert normalize_text("  \n\t  hello  \n\t  ") == "hello"


class TestParseParagraphElement:
    """Test _parse_paragraph_element for structural detection."""

    def test_detects_absatz_and_satz(self) -> None:
        html = "<p>§ 31 Abs. 1 Satz 2 Der Inhalt.</p>"
        soup = BeautifulSoup(html, "lxml")
        p_tag = soup.find("p")
        assert isinstance(p_tag, Tag)
        hierarchy, text = corpus_mod._parse_paragraph_element(p_tag, "sgb2")
        assert "§ 31" in hierarchy
        assert "Abs. 1" in hierarchy
        assert "Satz 2" in hierarchy

    def test_unstructured_text_falls_back_to_allgemein(self) -> None:
        html = "<p>Einleitung ohne Paragraph.</p>"
        soup = BeautifulSoup(html, "lxml")
        p_tag = soup.find("p")
        assert isinstance(p_tag, Tag)
        hierarchy, text = corpus_mod._parse_paragraph_element(p_tag, "sgb2")
        assert hierarchy == ["SGB II", "Allgemein"]
