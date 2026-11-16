"""Print-ready PDF export of the dossier (WP-103).

Rendered locally with PyMuPDF's Story engine (HTML/CSS subset → PDF); no
external service, no network. The PDF carries the provenance marker three
ways: a visible footer line on every page, the PDF metadata (``keywords``,
``subject``) and two embedded files — ``dossier.json`` (the full validated
dossier) and ``provenance.json`` (the Art. 50(2) marker) — so the
machine-readable form travels with the printout.

The deadline banner is placed first, before every other section: a
critical deadline must be impossible to miss (roadmap WP-121).
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-103 initial.

from __future__ import annotations

import io
import json
from datetime import UTC, date, datetime
from html import escape
from typing import Any

import fitz  # PyMuPDF

_CSS = """
body { font-family: sans-serif; font-size: 9.5pt; line-height: 1.35; }
h1 { font-size: 17pt; margin: 0 0 4pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 4pt 0; border-bottom: 1px solid #555; }
h3 { font-size: 10.5pt; margin: 8pt 0 2pt 0; }
p { margin: 2pt 0 4pt 0; }
.meta { color: #333; font-size: 8.5pt; }
.notice { border: 1px solid #777; background-color: #f2f2f2; padding: 5pt; }
.banner { border: 2px solid #a00000; background-color: #fff0f0; padding: 6pt; }
.banner-ok { border: 1px solid #555; background-color: #f6f6f6; padding: 6pt; }
.warn { color: #a00000; }
.small { font-size: 8pt; color: #333; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #999; padding: 2pt 3pt; vertical-align: top; font-size: 8.5pt; }
th { background-color: #e6e6e6; text-align: left; }
pre { font-family: monospace; font-size: 8pt; white-space: pre-wrap; }
"""

_STATUS_DE = {
    "proposed": "unbestätigt",
    "confirmed": "bestätigt",
    "user_added": "ergänzt",
    "computed": "berechnet",
    "provisional": "VORLÄUFIG",
    "not_applicable": "nicht anwendbar",
    "missing_input": "NICHT BERECHNET",
}


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))


def _de_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _de_timestamp(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso).astimezone(UTC)
    except ValueError:
        return iso
    return moment.strftime("%d.%m.%Y, %H:%M UTC")


def _eur(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _e(value)
    text = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


def _deadline_banner(section: dict[str, Any]) -> str:
    items = section["items"]
    if not items:
        return (
            '<div class="banner-ok"><b>Fristen:</b> Für die Rechtsgebiete dieses Falls '
            "sind keine Fristen hinterlegt. Klären Sie Fristen im Termin.</div>"
        )
    rows = []
    for item in items:
        status = _STATUS_DE.get(item["status"], item["status"])
        if item["frist_ende"]:
            when = f"<b>{_de_date(item['frist_ende'])}</b>"
            if item.get("oq1_alternate_ende"):
                when += (
                    f"<br/><span class='small'>Alternativ (bürgerfreundliche Lesart): "
                    f"{_de_date(item['oq1_alternate_ende'])}</span>"
                )
        elif item["status"] == "not_applicable":
            when = "keine Frist (siehe Erläuterung)"
        else:
            when = "<b class='warn'>nicht berechnet</b>"
        rows.append(
            f"<tr><td>{_e(item['label_de'])}<br/><span class='small'>{_e(item['basis'])}"
            f"</span></td><td>{when}</td><td>{_e(status)}</td></tr>"
        )
    assumptions = sorted({a for item in items for a in item["assumptions"]})
    notes = "".join(f"<li>{_e(a)}</li>" for a in assumptions)
    return (
        '<div class="banner"><h3>Fristen — bitte zuerst lesen</h3>'
        "<table><tr><th>Frist</th><th>Fristende</th><th>Status</th></tr>"
        + "".join(rows)
        + "</table>"
        + (f"<p class='small'><b>Annahmen:</b></p><ul class='small'>{notes}</ul>" if notes else "")
        + "<p class='small'>Fristen werden regelbasiert berechnet, nicht von der KI. "
        "Sie hängen von den Angaben in der Chronologie ab. Im Zweifel: rechtzeitig "
        "handeln und die Frist im Termin bestätigen lassen.</p></div>"
    )


def _chronology(section: dict[str, Any]) -> str:
    entries = section["entries"]
    if not entries:
        return "<p>Keine datierten Ereignisse gefunden.</p>"
    rows = "".join(
        f"<tr><td>{_de_date(e['date'])}</td><td>{_e(e['label_de'])}"
        + (f"<br/><span class='small'>{_e(e['source']['excerpt'])}</span>" if e["source"] else "")
        + (f"<br/><span class='small'>Notiz: {_e(e['note'])}</span>" if e.get("note") else "")
        + f"</td><td>{_e(_STATUS_DE.get(e['status'], e['status']))}</td></tr>"
        for e in entries
    )
    counts = section["counts"]
    return (
        "<table><tr><th>Datum</th><th>Ereignis</th><th>Status</th></tr>"
        + rows
        + "</table>"
        + f"<p class='small'>{counts['confirmed']} bestätigt, {counts['user_added']} ergänzt, "
        f"{counts['proposed']} unbestätigt, {counts['rejected']} verworfen.</p>"
    )


def _checklist(section: dict[str, Any]) -> str:
    items = section["items"]
    if not items:
        return "<p>Keine Checkliste verfügbar.</p>"
    rows = "".join(
        f"<tr><td>☐</td><td>{_e(i['label_de'])}"
        + (f"<br/><span class='small'>{_e(i['why_de'])}</span>" if i["why_de"] else "")
        + f"</td><td>{'ja' if i['required'] else 'falls vorhanden'}</td></tr>"
        for i in items
    )
    return "<table><tr><th></th><th>Unterlage</th><th>Wichtig</th></tr>" + rows + "</table>"


def _calculations(section: dict[str, Any]) -> str:
    if section["status"] == "none":
        return "<p>Keine regelbasierte Berechnungsprüfung vorhanden.</p>"
    parts = []
    summary = section["summary"]
    if summary:
        parts.append(
            f"<p>Abweichungen: <b>{summary['total_discrepancies']}</b>, "
            f"Summe: <b>{_eur(summary['total_amount_eur'])}</b>"
            + (f" ({_e(summary['direction'])})" if summary.get("direction") else "")
            + "</p>"
        )
    if section["items"]:
        rows = "".join(
            f"<tr><td>{_e(i['label'])}<br/><span class='small'>{_e(i['relevant_rule'])}</span>"
            f"</td><td>{_e(json.dumps(i['authority_values'], ensure_ascii=False))}</td>"
            f"<td>{_e(i['deterministic_result'])}<br/><span class='small'>"
            f"{_e(i['computation_detail'])}</span></td>"
            f"<td>{_eur(i['discrepancy_amount_eur']) if i['discrepancy_found'] else '—'}</td></tr>"
            for i in section["items"]
        )
        parts.append(
            "<table><tr><th>Posten</th><th>Laut Schreiben</th><th>Regelbasiert</th>"
            "<th>Abweichung</th></tr>" + rows + "</table>"
        )
    else:
        parts.append("<p class='small'>Nur die Zusammenfassung wurde gespeichert.</p>")
    return "".join(parts)


def _evidence(section: dict[str, Any]) -> str:
    items = section["items"]
    if not items:
        return "<p>Keine Aussagen vorhanden.</p>"
    blocks = []
    for item in items:
        adjudication = item["user_adjudication"] or {}
        mark = {"agreed": " — von Ihnen bestätigt", "disputed": " — von Ihnen bestritten"}.get(
            str(adjudication.get("status")), ""
        )
        quotes = "".join(
            f"<li>„{_e(b['quote_excerpt'])}“"
            + (f" <span class='small'>({_e(b['source'])})</span>" if b["source"] else "")
            + "</li>"
            for b in item["bindings"]
        )
        blocks.append(
            f"<p><b>{_e(item['claim_text'])}</b><br/><span class='small'>"
            f"Prüfstatus: {_e(item['verification'])}, Konfidenz "
            f"{item['confidence_score']:.2f}{_e(mark)}</span></p>"
            + (f"<ul class='small'>{quotes}</ul>" if quotes else "")
        )
    return "".join(blocks)


def _questions(section: dict[str, Any]) -> str:
    items = section["items"]
    if not items:
        return "<p>Keine Fragen hinterlegt.</p>"
    return "<ol>" + "".join(f"<li>{_e(q['text_de'])}</li>" for q in items) + "</ol>"


def _drafts(section: dict[str, Any]) -> str:
    items = section["items"]
    if not items:
        return "<p>Kein Entwurf beigefügt.</p>"
    return "".join(
        f"<h3>{_e(d['title'])}</h3><p class='small'>Entwurf — Stellen mit [BITTE PRÜFEN] "
        f"sind offen ({d['review_slots']}). Sie entscheiden, ob und was Sie einreichen.</p>"
        f"<pre>{_e(d['rendered_text'])}</pre>"
        for d in items
    )


def render_html(dossier: dict[str, Any]) -> str:
    case = dossier["case"]
    sections = dossier["sections"]
    modules = ", ".join(f"{m['title_de']} ({m['id']} {m['version']})" for m in case["modules"])
    warnings = "".join(f"<li class='warn'>{_e(w)}</li>" for w in dossier["warnings"])
    return (
        "<h1>Mandatsvorbereitungs-Dossier</h1>"
        f"<p class='meta'>Fall: {_e(case['title'] or case['case_id'])}<br/>"
        f"Rechtsgebiete: {_e(modules)}<br/>"
        f"Erstellt: {_e(_de_timestamp(dossier['generated_at']))} · "
        f"Revision {dossier['revision']} · "
        f"Schema {_e(dossier['schema_version'])}</p>"
        f"<div class='notice'>{_e(dossier['notice']['de'])}</div>"
        + _deadline_banner(sections["deadlines"])
        + (f"<ul>{warnings}</ul>" if warnings else "")
        + "<h2>1. Chronologie des Sachverhalts</h2>"
        + _chronology(sections["chronology"])
        + "<h2>2. Checkliste: Unterlagen zum Termin mitbringen</h2>"
        + _checklist(sections["document_checklist"])
        + "<h2>3. Fristen (Erläuterung)</h2>"
        + "".join(
            f"<p><b>{_e(i['label_de'])}:</b> {_e(i['explanation_de'] or 'nicht berechnet')}</p>"
            for i in sections["deadlines"]["items"]
        )
        + "<h2>4. Rechnerische Ergebnisse</h2>"
        + _calculations(sections["calculations"])
        + "<h2>5. Aussagen der Analyse mit Belegen (KI-erstellt)</h2>"
        + _evidence(sections["evidence"])
        + "<h2>6. Fragen für den Termin</h2>"
        + _questions(sections["questions"])
        + "<h2>7. Anhang: Entwürfe</h2>"
        + _drafts(sections["drafts"])
        + "<h2>8. Maschinenlesbare Fassung</h2>"
        "<p class='small'>Diese PDF-Datei enthält als Anhang die vollständige JSON-Fassung "
        "(dossier.json) und den Herkunftsnachweis (provenance.json).</p>"
    )


def _footer(provenance: dict[str, Any]) -> str:
    modules = ",".join(f"{m.get('id')}@{m.get('version')}" for m in provenance.get("modules", []))
    return (
        f"KI-gestützt erstellt (Art. 50 VO (EU) 2024/1689) · {provenance.get('generator')} "
        f"{provenance.get('app_version')} · {provenance.get('spec_version')} · {modules}"
    )


def render_pdf(dossier: dict[str, Any]) -> bytes:
    """Render *dossier* (schema-valid) to PDF bytes."""
    story = fitz.Story(html=render_html(dossier), user_css=_CSS)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    mediabox = fitz.paper_rect("a4")
    # Margins: 50 pt left/top/right, 60 pt bottom (room for the footer).
    where = fitz.Rect(mediabox.x0 + 50, mediabox.y0 + 50, mediabox.x1 - 50, mediabox.y1 - 60)
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()

    doc = fitz.open(stream=buffer.getvalue(), filetype="pdf")
    provenance = dossier["provenance"]
    footer = _footer(provenance)
    for number, page in enumerate(doc, start=1):
        page.insert_text(
            (50, mediabox.height - 35), footer, fontsize=6.5, fontname="helv", color=(0.3, 0.3, 0.3)
        )
        page.insert_text(
            (mediabox.width - 95, mediabox.height - 35),
            f"Seite {number}/{doc.page_count}",
            fontsize=6.5,
            fontname="helv",
        )
    doc.set_metadata(
        {
            "title": "Mandatsvorbereitungs-Dossier",
            "subject": f"{dossier['schema_version']} case {dossier['case']['case_id']}",
            "keywords": json.dumps(provenance, ensure_ascii=False, sort_keys=True),
            "creator": f"citizen {provenance.get('app_version')}",
            "producer": "citizen dossier renderer 1.0.0 (PyMuPDF)",
        }
    )
    doc.embfile_add(
        "dossier.json",
        json.dumps(dossier, ensure_ascii=False, indent=2).encode("utf-8"),
        filename="dossier.json",
        desc=dossier["schema_version"],
    )
    doc.embfile_add(
        "provenance.json",
        json.dumps(provenance, ensure_ascii=False, indent=2).encode("utf-8"),
        filename="provenance.json",
        desc=str(provenance.get("spec_version")),
    )
    data: bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data
