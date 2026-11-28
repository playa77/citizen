"""Corpus scraper, parser, hierarchical chunker, and vector upserter.

Fetches legal texts from ``gesetze-im-internet.de``, parses their hierarchical
structure into ``§ → Absatz → Satz`` units, generates metadata, and returns
normalised :class:`dict` objects ready for embedding and DB insertion.
"""

# Semantic Version: 0.4.0 | 2026-11-17 — WP-113: `bsg` is scraped from case-law
# providers (app/services/case_law.py); gii_source_slugs() for change detection.
# 0.3.0 | 2026-11-16 — `default_corpus_sources()`: the
# ingest default comes from the DEFAULT_MODULE's corpus scope unless
# CORPUS_SOURCES is set (last residual coupling of ARCHITECTURE.md § 8).
# 0.2.0 | 2026-11-16 — WP-93: § range → legal_area chunk tags
# come from module corpus scopes (`chunk_tags`), no hard-coded area table.

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup, Tag
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as upsert_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.router import OpenRouterClient
from app.db.models import ChunkEmbedding, LegalChunk, LegalSource
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP client limits — be a good netizen
# ---------------------------------------------------------------------------
# Never open more than 4 concurrent connections to the same host.
_HTTP_LIMITS = httpx.Limits(max_connections=4, max_keepalive_connections=2)

# Minimum delay between consecutive requests to the same host (seconds).
_POLITENESS_DELAY = 1.0

# Exponential backoff: initial delay, max delay, max retry count.
_BACKOFF_INITIAL = 1.0  # seconds
_BACKOFF_MAX = 10.0  # seconds
_BACKOFF_MAX_RETRIES = 3

# HTTP status codes considered transient (worth retrying).
_TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})

# Prevent overlapping scrape operations (e.g. double-click of Corpus aktualisieren).
_SCRAPE_SEMAPHORE = asyncio.Semaphore(1)

# ---------------------------------------------------------------------------
# Runtime corpus source selection (persisted to .corpus_sources.json)
# ---------------------------------------------------------------------------
_CORPUS_SOURCES_FILE = Path(".corpus_sources.json")

CORPUS_SOURCE_METADATA: dict[str, dict[str, object]] = {
    "sgb2": {
        "key": "sgb2",
        "name": "SGB II",
        "full_name": "SGB II (Bürgergeld, Grundsicherung für Arbeitsuchende)",
        "description": (
            "Grundsicherung für Arbeitsuchende — das zentrale Gesetz für Bürgergeld, "
            "Eingliederungsleistungen und Sanktionen."
        ),
        "tooltip": (
            "Unverzichtbar. Regelt Bürgergeld, Leistungen zur Eingliederung, "
            "Sanktionen, Einkommensanrechnung und Bedarfsermittlung."
        ),
        "has_scraper": True,
        "checked_by_default": True,
        "source": "gesetze-im-internet.de",
    },
    "sgbx": {
        "key": "sgbx",
        "name": "SGB X",
        "full_name": "SGB X (Sozialverwaltungsverfahren und Sozialdatenschutz)",
        "description": (
            "Regelt Verwaltungsverfahren, Datenschutz und Zusammenarbeit "
            "der Sozialleistungsträger."
        ),
        "tooltip": (
            "Wichtig für Verfahrensfragen. Definiert Fristen, Akteneinsicht, "
            "Anhörung, Datenschutz im Sozialrecht."
        ),
        "has_scraper": True,
        "checked_by_default": True,
        "source": "gesetze-im-internet.de",
    },
    "sgb1": {
        "key": "sgb1",
        "name": "SGB I",
        "full_name": "SGB I (Allgemeiner Teil)",
        "description": (
            "Allgemeiner Teil des Sozialgesetzbuchs — Grundprinzipien, "
            "soziale Rechte, Aufklärung, Beratung."
        ),
        "tooltip": (
            "Empfohlen. Enthält übergreifende Prinzipien wie Aufklärungs- "
            "und Beratungspflichten nach §§ 13–15 SGB I."
        ),
        "has_scraper": True,
        "checked_by_default": True,
        "source": "gesetze-im-internet.de",
    },
    "sgb12": {
        "key": "sgb12",
        "name": "SGB XII",
        "full_name": "SGB XII (Sozialhilfe)",
        "description": (
            "Sozialhilfe — Hilfe zum Lebensunterhalt, Grundsicherung im Alter, "
            "Eingliederungshilfe."
        ),
        "tooltip": (
            "Relevant für Abgrenzung SGB II vs. SGB XII und bei " "Erwerbsminderung (§ 41 SGB XII)."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "sgb3": {
        "key": "sgb3",
        "name": "SGB III",
        "full_name": "SGB III (Arbeitsförderung)",
        "description": (
            "Arbeitsförderung — Arbeitslosengeld, Vermittlung, " "Berufsberatung, Weiterbildung."
        ),
        "tooltip": (
            "Nützlich für Eingliederungsleistungen nach § 16 SGB II " "(Verweiskette ins SGB III)."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "sgb9": {
        "key": "sgb9",
        "name": "SGB IX",
        "full_name": "SGB IX (Rehabilitation und Teilhabe)",
        "description": "Rehabilitation und Teilhabe von Menschen mit Behinderungen.",
        "tooltip": "Spezialfall. Relevant wenn Behinderung oder Reha im Spiel ist.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "bgb": {
        "key": "bgb",
        "name": "BGB",
        "full_name": "BGB (Bürgerliches Gesetzbuch)",
        "description": (
            "Bürgerliches Gesetzbuch — allgemeines Zivilrecht, " "Verträge, Schuldverhältnisse."
        ),
        "tooltip": "Geringe Relevanz. Nur in Ausnahmefällen (z.B. zivilrechtliche Vorfragen).",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "egbgb": {
        "key": "egbgb",
        "name": "EGBGB",
        "full_name": "Einführungsgesetz zum BGB",
        "description": "Informationspflichten und Übergangsrecht für Verträge.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "owig": {
        "key": "owig",
        "name": "OWiG",
        "full_name": "OWiG",
        "description": "Bußgeldverfahren, Einspruch und Akteneinsicht.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "stvg": {
        "key": "stvg",
        "name": "StVG",
        "full_name": "StVG",
        "description": "Straßenverkehrsgesetz; Fahrverbot, Register und Verjährung.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "stvo": {
        "key": "stvo",
        "name": "StVO",
        "full_name": "StVO",
        "description": (
            "Straßenverkehrs-Ordnung; " "nur Paragraphen, Anlagen nicht automatisch eingelesen."
        ),
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "bkatv": {
        "key": "bkatv",
        "name": "BKatV",
        "full_name": "BKatV",
        "description": (
            "Bußgeldkatalog-Verordnung; "
            "nur Paragraphen, Anlagen und Sanktionstabellen nicht automatisch eingelesen."
        ),
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "fev": {
        "key": "fev",
        "name": "FeV",
        "full_name": "FeV",
        "description": (
            "Fahrerlaubnis-Verordnung; "
            "nur Paragraphen, Anlagen und Punktetabellen nicht automatisch eingelesen."
        ),
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "stpo": {
        "key": "stpo",
        "name": "StPO",
        "full_name": "StPO",
        "description": "Strafprozessordnung; ergänzende Verfahrensregeln für OWiG.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "famfg": {
        "key": "famfg",
        "name": "FamFG",
        "full_name": "FamFG",
        "description": "Verfahren in Familiensachen; Beschwerden und Bekanntgabe.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "uvg": {
        "key": "uvg",
        "name": "UhVorschG",
        "full_name": "UhVorschG",
        "description": "Unterhaltsvorschuss; Voraussetzungen und Anrechnung.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "minuhv": {
        "key": "minuhv",
        "name": "MinUhV",
        "full_name": "MinUhV",
        "description": "Gesetzlicher Mindestunterhalt minderjähriger Kinder.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "estg": {
        "key": "estg",
        "name": "EStG",
        "full_name": "Einkommensteuergesetz",
        "description": "Einkommensteuer natürlicher Personen; keine vollständige Veranlagung.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "ao": {
        "key": "ao",
        "name": "AO",
        "full_name": "Abgabenordnung",
        "description": "Besteuerungsverfahren, Bekanntgabe und Einspruch.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "solzg": {
        "key": "solzg",
        "name": "SolZG",
        "full_name": "Solidaritätszuschlaggesetz 1995",
        "description": "Solidaritätszuschlag; Voraussetzungen gesondert prüfen.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "fgo": {
        "key": "fgo",
        "name": "FGO",
        "full_name": "Finanzgerichtsordnung",
        "description": "Finanzgerichtliche Verfahren und Fristen.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "stberg": {
        "key": "stberg",
        "name": "StBerG",
        "full_name": "Steuerberatungsgesetz",
        "description": "Grenzen der Hilfeleistung in Steuersachen; nur eigene Angelegenheiten.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "aufenthg": {
        "key": "aufenthg",
        "name": "AufenthG",
        "full_name": "AufenthG",
        "description": "Aufenthaltstitel und Verlängerung; keine individuelle Statusentscheidung.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "asylg": {
        "key": "asylg",
        "name": "AsylG",
        "full_name": "AsylG",
        "description": "Asylverfahren und Fristschutz; Übergangsrecht gesondert prüfen.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "aufenthv": {
        "key": "aufenthv",
        "name": "AufenthV",
        "full_name": "AufenthV",
        "description": "Aufenthaltsverordnung; nur Paragraphen, Anlagen nicht vollständig erfasst.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "beschv": {
        "key": "beschv",
        "name": "BeschV",
        "full_name": "BeschV",
        "description": "Beschäftigungsverordnung; keine automatische Arbeitserlaubnis.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "freizuegg_eu": {
        "key": "freizuegg_eu",
        "name": "FreizügG/EU",
        "full_name": "FreizügG/EU",
        "description": "Freizügigkeit; vom Aufenthaltsgesetz getrennt prüfen.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "stag": {
        "key": "stag",
        "name": "StAG",
        "full_name": "StAG",
        "description": "Staatsangehörigkeit und Einbürgerungsvorbereitung.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "vwgo": {
        "key": "vwgo",
        "name": "VwGO",
        "full_name": "VwGO",
        "description": "Verwaltungsgerichtliche Verfahren und Fristen.",
        "tooltip": "Nur nach ausdrücklicher Quellenauswahl laden; Abdeckung prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "eu261": {
        "key": "eu261",
        "name": "VO (EG) Nr. 261/2004",
        "full_name": "Verordnung (EG) Nr. 261/2004 über Fluggastrechte",
        "description": "Amtlicher Verordnungstext zu Fluggastrechten.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden; Rechtsprechung separat prüfen.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "eur-lex.europa.eu",
    },
    "betrkv": {
        "key": "betrkv",
        "name": "BetrKV",
        "full_name": "Betriebskostenverordnung",
        "description": "Betriebskostenarten bei Wohnraummiete.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "heizkostenv": {
        "key": "heizkostenv",
        "name": "HeizkostenV",
        "full_name": "Heizkostenverordnung",
        "description": "Verteilung und Abrechnung von Heiz- und Warmwasserkosten.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "landes_mietrecht": {
        "key": "landes_mietrecht",
        "name": "Landes-Mietrechtsverordnungen",
        "full_name": "Landesrechtliche Mietpreis- und Kappungsgrenzenverordnungen",
        "description": "Explizit importierte, datierte amtliche Geltungsnachweise.",
        "tooltip": "Kein automatischer Abruf; geprüfte amtliche Auszüge separat importieren.",
        "has_scraper": False,
        "checked_by_default": False,
        "source": "Amtliche Veröffentlichungen der Länder",
    },
    "zpo": {
        "key": "zpo",
        "name": "ZPO",
        "full_name": "Zivilprozessordnung",
        "description": "Zivilgerichtliches Verfahren und Zwangsvollstreckung.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "inso": {
        "key": "inso",
        "name": "InsO",
        "full_name": "Insolvenzordnung",
        "description": "Insolvenzverfahren und Schuldenbereinigung.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "rdg": {
        "key": "rdg",
        "name": "RDG",
        "full_name": "Rechtsdienstleistungsgesetz",
        "description": "Rechtsdienstleistungen und Inkassokosten.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "rvg": {
        "key": "rvg",
        "name": "RVG",
        "full_name": "Rechtsanwaltsvergütungsgesetz",
        "description": "Vergütung und Gebühren für Rechtsdienstleistungen.",
        "tooltip": "Quelle nur nach ausdrücklicher Auswahl laden.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "vwvfg": {
        "key": "vwvfg",
        "name": "VwVfG",
        "full_name": "VwVfG (Verwaltungsverfahrensgesetz)",
        "description": (
            "Bundes-Verwaltungsverfahrensgesetz — allgemeines " "Verwaltungsverfahrensrecht."
        ),
        "tooltip": (
            "Ergänzend. Regeln für Verwaltungsakte, Widerspruchsverfahren " "außerhalb SGB X."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "sgg": {
        "key": "sgg",
        "name": "SGG",
        "full_name": "SGG (Sozialgerichtsgesetz)",
        "description": "Sozialgerichtsgesetz — Verfahren vor den Sozialgerichten.",
        "tooltip": (
            "Nur für Verfahrensfragen relevant (Klagefristen, Rechtsmittel, "
            "einstweiliger Rechtsschutz)."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "weisung": {
        "key": "weisung",
        "name": "Fachliche Weisungen",
        "full_name": "Fachliche Weisungen der BA (SGB II)",
        "description": (
            "Verwaltungsinterne Weisungen der Bundesagentur für Arbeit "
            "zur Anwendung des SGB II — PDFs von arbeitsagentur.de."
        ),
        "tooltip": (
            "Sehr wertvoll für die Praxis. Enthält Auslegungshilfen, "
            "Ermessensdirektiven, Berechnungsbeispiele und Verfahrens- "
            "hinweise der BA. Kein Gesetz, aber bindend für die Jobcenter."
        ),
        "has_scraper": True,
        "checked_by_default": True,
        "source": "arbeitsagentur.de",
    },
    "bsg": {
        "key": "bsg",
        "name": "BSG-Rechtsprechung",
        "full_name": "BSG-Rechtsprechung (Bundessozialgericht)",
        "description": "Entscheidungen des Bundessozialgerichts zu SGB II/SGB XII.",
        "tooltip": (
            "Entscheidungen aus rechtsprechung-im-internet.de, soweit ein "
            "geprüftes Modul sie in seiner corpus.yaml (`case_law`) anfordert."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "rechtsprechung-im-internet.de",
    },
    "erbstg": {
        "key": "erbstg",
        "name": "ErbStG",
        "full_name": "ErbStG (Erbschaftsteuer- und Schenkungsteuergesetz)",
        "description": (
            "Erbschaft- und Schenkungsteuer: Freibeträge, Steuerklassen, "
            "Bewertung von Grundvermögen, land- und forstwirtschaftlichem "
            "Vermögen, Betriebsvermögen und sonstigem Vermögen."
        ),
        "tooltip": (
            "Neu. Erforderlich für jede erbrechtliche oder schenkungs-"
            "rechtliche Analyse, die steuerliche Auswirkungen hat."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "hoefev": {
        "key": "hoefev",
        "name": "HöfeO",
        "full_name": "Höfeordnung (HöfeO)",
        "description": (
            "Höfeordnung — Sondererbrecht für landwirtschaftliche "
            "Höfe in einigen Bundesländern: Hofesübergabe, "
            "Abfindung weichender Erben, Ertragswertverfahren."
        ),
        "tooltip": (
            "Neu. Regional begrenzt. Relevant für Hofübergaben in "
            "Bundesländern mit Höfeordnung (z. B. NW, NDS, SH, HE, RP, BY)."
        ),
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "kschg": {
        "key": "kschg",
        "name": "KSchG",
        "full_name": "Kündigungsschutzgesetz (KSchG)",
        "description": "Kündigungsschutz in Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "burlg": {
        "key": "burlg",
        "name": "BUrlG",
        "full_name": "Bundesurlaubsgesetz (BUrlG)",
        "description": "Bundesurlaubsgesetz zur Vorbereitung Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "tzbfg": {
        "key": "tzbfg",
        "name": "TzBfG",
        "full_name": "Teilzeit- und Befristungsgesetz (TzBfG)",
        "description": "Teilzeit und Befristung in Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "entgfg": {
        "key": "entgfg",
        "name": "EntgFG",
        "full_name": "Entgeltfortzahlungsgesetz (EntgFG)",
        "description": "Entgeltfortzahlung in Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "milog": {
        "key": "milog",
        "name": "MiLoG",
        "full_name": "Mindestlohngesetz (MiLoG)",
        "description": "Mindestlohngesetz zur Vorbereitung Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "muschg": {
        "key": "muschg",
        "name": "MuSchG",
        "full_name": "Mutterschutzgesetz (MuSchG)",
        "description": "Mutterschutzgesetz zur Vorbereitung Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "arbzg": {
        "key": "arbzg",
        "name": "ArbZG",
        "full_name": "Arbeitszeitgesetz (ArbZG)",
        "description": "Arbeitszeitgesetz zur Vorbereitung Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "arbgg": {
        "key": "arbgg",
        "name": "ArbGG",
        "full_name": "Arbeitsgerichtsgesetz (ArbGG)",
        "description": "Arbeitsgerichtsgesetz zur Vorbereitung Ihrer eigenen Arbeitsangelegenheit.",
        "tooltip": "Amtlicher Gesetzestext; Auswahl und Ingestion erfolgen ausdrücklich.",
        "has_scraper": True,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
    "tvg": {
        "key": "tvg",
        "name": "TVG",
        "full_name": "TVG (Tarifvertragsgesetz)",
        "description": (
            "Tarifvertragsgesetz — Abschluss, Wirkung und Beendigung " "von Tarifverträgen."
        ),
        "tooltip": (
            "Noch nicht verfügbar. Scraper ist geplant; bis dahin "
            "wird die Quelle im Auswahlmenü als deaktiviert angezeigt."
        ),
        "has_scraper": False,
        "checked_by_default": False,
        "source": "gesetze-im-internet.de",
    },
}


def _get_corpus_sources_path() -> Path:
    """Return the path to the runtime corpus sources config file."""
    return _CORPUS_SOURCES_FILE


def load_runtime_sources() -> list[str] | None:
    """Load runtime corpus source selection from JSON file.

    Returns None if the file doesn't exist (meaning the env default
    should be used instead).
    """
    path = _get_corpus_sources_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        selected = data.get("selected_sources", [])
        return selected if isinstance(selected, list) else None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None


def save_runtime_sources(sources: list[str]) -> None:
    """Save runtime corpus source selection to JSON file."""
    path = _get_corpus_sources_path()
    data: dict[str, object] = {
        "selected_sources": sources,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def default_corpus_sources(configured: list[str] | None = None) -> list[str]:
    """Explicit ``CORPUS_SOURCES``, or no sources when unconfigured (D-070).

    *configured* lets callers that read a (patchable) settings object pass
    their own ``CORPUS_SOURCES``; ``None`` reads the module-level settings.
    """
    if configured is None:
        configured = settings.CORPUS_SOURCES
    if configured is not None:
        return list(configured)
    return []


async def get_effective_corpus_sources() -> list[str]:
    """Get the effective list of corpus sources to ingest.

    Prefers runtime configuration (from .corpus_sources.json) over the
    configured default (:func:`default_corpus_sources`) and validates that all
    requested sources are known.
    """
    runtime = load_runtime_sources()
    if runtime is not None:
        valid = [s for s in runtime if s in CORPUS_SOURCE_METADATA]
        unknown = set(runtime) - set(CORPUS_SOURCE_METADATA)
        if unknown:
            logger.warning("Ignoring unknown corpus sources from runtime config: %s", unknown)
        return valid
    return default_corpus_sources()


#: Source types filled from case-law providers (WP-113) instead of statutes.
CASE_LAW_SOURCE_TYPES = frozenset({"bsg"})


# ---------------------------------------------------------------------------
# Source URL prefixes (gesetze-im-internet.de official XML/HTML endpoints)
# ---------------------------------------------------------------------------
_BASE = "https://www.gesetze-im-internet.de"

_SOURCE_TYPE_PREFIX: dict[str, str] = {
    "sgb2": "/sgb_2/",
    "sgbx": "/sgb_10/",  # SGB X = Zehntes Buch → sgb_10
    "sgb12": "/sgb_12/",  # SGB XII - Sozialhilfe
    "sgb1": "/sgb_1/",  # SGB I - Allgemeiner Teil
    "sgb3": "/sgb_3/",  # SGB III - Arbeitsförderung
    "sgb9": "/sgb_9/",  # SGB IX - Rehabilitation und Teilhabe
    "bgb": "/bgb/",
    "egbgb": "/bgbeg/",
    "owig": "/owig_1968/",
    "stvg": "/stvg/",
    "stvo": "/stvo_2013/",
    "bkatv": "/bkatv_2013/",
    "fev": "/fev_2010/",
    "famfg": "/famfg/",
    "uvg": "/uhvorschg/",
    "minuhv": "/minuhv/",
    "estg": "/estg/",
    "ao": "/ao_1977/",
    "solzg": "/solzg_1995/",
    "fgo": "/fgo/",
    "stberg": "/stberg/",
    "aufenthg": "/aufenthg_2004/",
    "asylg": "/asylvfg_1992/",
    "aufenthv": "/aufenthv/",
    "beschv": "/beschv_2013/",
    "freizuegg_eu": "/freiz_gg_eu_2004/",
    "stag": "/stag/",
    "vwgo": "/vwgo/",
    "stpo": "/stpo/",
    "kschg": "/kschg/",
    "burlg": "/burlg/",
    "tzbfg": "/tzbfg/",
    "entgfg": "/entgfg/",
    "milog": "/milog/",
    "muschg": "/muschg_2018/",
    "arbzg": "/arbzg/",
    "arbgg": "/arbgg/",
    # BGB - Bürgerliches Gesetzbuch
    "betrkv": "/betrkv/",
    "heizkostenv": "/heizkostenv/",
    "zpo": "/zpo/",
    "inso": "/inso/",
    "rdg": "/rdg/",
    "rvg": "/rvg/",
    "vwvfg": "/vwvfg/",  # VwVfG - Verwaltungsverfahrensgesetz
    "sgg": "/sgg/",  # SGG - Sozialgerichtsgesetz
    "erbstg": "/erbstg/",  # ErbStG - Erbschaft- und Schenkungsteuergesetz
    "hoefev": "/hoefeordn_/",  # Höfeordnung (slug varies by BL; fallback)
}


def gii_source_slugs() -> dict[str, str]:
    """Source type → gesetze-im-internet.de directory slug (``sgb2`` → ``sgb_2``).

    Used by the daily change detection (WP-113) to find each source's
    ``xml.zip`` in ``gii-toc.xml``.
    """
    return {key: prefix.strip("/") for key, prefix in _SOURCE_TYPE_PREFIX.items()}


# ---------------------------------------------------------------------------
# § range → legal_area tagger (module data, WP-93)
# ---------------------------------------------------------------------------
# Paragraph ranges per source type are declared by modules as
# ``chunk_tags`` in ``modules/<id>/corpus.yaml`` and stamped on
# legal_chunk.legal_area. Ranges are inclusive on both ends; the first
# matching range (area-table order) wins. Tagging is purely additive:
# chunks outside every range (e.g. "Allgemein" headers) get legal_area=None.
# legal_chunk.legal_area is kept for backward compatibility
# (ARCHITECTURE.md § 4); module corpus scopes are the retrieval filter.


def _chunk_tag_ranges(source_type: str) -> list[tuple[tuple[int, int], str]]:
    from app.modules.areas import area_tables

    return [
        ((lo, hi), area)
        for tag_source, lo, hi, area in area_tables().chunk_tags
        if tag_source == source_type
    ]


def _infer_legal_area_for_bgb(hierarchy_path: str) -> str | None:
    """Return the legal_area for a BGB chunk based on its §-reference.

    Parameters
    ----------
    hierarchy_path :
        The chunk's hierarchy path (e.g. ``"BGB > § 1933"``). Only the
        §-number is inspected; other parts of the path are ignored.

    Returns
    -------
    str | None
        The matched ``legal_area`` (module-declared ``chunk_tags``) or
        ``None`` if the paragraph falls outside any declared range.
    """
    if not hierarchy_path:
        return None
    match = _PARA_TAG_RE.search(hierarchy_path)
    if not match:
        return None
    try:
        para = int(match.group(1))
    except (TypeError, ValueError):
        return None
    for (lo, hi), area in _chunk_tag_ranges("bgb"):
        if lo <= para <= hi:
            return area
    return None


# Numeric range tag for BGB area classification; section identities use _SECTION_TAG_RE.
_PARA_TAG_RE = re.compile(r"§\s*(\d+)")
_SECTION_TAG_RE = re.compile(r"§\s*(\d+[a-z]?)\b", re.IGNORECASE)

# Regex for Absatz references, e.g. "Abs. 1", "Abs. 2", "Abs. 3"
_ABSATZ_RE = re.compile(r"Abs\.\s*(\d+)")

# Regex for Satz references, e.g. "Satz 1", "Satz 2", "Satz 3"
# Also matches numbered sentences like "1.", "2." at start of lines
_SATZ_RE = re.compile(r"Satz\s*(\d+)")
_ENUM_SENTENCE_RE = re.compile(r"^(\d+)\.\s+")

# ---------------------------------------------------------------------------
# Polite HTTP helper with exponential backoff
# ---------------------------------------------------------------------------


async def _http_get_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    delay: float = _POLITENESS_DELAY,
) -> httpx.Response:
    """GET *url* with exponential backoff on transient failures.

    Only retries on connection errors, timeouts, and 5xx / 429 responses.
    Respects a minimum politeness delay between the previous request and
    this one (the caller must manage the shared clock; this function only
    enforces the backoff on retries).
    """
    last_exc: Exception | None = None

    for attempt in range(_BACKOFF_MAX_RETRIES + 1):
        try:
            resp = await client.get(url)
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
            last_exc = exc
        else:
            if resp.status_code < 500 and resp.status_code not in _TRANSIENT_CODES:
                return resp  # success or non-retryable client error
            # Transient status – treat as retryable
            last_exc = httpx.HTTPStatusError(
                f"Transient {resp.status_code}",
                request=resp.request,
                response=resp,
            )

        if attempt == _BACKOFF_MAX_RETRIES:
            break

        sleep_s = min(delay * (2**attempt), _BACKOFF_MAX)
        logger.warning(
            "HTTP GET %s failed (attempt %d/%d): %s – retrying in %.1fs",
            url,
            attempt + 1,
            _BACKOFF_MAX_RETRIES + 1,
            last_exc,
            sleep_s,
        )
        await asyncio.sleep(sleep_s)

    raise last_exc  # type: ignore[misc]


async def scrape_and_chunk(
    source_type: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Scrape a legal corpus and return hierarchical chunks.

    Dispatches to the appropriate scraper based on *source_type*:
    - Gesetze-im-Internet sources (sgb2, sgbx, …): HTML parsing
    - weisung: PDF scraping from arbeitsagentur.de

    Args:
        source_type: One of the keys in :data:`CORPUS_SOURCE_METADATA`.

    Returns:
        List of dicts with keys: ``id``, ``source_type``, ``title``,
        ``unit_type``, ``hierarchy_path``, ``text_content``,
        ``effective_date``, ``source_url``, ``version_hash``, ``chunk_id``.
    """
    if source_type not in CORPUS_SOURCE_METADATA:
        raise ValueError(
            f"Unknown source_type={source_type!r}. " f"Allowed: {list(CORPUS_SOURCE_METADATA)}"
        )

    if source_type == "eu261":
        return await scrape_eu261(client=client)

    # Dispatch weisung to dedicated PDF scraper
    if source_type == "weisung":
        return await scrape_weisungen(client=client)

    if source_type == "landes_mietrecht":
        raise ValueError(
            "State tenancy evidence requires an explicit official snapshot import "
            "through normalize_state_ordinance(); no automatic state scraper is available."
        )

    # WP-113: case-law source types are filled from the `case_law`
    # declarations of verified modules (RII / Open Legal Data).
    if source_type in CASE_LAW_SOURCE_TYPES:
        from app.services.case_law import scrape_case_law

        async with _SCRAPE_SEMAPHORE:
            return await scrape_case_law(source_type, client=client)

    # All other known source types use gesetze-im-internet.de
    if source_type not in _SOURCE_TYPE_PREFIX:
        raise ValueError(f"No gesetze-im-internet.de mapping for source_type={source_type!r}.")

    prefix = _SOURCE_TYPE_PREFIX[source_type]
    index_url = urljoin(_BASE, prefix)

    async with _SCRAPE_SEMAPHORE:
        async with client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            limits=_HTTP_LIMITS,
        ) as c:
            # Step 1: Fetch index page to find consolidated HTML link
            resp = await _http_get_with_backoff(c, index_url)
            resp.raise_for_status()
            index_soup = BeautifulSoup(resp.text, "lxml")

            # Step 2: Find consolidated HTML link (BJNR*.html in same directory)
            consolidated_href = _find_consolidated_href(index_soup)
            if not consolidated_href:
                logger.warning(
                    "No consolidated HTML found for source_type=%s at %s", source_type, index_url
                )
                return []

            consolidated_url = urljoin(index_url, consolidated_href)
            logger.info("Fetching consolidated HTML: %s", consolidated_url)

            # Politeness delay between requests to the same host.
            await asyncio.sleep(_POLITENESS_DELAY)

            # Step 3: Fetch consolidated HTML
            resp = await _http_get_with_backoff(c, consolidated_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

        # Step 4: Extract metadata (outside the HTTP client context but inside semaphore)
        law_name = _infer_law_name(soup, source_type)
        effective_date = _infer_effective_date(soup)

        # Step 5: Parse law structure (§ → Absatz)
        chunks = _parse_law_sections(soup, source_type, law_name, effective_date, prefix)

    logger.info("Scraped %d chunks for source_type=%s", len(chunks), source_type)
    return chunks


_EU261_URL = "https://eur-lex.europa.eu/LexUriServ/LexUriServ.do?uri=CELEX:32004R0261:DE:HTML"


async def scrape_eu261(*, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    """Read the official original act; never substitute recitals or a challenge page.

    This endpoint is the original 2004 publication, effective 2005-02-17, not a
    claim of consolidated case-law coverage. Numbered paragraphs retain their
    lettered lists, so the conditions and exceptions travel with each chunk.
    """
    async with _SCRAPE_SEMAPHORE:
        if client is not None:
            response = await _http_get_with_backoff(client, _EU261_URL)
        else:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0, limits=_HTTP_LIMITS
            ) as c:
                response = await _http_get_with_backoff(c, _EU261_URL)
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("EUR-Lex did not return the official article text")
        soup = BeautifulSoup(response.text, "lxml")
        nodes = soup.find_all("p")
        article: str | None = None
        absatz = ""
        parts: list[str] = []
        chunks: list[dict[str, Any]] = []

        def flush() -> None:
            if article is None or not parts:
                return
            text = normalize_text(" ".join(parts))
            path = f"VO (EG) Nr. 261/2004 > Art. {article}"
            if absatz:
                path += f" > Abs. {absatz}"
            chunks.append(
                {
                    "id": str(uuid4()),
                    "chunk_id": str(uuid4()),
                    "source_type": "eu261",
                    "title": "VO (EG) Nr. 261/2004",
                    "unit_type": "satz",
                    "hierarchy_path": path,
                    "text_content": text,
                    "effective_date": "2005-02-17",
                    "source_url": _EU261_URL,
                    "version_hash": _compute_version_hash(text),
                    "legal_area": None,
                }
            )

        for node in nodes:
            text = node.get_text(" ", strip=True)
            heading = re.fullmatch(r"Artikel\s+(\d{1,2})", text)
            if heading:
                flush()
                article, absatz, parts = heading.group(1), "", []
                continue
            if article is None or not text:
                continue
            numbered = re.match(r"\((\d+)\)\s*", text)
            if numbered:
                # The article caption belongs to its first paragraph, not an
                # independent fragment that could be retrieved as a legal rule.
                if absatz:
                    flush()
                    parts = []
                absatz = numbered.group(1)
            if text.startswith("Geschehen zu Straßburg"):
                flush()
                article, parts = None, []
                break
            parts.append(text)
        flush()
        articles = {
            int(match.group(1))
            for chunk in chunks
            if (match := re.search(r" > Art\. (\d+)", chunk["hierarchy_path"]))
        }
        if articles != set(range(1, 20)):
            raise ValueError("EUR-Lex article text missing or incomplete")
        return chunks


def _find_consolidated_href(soup: BeautifulSoup) -> str | None:
    """Find the consolidated HTML link (BJNR<digits>.html) on the index page."""
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag["href"])
        if re.match(r"^BJNR\d+\.html$", href):
            return href
    return None


# ---------------------------------------------------------------------------
# Weisung PDF scraper (arbeitsagentur.de)
# ---------------------------------------------------------------------------
# Index page listing all Fachliche Weisungen organised by SGB paragraph.
_WEISUNG_INDEX = (
    "https://www.arbeitsagentur.de/ueber-uns/"
    "veroeffentlichungen/weisungen/weisungen-nach-rechtsnorm"
)
_WEISUNG_PDF_RE = re.compile(r"fw-sgb-?ii.*\.pdf", re.IGNORECASE)


async def scrape_weisungen(
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Scrape Fachliche Weisungen (SGB II) PDFs from arbeitsagentur.de.

    Fetches the Weisungen-nach-Rechtsnorm index page, finds all
    SGB II PDF links, downloads each PDF, extracts text via pdfplumber,
    and returns hierarchical chunks suitable for embedding.
    """
    chunks: list[dict[str, Any]] = []

    async with client or httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        limits=_HTTP_LIMITS,
    ) as c:
        # ── Step 1: Fetch the Weisungen index page ───────────────────
        resp = await _http_get_with_backoff(c, _WEISUNG_INDEX)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # ── Step 2: Find all SGB II PDF links ────────────────────────
        pdf_links = _find_weisung_pdf_links(soup)
        if not pdf_links:
            logger.warning("No SGB II Weisung PDF links found at %s", _WEISUNG_INDEX)
            return []

        logger.info("Found %d Weisung PDF links for SGB II", len(pdf_links))

        # ── Step 3: Download and parse each PDF sequentially ─────────
        for i, (pdf_url, pdf_title) in enumerate(pdf_links):
            # Be a good netizen — delay between consecutive requests.
            await asyncio.sleep(_POLITENESS_DELAY)

            try:
                pdf_chunks = await _scrape_weisung_pdf(
                    c,
                    pdf_url,
                    pdf_title,
                    i + 1,
                    len(pdf_links),
                )
                chunks.extend(pdf_chunks)
            except Exception as exc:
                logger.warning(
                    "Failed to scrape Weisung %d/%d: %s — %s",
                    i + 1,
                    len(pdf_links),
                    pdf_title or pdf_url,
                    exc,
                )

    logger.info("Scraped %d chunks from %d Weisungen", len(chunks), len(pdf_links))
    return chunks


def _find_weisung_pdf_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Find all SGB II Weisung PDF links on the index page.

    Returns list of (url, title) tuples.
    """
    links: list[tuple[str, str]] = []
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag["href"])
        if _WEISUNG_PDF_RE.search(href):
            text = a_tag.get_text(strip=True) or href
            # Resolve relative URLs
            if href.startswith("/"):
                href = urljoin("https://www.arbeitsagentur.de", href)
            links.append((href, text))
    return links


async def _scrape_weisung_pdf(
    client: httpx.AsyncClient,
    pdf_url: str,
    title: str,
    index: int,
    total: int,
) -> list[dict[str, Any]]:
    """Download a single Weisung PDF, extract text, and chunk it hierarchically.

    Uses pdfplumber for text extraction and applies the same hierarchical
    parsing logic as the gesetze-im-internet scraper (Absatz-level chunks).
    """
    import io

    import pdfplumber

    logger.info("Downloading Weisung %d/%d: %s", index, total, title or pdf_url)
    resp = await _http_get_with_backoff(client, pdf_url)
    resp.raise_for_status()

    chunks: list[dict[str, Any]] = []

    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        full_text_parts: list[str] = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text_parts.append(text)

        if not full_text_parts:
            logger.warning("No extractable text in Weisung PDF: %s", title or pdf_url)
            return []

        full_text = "\n\n".join(full_text_parts)
        full_text = _clean_ocr_artefacts(full_text)

        # Attempt to detect § references and split into paragraph-level chunks
        para_chunks = _split_weisung_into_paragraphs(full_text, title, pdf_url)
        chunks.extend(para_chunks)

    return chunks


def _split_weisung_into_paragraphs(
    text: str,
    title: str,
    source_url: str,
) -> list[dict[str, Any]]:
    """Split Weisung text into paragraph-level chunks on § markers.

    Weisung PDFs contain the full Gesetzestext followed by the BA commentary.
    We split on ``§ NNN`` boundaries and treat each as a chunk.
    """
    chunks: list[dict[str, Any]] = []

    # Split on "§ <number>" boundaries (German paragraph markers)
    sections = re.split(r"\n(?=§\s+\d+)", text)

    for section in sections:
        norm_text = normalize_text(section)
        if not norm_text:
            continue

        # Extract paragraph number
        para_match = _SECTION_TAG_RE.search(norm_text)
        para_label = f"§ {para_match.group(1)}" if para_match else "Allgemein"

        hierarchy = ["Fachliche Weisung", para_label]

        chunks.append(
            {
                "id": str(uuid4()),
                "source_type": "weisung",
                "title": "Fachliche Weisung",
                "unit_type": "absatz",
                "hierarchy_path": " > ".join(hierarchy),
                "text_content": norm_text,
                "effective_date": date.today().isoformat(),
                "source_url": source_url,
                "version_hash": _compute_version_hash(norm_text),
                "chunk_id": str(uuid4()),
                "legal_area": None,
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# Consolidated HTML parser
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Consolidated HTML parser
# ---------------------------------------------------------------------------


def _parse_law_sections(
    soup: BeautifulSoup,
    source_type: str,
    law_name: str,
    effective_date: date,
    prefix: str,
) -> list[dict[str, Any]]:
    """Parse consolidated HTML (BJNR*.html) into Absatz-level chunks.

    Scans ``div.jnnorm`` elements for ``span.jnenbez`` containing a § reference,
    then extracts ``div.jurAbsatz`` children as individual paragraphs.

    Returns one chunk per ``jurAbsatz`` with hierarchy: Law > § N > Abs. X.
    """
    chunks: list[dict[str, Any]] = []
    source_url = urljoin(_BASE, prefix)

    current_article = ""
    for jnnorm in soup.find_all("div", class_="jnnorm"):
        if not isinstance(jnnorm, Tag):
            continue

        if source_type == "egbgb":
            # GiI places article headings in unclassed h2 spans; the following
            # § nodes carry only their local number. Retain the article scope.
            heading = jnnorm.select_one(".jnheader h2")
            if heading:
                match = re.match(r"Art\.?\s*(\d+[a-z]?)\b", heading.get_text(" ", strip=True))
                if match:
                    current_article = f"Art. {match.group(1)}"
        jnenbez_span = jnnorm.find("span", class_="jnenbez")
        if not jnenbez_span or not isinstance(jnenbez_span, Tag):
            continue

        jnenbez_text = " ".join(
            node.get_text(" ", strip=True) for node in jnnorm.find_all("span", class_="jnenbez")
        )
        article_match = re.search(r"Art\.?\s*(\d+[a-z]?)", jnenbez_text)
        if source_type == "egbgb" and article_match:
            current_article = f"Art. {article_match.group(1)}"
        para_match = _SECTION_TAG_RE.search(jnenbez_text)
        if not para_match and not (source_type == "egbgb" and article_match):
            continue

        para_label = f"§ {para_match.group(1)}" if para_match else ""

        # Collect all jurAbsatz divs within this jnnorm
        for jur_absatz in jnnorm.find_all("div", class_="jurAbsatz"):
            if not isinstance(jur_absatz, Tag):
                continue

            # Skip synthetic jurAbsatz that only contain tables of contents
            if jur_absatz.find("table") is not None:
                continue

            raw_text = jur_absatz.get_text(separator=" ", strip=True)
            if not raw_text:
                continue

            raw_text = _clean_ocr_artefacts(raw_text)
            norm_text = normalize_text(raw_text)
            if not norm_text:
                continue

            # Detect Absatz number from text pattern like "(1)", "(2)", etc.
            absatz_label = ""
            abs_match = re.match(r"\((\d+[a-z]?)\)\s+", norm_text)
            if abs_match:
                absatz_label = f"Abs. {abs_match.group(1)}"

            hierarchy = [law_name]
            if source_type == "egbgb" and current_article:
                hierarchy.append(current_article)
            if para_label:
                hierarchy.append(para_label)
            if absatz_label:
                hierarchy.append(absatz_label)

            hierarchy_path = " > ".join(hierarchy)

            # Tag BGB chunks with their legal_area (module chunk_tags,
            # WP-93; None outside every declared range). Other sources
            # leave legal_area=None — they are either single-domain
            # (sgb*, weisung) or otherwise un-tagged.
            legal_area: str | None = None
            if source_type == "bgb":
                legal_area = _infer_legal_area_for_bgb(hierarchy_path)

            chunks.append(
                {
                    "id": str(uuid4()),
                    "source_type": source_type,
                    "title": law_name,
                    "unit_type": "satz",
                    "hierarchy_path": hierarchy_path,
                    "text_content": norm_text,
                    "effective_date": effective_date.isoformat(),
                    "source_url": source_url,
                    "version_hash": _compute_version_hash(norm_text),
                    "chunk_id": str(uuid4()),
                    "legal_area": legal_area,
                }
            )

    return chunks


# ---------------------------------------------------------------------------
# Internal helpers (legacy — retained for compatibility)
# ---------------------------------------------------------------------------


# These are publication hosts, not geography or legal applicability rules.
# Keep import provenance bounded to the named Land's official publisher;
# municipality/validity decisions remain versioned module data.
_STATE_PUBLICATION_HOSTS: dict[str, frozenset[str]] = {
    "BE": frozenset({"www.berlin.de", "gesetze.berlin.de"}),
    "BB": frozenset({"mil.brandenburg.de", "bravors.brandenburg.de"}),
    "BW": frozenset({"mlw.baden-wuerttemberg.de", "www.landesrecht-bw.de"}),
    "BY": frozenset({"www.gesetze-bayern.de"}),
    "HB": frozenset({"www.transparenz.bremen.de"}),
    "HE": frozenset({"wirtschaft.hessen.de", "verkuendung.hessen.de"}),
    "HH": frozenset({"www.hamburg.de", "www.landesrecht-hamburg.de"}),
    "MV": frozenset({"www.mecklenburg-vorpommern.de", "www.landesrecht-mv.de"}),
    "NI": frozenset({"www.mw.niedersachsen.de", "www.nds-voris.de"}),
    "NW": frozenset({"recht.nrw.de"}),
    "RP": frozenset({"mkbwk.rlp.de", "landesrecht.rlp.de"}),
    "SH": frozenset({"www.schleswig-holstein.de", "www.gesetze-rechtsprechung.sh.juris.de"}),
    "SL": frozenset({"www.saarland.de", "recht.saarland.de"}),
    "SN": frozenset({"www.recht.sachsen.de", "www.revosax.sachsen.de"}),
    "ST": frozenset({"lv.sachsen-anhalt.de", "www.landesrecht.sachsen-anhalt.de"}),
    "TH": frozenset({"landesrecht.thueringen.de", "infrastruktur-landwirtschaft.thueringen.de"}),
}


def normalize_state_ordinance(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt an explicitly selected official excerpt to the existing chunk pipeline.

    This offline boundary does not fetch, embed, persist or establish current
    municipality coverage. The caller supplies a source-checked excerpt and
    may pass the resulting chunks to the existing embedding/upsert functions.
    The digest proves snapshot integrity, not legal or human review.
    """
    required = (
        "bundesland",
        "title",
        "official_url",
        "effective_date",
        "publication",
        "text",
        "sha256",
        "snapshot_kind",
    )
    if any(not isinstance(record.get(key), str) or not record[key].strip() for key in required):
        raise ValueError("State snapshot requires non-empty source, date, text and digest fields")
    land = record["bundesland"]
    if land not in _STATE_PUBLICATION_HOSTS:
        raise ValueError("State snapshot has an unsupported Bundesland")
    url = urlsplit(record["official_url"])
    if (
        url.scheme != "https"
        or url.hostname not in _STATE_PUBLICATION_HOSTS[land]
        or url.username is not None
        or url.password is not None
        or url.port not in (None, 443)
    ):
        raise ValueError("State snapshot URL must name the Land's official HTTPS publication host")
    effective_date = date.fromisoformat(record["effective_date"])
    if (
        record.get("valid_to") is not None
        and date.fromisoformat(record["valid_to"]) < effective_date
    ):
        raise ValueError("State snapshot validity interval is reversed")
    if record["snapshot_kind"] != "applicability_excerpt":
        raise ValueError("State snapshot must identify its limited applicability-excerpt coverage")
    if hashlib.sha256(record["text"].encode("utf-8")).hexdigest() != record["sha256"]:
        raise ValueError("State snapshot text does not match its SHA-256 evidence digest")
    title = record["title"].strip()
    if len(title) > 500:
        raise ValueError("State snapshot title exceeds the storage contract")
    # Identical text in another Land, publication or period must not collapse
    # under the existing (source_type, version_hash) source identity constraint.
    evidence = {key: record[key] for key in required if key != "text"}
    evidence["valid_to"] = record.get("valid_to")
    version_hash = _compute_version_hash(json.dumps(evidence, sort_keys=True, ensure_ascii=False))
    return [
        {
            "id": str(uuid4()),
            "source_type": "landes_mietrecht",
            "title": title,
            "jurisdiction": f"DE-{land}",
            "unit_type": "statute",
            "hierarchy_path": f"{title} > {record['publication']} > Geltungsnachweis (Auszug)",
            "text_content": (
                "Amtlicher Geltungsnachweis (Auszug; kein vollständiger Verordnungstext). "
                f"Stand/Gültigkeit ab {effective_date.isoformat()}"
                + (f" bis {record['valid_to']}" if record.get("valid_to") else "")
                + ". "
                + normalize_text(record["text"])
            ),
            "effective_date": effective_date.isoformat(),
            "source_url": record["official_url"],
            "version_hash": version_hash,
            "chunk_id": str(uuid4()),
            "legal_area": None,
        }
    ]


def _extract_paragraph_nodes(soup: BeautifulSoup, source_type: str) -> list[Tag]:
    """Find all paragraph elements (<p>, <norm> <jur> etc.) carrying legal text."""

    # Strategy 1: look for <p> tags inside <content> or <body>
    content_area = soup.find("content") or soup.find("body") or soup

    paragraphs: list[Tag] = []
    for tag in content_area.find_all(["p", "jur-body", "norm"]):
        if isinstance(tag, Tag):
            # Only include tags that have actual text content
            text = tag.get_text(strip=True)
            if text:
                paragraphs.append(tag)

    # Strategy 2: If the page has no structured elements, fall back to all <p>
    if not paragraphs:
        paragraphs = [p for p in soup.find_all("p") if p.get_text(strip=True)]

    return paragraphs


def _parse_paragraph_element(
    element: Tag,
    source_type: str,
) -> tuple[list[str], str]:
    """Extract hierarchy path and text from a single paragraph / legal element.

    Returns:
        Tuple of (hierarchy_list, raw_text).
        hierarchy_list example: ["SGB II", "§ 31", "Abs. 1", "Satz 2"]
    """
    text = element.get_text(separator=" ", strip=True)
    text = _clean_ocr_artefacts(text)

    # Build hierarchy from tag structure, attributes, and content cues
    law_name = _infer_law_name(element, source_type)

    # Extract paragraph number from text itself (e.g. "§ 31")
    para_match = _SECTION_TAG_RE.search(text)
    para_label = f"§ {para_match.group(1)}" if para_match else "Unbekannt"

    # Extract Absatz (Abs./Absatz X)
    absatz_match = _ABSATZ_RE.search(text)
    absatz_label = f"Abs. {absatz_match.group(1)}" if absatz_match else ""

    # Extract Satz (Satz X) or use numbered sentences
    satz_match = _SATZ_RE.search(text)
    satz_label = f"Satz {satz_match.group(1)}" if satz_match else ""

    hierarchy = [law_name, para_label]
    if absatz_label:
        hierarchy.append(absatz_label)
    if satz_label:
        hierarchy.append(satz_label)

    # If we couldn't detect any structural markers, fall back to the full text
    # as a single statute-level chunk.
    if not para_match and not absatz_match and not satz_match:
        return [law_name, "Allgemein"], text

    return hierarchy, text


def _split_into_sentences(text: str) -> list[str]:
    """Split a paragraph into individual sentences for Satz-level chunking."""
    # Split on ". " followed by a capital letter (German sentence boundary)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÖÜÄ])", text)
    return [s.strip() for s in sentences if s.strip()]


def _infer_law_name(element: Tag, source_type: str) -> str:
    """Derive the law name from surrounding HTML structure or source_type.

    Prefers clean mapped names for known source types; falls back to
    HTML title/h1 extraction for unknown types.
    """
    _LAW_NAME_DEFAULT: dict[str, str] = {
        "sgb2": "SGB II",
        "sgbx": "SGB X",
        "sgb12": "SGB XII",
        "sgb1": "SGB I",
        "sgb3": "SGB III",
        "sgb9": "SGB IX",
        "bgb": "BGB",
        "egbgb": "EGBGB",
        "owig": "OWiG",
        "stvg": "StVG",
        "stvo": "StVO",
        "bkatv": "BKatV",
        "fev": "FeV",
        "famfg": "FamFG",
        "estg": "EStG",
        "ao": "AO",
        "solzg": "SolZG",
        "fgo": "FGO",
        "stberg": "StBerG",
        "aufenthg": "AufenthG",
        "asylg": "AsylG",
        "aufenthv": "AufenthV",
        "beschv": "BeschV",
        "freizuegg_eu": "FreizügG/EU",
        "stag": "StAG",
        "vwgo": "VwGO",
        "uvg": "UhVorschG",
        "minuhv": "MinUhV",
        "stpo": "StPO",
        "kschg": "KSchG",
        "burlg": "BUrlG",
        "tzbfg": "TzBfG",
        "entgfg": "EntgFG",
        "milog": "MiLoG",
        "muschg": "MuSchG",
        "arbzg": "ArbZG",
        "arbgg": "ArbGG",
        "betrkv": "BetrKV",
        "heizkostenv": "HeizkostenV",
        "zpo": "ZPO",
        "inso": "InsO",
        "rdg": "RDG",
        "rvg": "RVG",
        "vwvfg": "VwVfG",
        "sgg": "SGG",
        "weisung": "Fachliche Weisung",
        "bsg": "BSG Urteil",
    }

    # For known source types, prefer the clean default.
    if source_type in _LAW_NAME_DEFAULT:
        return _LAW_NAME_DEFAULT[source_type]

    # Fallback: extract from HTML metadata
    doc = element.find_parent("html") or element
    if isinstance(doc, Tag):
        h1_tag = doc.find("h1")
        if h1_tag and h1_tag.get_text(strip=True):
            # Extract a concise name from the first part of the h1
            return str(h1_tag.get_text(strip=True))

        title_tag = doc.find("title")
        if title_tag and title_tag.get_text(strip=True):
            return str(title_tag.get_text(strip=True))

    return source_type.upper()


def _infer_effective_date(soup: BeautifulSoup) -> date:
    """Extract the effective date from HTML metadata or use today's date."""
    # Check for <meta> tag with date info
    if isinstance(soup, Tag):
        meta = soup.find("meta", attrs={"name": "date"})
        if meta and isinstance(meta, Tag):
            content = meta.get("content", "")
            try:
                return date.fromisoformat(str(content)[:10])
            except ValueError:
                pass

        meta_fundstelle = soup.find("meta", attrs={"name": "fundstelle"})
        if meta_fundstelle and isinstance(meta_fundstelle, Tag):
            fundstelle = str(meta_fundstelle.get("content", ""))
            date_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", fundstelle)
            if date_match:
                try:
                    return date(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                except ValueError:
                    pass

    return date.today()


def _compute_version_hash(text: str) -> str:
    """SHA-256 hex digest of the normalised text for version tracking."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_ocr_artefacts(text: str) -> str:
    """Remove common OCR / HTML artefacts from scraped text."""
    # Replace non-breaking spaces with regular spaces
    text = text.replace("\u00a0", " ")
    # Remove zero-width spaces and soft hyphens
    text = re.sub(r"[\u200B-\u200D\uFEFF\u00AD\u2060\u200C\u200D\u200E\u200F]", "", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Sentence-aware hierarchical splitting (used for fine-grained chunks)
# ---------------------------------------------------------------------------


def build_sentence_level_chunks(
    raw_paragraphs: list[dict[str, Any]],
    *,
    source_type: str,
    title: str,
) -> list[dict[str, Any]]:
    """Take a list of paragraph dicts and split each into Satz-level chunks.

    Each input dict must have at least a ``text`` key.  Optional keys:
    ``paragraph``, ``absatz``.

    Returns enriched chunk dicts with ``unit_type``, ``hierarchy_path``,
    ``text_content``, ``effective_date``, ``source_url``, ``version_hash``.
    """
    chunks: list[dict[str, Any]] = []

    for para in raw_paragraphs:
        raw_text = para.get("text", "")
        if not raw_text or not raw_text.strip():
            continue

        sentences = _split_into_sentences(normalize_text(raw_text))
        if not sentences:
            continue

        para_num = para.get("paragraph", "?")
        absatz_num = para.get("absatz", "")
        effective_date = para.get("effective_date", date.today().isoformat())
        source_url = para.get(
            "source_url", urljoin(_BASE, _SOURCE_TYPE_PREFIX.get(source_type, "/"))
        )

        if len(sentences) == 1:
            # Single-sentence paragraph → one chunk
            hierarchy = _build_hierarchy(title, para_num, absatz_num, "1")
            chunks.append(
                _make_chunk(
                    source_type=source_type,
                    title=title,
                    hierarchy=hierarchy,
                    text=sentences[0],
                    unit_type="satz",
                    effective_date=effective_date,
                    source_url=source_url,
                )
            )
        else:
            # Multi-sentence → one chunk per sentence
            for idx, sentence in enumerate(sentences, start=1):
                hierarchy = _build_hierarchy(title, para_num, absatz_num, str(idx))
                chunks.append(
                    _make_chunk(
                        source_type=source_type,
                        title=title,
                        hierarchy=hierarchy,
                        text=sentence,
                        unit_type="satz",
                        effective_date=effective_date,
                        source_url=source_url,
                    )
                )

    return chunks


def _build_hierarchy(title: str, paragraph: str, absatz: str, satz: str) -> list[str]:
    parts = [title, f"§ {paragraph}"]
    if absatz:
        parts.append(f"Abs. {absatz}")
    parts.append(f"Satz {satz}")
    return parts


def _make_chunk(
    *,
    source_type: str,
    title: str,
    hierarchy: list[str],
    text: str,
    unit_type: str,
    effective_date: str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "source_type": source_type,
        "title": title,
        "unit_type": unit_type,
        "hierarchy_path": " > ".join(hierarchy),
        "text_content": text,
        "effective_date": effective_date,
        "source_url": source_url,
        "version_hash": _compute_version_hash(text),
        "chunk_id": str(uuid4()),
        "legal_area": None,
    }


# ---------------------------------------------------------------------------
# Embedding generation & vector upsert (WP-006)
# ---------------------------------------------------------------------------


async def generate_embeddings(
    chunks: list[dict[str, Any]],
    *,
    client: OpenRouterClient | None = None,
    progress_cb: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """Generate embeddings for each chunk and attach them to the chunk dict.

    Mutates each input dict in-place by adding an ``embedding`` key with a
    ``list[float]`` of length ``settings.VECTOR_DIM``.

    Args:
        chunks: List of chunk dicts produced by ``scrape_and_chunk`` (must
            contain ``text_content`` and ``chunk_id``).
        client: Optional pre-instantiated ``OpenRouterClient``.  A new
            client is created if none is provided.
        progress_cb: Optional async callback ``(done, total) -> None``
            invoked after each embedding batch completes, enabling
            fine-grained progress reporting.

    Returns:
        The same list, now enriched with ``embedding`` keys.
    """
    if not chunks:
        return chunks

    async with client or OpenRouterClient() as router:
        texts = [c["text_content"] for c in chunks]
        embeddings = await router.get_embeddings_batch(texts, progress_cb=progress_cb)

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk["embedding"] = embedding

    logger.info("Generated %d embeddings with model=%s", len(chunks), settings.EMBEDDING_MODEL)
    return chunks


async def upsert_chunks(
    session: AsyncSession,
    chunks: list[dict[str, Any]],
    *,
    progress_cb: Callable[[int, int], Awaitable[None]] | None = None,
) -> None:
    """Persist legal chunks and their embeddings, de-duplicating on ``version_hash``.

    For each chunk dict the function:
    1. Looks up (or creates) a :class:`LegalSource` by
       ``source_type + version_hash``.
    2. Creates a :class:`LegalChunk` under that source, keyed on
       ``hierarchy_path + text_content`` (ON CONFLICT skip).
    3. Upserts a :class:`ChunkEmbedding`` row with ``ON CONFLICT DO UPDATE``
       to refresh the embedding vector when the model or text changes.

    Args:
        session: An active async DB session.
        chunks: List of chunk dicts as returned by ``generate_embeddings``
            (must contain ``embedding``, ``source_type``, ``title``,
            ``hierarchy_path``, ``text_content``, ``effective_date``,
            ``source_url``, ``version_hash``, ``unit_type``).
        progress_cb: Optional async callback ``(done, total) -> None``
            invoked every 25 chunks to report upsert progress.
    """
    total = len(chunks)
    backend = "pgvector"
    logger.info(
        "upsert_chunks started: total=%d, backend=%s, model=%s",
        total,
        backend,
        settings.EMBEDDING_MODEL,
    )
    for i, chunk in enumerate(chunks, 1):
        try:
            source = await _get_or_create_source(session, chunk)
            lc = await _get_or_create_legal_chunk(session, source, chunk)
            await _upsert_embedding(session, lc, chunk)
        except Exception as exc:
            logger.error(
                "upsert_chunks FAILED at chunk %d/%d: source_type=%s, hierarchy_path=%s, "
                "text_content_len=%d, error=%s",
                i,
                total,
                chunk.get("source_type", "?"),
                chunk.get("hierarchy_path", "?"),
                len(chunk.get("text_content", "")),
                exc,
            )
            raise
        if progress_cb and (i % 25 == 0 or i == total):
            await progress_cb(i, total)

    await session.commit()
    logger.info("Upserted %d chunks with embeddings (backend=%s)", total, backend)


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------


async def _get_or_create_source(
    session: AsyncSession,
    chunk: dict[str, Any],
) -> LegalSource:
    """Return an existing LegalSource or create a new one."""
    source_type = chunk["source_type"]
    version_hash = chunk["version_hash"]

    stmt = select(LegalSource).where(
        LegalSource.source_type == source_type,
        LegalSource.version_hash == version_hash,
    )
    result = await session.execute(stmt)
    source = result.scalar_one_or_none()

    if source is None:
        source = LegalSource(
            source_type=source_type,
            title=chunk.get("title", source_type.upper()),
            jurisdiction=chunk.get("jurisdiction", "DE"),
            effective_date=date.fromisoformat(chunk["effective_date"]),
            source_url=chunk.get("source_url", ""),
            version_hash=version_hash,
            is_active=True,
        )
        session.add(source)
        await session.flush()

    return source


async def _get_or_create_legal_chunk(
    session: AsyncSession,
    source: LegalSource,
    chunk: dict[str, Any],
) -> LegalChunk:
    """Return an existing LegalChunk or create a new one."""
    hierarchy_path = chunk["hierarchy_path"]
    text_content = chunk["text_content"]
    text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()

    stmt = select(LegalChunk).where(
        LegalChunk.source_id == source.id,
        LegalChunk.hierarchy_path == hierarchy_path,
        LegalChunk.text_hash == text_hash,
    )
    result = await session.execute(stmt)
    lc = result.scalar_one_or_none()

    if lc is None:
        lc = LegalChunk(
            source_id=source.id,
            unit_type=chunk.get("unit_type", "satz"),
            hierarchy_path=hierarchy_path,
            text_content=text_content,
            text_hash=text_hash,
            effective_date=date.fromisoformat(chunk["effective_date"]),
            legal_area=chunk.get("legal_area"),
        )
        session.add(lc)
        await session.flush()
    elif chunk.get("legal_area") and lc.legal_area != chunk["legal_area"]:
        # Back-fill legal_area for chunks that pre-date the column.
        # Idempotent: subsequent re-corpus runs are no-ops.
        lc.legal_area = chunk["legal_area"]
        await session.flush()

    return lc


async def _upsert_embedding(
    session: AsyncSession,
    legal_chunk: LegalChunk,
    chunk: dict[str, Any],
) -> None:
    """Insert or update a ChunkEmbedding row for the given legal chunk.

    Uses ``ON CONFLICT DO UPDATE`` on ``chunk_id + model_name``
    to atomically upsert the embedding vector. Since D-024 the ORM column is
    pgvector's ``Vector`` type, so the plain dialect insert binds
    ``list[float]`` directly — the former LargeBinary/raw-SQL `::vector`
    cast workaround (D-014) is gone.
    """
    embedding_vec = chunk["embedding"]
    model_name = settings.EMBEDDING_MODEL
    chunk_id_str = str(legal_chunk.id)

    stmt = (
        upsert_insert(ChunkEmbedding)
        .values(
            chunk_id=legal_chunk.id,
            embedding=embedding_vec,
            model_name=model_name,
        )
        .on_conflict_do_update(
            index_elements=["chunk_id", "model_name"],
            set_={"embedding": embedding_vec},
        )
    )
    await session.execute(stmt)
    logger.debug(
        "upsert_embedding (pgvector): chunk_id=%s, model=%s, dim=%d",
        chunk_id_str,
        model_name,
        len(embedding_vec),
    )
