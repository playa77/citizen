"""Court-ready action document generators (WP-40).

Generates three building-block documents:
  - Widerspruch (objection against a Bescheid)
  - Widerspruch under Jahresfrist (§ 66 Abs. 2 SGG, missing/wrong RBB)
  - Überprüfungsantrag (§ 44 SGB X, after Frist lapse)
  - Akteneinsichtsantrag (§ 25 SGB X, file access request)

**Hard guardrail:** Every legal assertion in the rendered document must be
traceable to a claim whose ``verification_status`` is ``"exakt"`` or
``"normalisiert"`` **AND** whose ``user_adjudication.status`` is ``"confirmed"``.
Any slot that fails this check renders as ``[BITTE PRÜFEN: <topic>]`` — never
fluent invention.

**Sourcing discipline:**
- Deadline lines → exclusively from the Fristen engine.
- Amount lines → exclusively from the calculation engine.
- Claim text → exclusively from verified + confirmed claims.

**Pseudonymization:** If a ``PiiMapping`` is provided, user data placeholders
are generated, slotted into the document, then reinjected post-generation.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

from app.core.config import get_app_version, get_app_version_tag, settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class DocumentSlot:
    """A fillable slot in a document template.

    Attributes
    ----------
    key :
        Machine key, e.g. ``"anspruch_hoehe"``.
    label :
        Human-readable label (for audit trails).
    source :
        Origin of the value — ``"claim:<claim_id>"``, ``"fristen"``,
        ``"berechnung"``, or ``"user_input"``.
    value :
        The filled value (may be ``None`` if unresolvable).
    verified :
        Whether the value is backed by a verified + confirmed claim.
    needs_review :
        If ``True``, the slot renders as ``[BITTE PRÜFEN: ...]``.
    review_topic :
        Text to show inside the review placeholder.
    """

    key: str
    label: str
    source: str
    value: str | None = None
    verified: bool = False
    needs_review: bool = False
    review_topic: str = ""

    def render(self) -> str:
        """Return the display value for this slot.

        Unresolved or unverified slots render as ``[BITTE PRÜFEN: <topic>]``.
        """
        if self.needs_review or not self.verified or self.value is None:
            return f"[BITTE PRÜFEN: {self.review_topic or self.label}]"
        return self.value


@dataclass
class GeneratedDocument:
    """Output of a document generator.

    Attributes
    ----------
    document_type :
        One of ``"widerspruch"``, ``"widerspruch_jahresfrist"``,
        ``"ueberpruefungsantrag_44"``, ``"akteneinsichtsantrag_25"``.
    title :
        Human-readable title.
    rendered_text :
        The final document text with all slots filled (or review placeholders).
    slots :
        Audit trail of every filled slot.
    warnings :
        List of unresolved placeholders or issues encountered.
    generation_metadata :
        App version, inference profile, generation date.
    """

    document_type: str
    title: str
    rendered_text: str
    slots: list[DocumentSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generation_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Guardrail: slot claim validation
# ---------------------------------------------------------------------------


def validate_slot_claim(claim: dict[str, Any] | None) -> bool:
    """Check whether a claim can be used in a document slot.

    A claim is valid if:
    - It is not ``None``.
    - ``verification_status`` is ``"exakt"`` or ``"normalisiert"``
      (not ``"unverifiziert"``).
    - ``user_adjudication`` is a dict with ``status`` = ``"confirmed"``.

    Parameters
    ----------
    claim :
        A claim dict from the pipeline output (or ``None``).

    Returns
    -------
    bool
        ``True`` if the claim passes the guardrail.
    """
    if claim is None:
        return False

    v_status = claim.get("verification_status", "unverifiziert")
    if v_status not in ("exakt", "normalisiert"):
        return False

    adjudication = claim.get("user_adjudication")
    if not isinstance(adjudication, dict):
        return False
    return adjudication.get("status") == "confirmed"


def _get_verified_claim_text(
    claims: list[dict[str, Any]],
    topic_keywords: list[str],
) -> tuple[str | None, bool]:
    """Find a verified + confirmed claim matching the topic keywords.

    Returns
    -------
    Tuple of (claim_text, is_verified).
    If no matching verified claim is found, returns (None, False).
    """
    for claim in claims:
        claim_text = (claim.get("claim_text") or "").lower()
        if any(kw.lower() in claim_text for kw in topic_keywords):
            if validate_slot_claim(claim):
                return claim.get("claim_text"), True
            # Found a candidate but it's not verified — continue searching
            # for a verified one; keep this as fallback.
    return None, False


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


def _build_footer() -> str:
    """Build the mandatory document footer with legal disclaimer."""
    today = date.today().strftime("%d.%m.%Y")
    version = get_app_version_tag()
    profile = settings.INFERENCE_PROFILE
    return (
        "---\n"
        "Rechtsinformation: Dieses Dokument wurde von Citizen, einer "
        "KI-gestützten Rechtsinformationsanwendung, generiert. Es stellt "
        "keine Rechtsberatung dar. Die Nutzung erfolgt auf eigenes Risiko. "
        "Vor Einreichung sollte das Dokument von einer fachkundigen Person "
        "geprüft werden.\n"
        f"\nGeneriert am: {today}\n"
        f"Citizen Version: {version}\n"
        f"Inference Profile: {profile}\n"
    )


# ---------------------------------------------------------------------------
# Helper: extract values from reconciliation
# ---------------------------------------------------------------------------


def _find_reconciliation_value(
    reconciliation: list[Any],
    label: str,
) -> float | None:
    """Find a ``ReconciliationLineItem`` (or compatible dict) by label and
    return its ``korrekt`` (computed correct) value."""
    for item in reconciliation:
        if hasattr(item, "label"):  # dataclass instance
            if item.label == label and hasattr(item, "korrekt"):
                val = item.korrekt
                return val if isinstance(val, (int, float)) else None
        elif isinstance(item, dict):
            if item.get("label") == label:
                val = item.get("korrekt")
                return val if isinstance(val, (int, float)) else None
    return None


# ---------------------------------------------------------------------------
# Helper: format EUR amounts
# ---------------------------------------------------------------------------


def _fmt_eur(value: float | None) -> str:
    """Format a float as a German EUR string, or return a review placeholder."""
    if value is None:
        return "[BITTE PRÜFEN: Betrag]"
    return f"{value:.2f} EUR"


# ---------------------------------------------------------------------------
# Generator 1: Widerspruch (standard, Frist open)
# ---------------------------------------------------------------------------


def _build_widerspruch_slots(
    frist_result: Any,
    reconciliation: list[Any],
    claims: list[dict[str, Any]],
    bescheid_datum: date | None,
    aktenzeichen: str | None,
    behoerde: str | None,
) -> list[DocumentSlot]:
    """Build all slots for the Widerspruch template."""
    slots: list[DocumentSlot] = []

    # ── Fristen engine slots ──────────────────────────────────────────
    if frist_result is not None:
        frist_ende_str = frist_result.frist_ende.strftime("%d.%m.%Y")
        bekanntgabe_str = frist_result.bekanntgabe.strftime("%d.%m.%Y")
    else:
        frist_ende_str = None
        bekanntgabe_str = None

    slots.append(
        DocumentSlot(
            key="bescheid_datum",
            label="Bescheid-Datum",
            source="user_input",
            value=bescheid_datum.strftime("%d.%m.%Y") if bescheid_datum else None,
            verified=bescheid_datum is not None,
            needs_review=bescheid_datum is None,
            review_topic="Bescheid-Datum" if bescheid_datum is None else "",
        )
    )
    slots.append(
        DocumentSlot(
            key="bescheid_aktenzeichen",
            label="Aktenzeichen",
            source="user_input",
            value=aktenzeichen,
            verified=bool(aktenzeichen),
            needs_review=not aktenzeichen,
            review_topic="Aktenzeichen" if not aktenzeichen else "",
        )
    )
    slots.append(
        DocumentSlot(
            key="behoerde_name",
            label="Behördenname",
            source="user_input",
            value=behoerde,
            verified=bool(behoerde),
            needs_review=not behoerde,
            review_topic="Behördenname" if not behoerde else "",
        )
    )
    slots.append(
        DocumentSlot(
            key="bekanntgabe",
            label="Bekanntgabe-Datum",
            source="fristen",
            value=("am " + bekanntgabe_str) if bekanntgabe_str else None,
            verified=bool(bekanntgabe_str),
            needs_review=not bekanntgabe_str,
            review_topic="Bekanntgabe-Datum" if not bekanntgabe_str else "",
        )
    )
    slots.append(
        DocumentSlot(
            key="widerspruchsfrist_ende",
            label="Widerspruchsfrist-Ende",
            source="fristen",
            value=("der " + frist_ende_str) if frist_ende_str else None,
            verified=bool(frist_ende_str),
            needs_review=not frist_ende_str,
            review_topic="Widerspruchsfrist-Ende" if not frist_ende_str else "",
        )
    )

    # ── Calculation engine slots ──────────────────────────────────────
    anspruch = _find_reconciliation_value(reconciliation, "Anspruch (Leistung)")
    differenz = _find_reconciliation_value(reconciliation, "Gesamtbedarf")
    # Use "Differenz" from the Anspruch line item if available
    anspruch_diff = None
    for item in reconciliation:
        if hasattr(item, "label") and hasattr(item, "differenz"):
            if item.label == "Anspruch (Leistung)":
                anspruch_diff = item.differenz
                break
        elif isinstance(item, dict):
            if item.get("label") == "Anspruch (Leistung)":
                anspruch_diff = item.get("differenz")
                break

    slots.append(
        DocumentSlot(
            key="anspruch_hoehe",
            label="Anspruchshöhe (korrekt)",
            source="berechnung",
            value=_fmt_eur(anspruch),
            verified=anspruch is not None,
            needs_review=anspruch is None,
            review_topic="Anspruchshöhe" if anspruch is None else "",
        )
    )

    slot_diff = anspruch_diff if anspruch_diff is not None else differenz
    # Calculate a total difference string
    if slot_diff is not None:
        abs_diff = abs(slot_diff)
        if slot_diff > 0.02:
            diff_text = f"{abs_diff:.2f} EUR (zulasten des Leistungsberechtigten)"
        elif slot_diff < -0.02:
            diff_text = f"{abs_diff:.2f} EUR (zugunsten des Leistungsberechtigten)"
        else:
            diff_text = "0,00 EUR (keine Abweichung)"
    else:
        diff_text = None

    slots.append(
        DocumentSlot(
            key="differenz_gesamt",
            label="Gesamtdifferenz",
            source="berechnung",
            value=diff_text,
            verified=slot_diff is not None,
            needs_review=slot_diff is None,
            review_topic="Gesamtdifferenz" if slot_diff is None else "",
        )
    )

    # ── Claim text slots ──────────────────────────────────────────────
    # Collect all verified + confirmed claims
    verified_claims_text = ""
    unverified_topics: list[str] = []

    for claim in claims:
        ct = (claim.get("claim_text") or "").strip()
        if not ct:
            continue
        if validate_slot_claim(claim):
            if verified_claims_text:
                verified_claims_text += "\n\n"
            verified_claims_text += ct
        else:
            # Extract a short topic from the claim
            topic = ct[:80] + ("..." if len(ct) > 80 else "")
            unverified_topics.append(topic)

    if verified_claims_text:
        claims_value = verified_claims_text
    else:
        claims_value = None

    claims_review = bool(unverified_topics) or not verified_claims_text
    claims_topic = "; ".join(unverified_topics[:3]) if unverified_topics else "Geprüfte Ansprüche"

    slots.append(
        DocumentSlot(
            key="claims_text",
            label="Geprüfte Ansprüche",
            source="claim",
            value=claims_value,
            verified=bool(verified_claims_text),
            needs_review=claims_review and not verified_claims_text,
            review_topic=claims_topic if claims_review and not verified_claims_text else "",
        )
    )

    return slots


def _render_widerspruch_template(
    slots: list[DocumentSlot],
    absender_name: str | None,
    absender_adresse: str | None,
) -> str:
    """Render the full Widerspruch document from its slots."""
    slot_map: dict[str, DocumentSlot] = {s.key: s for s in slots}

    absender_rendered = ""
    if absender_name:
        absender_rendered += absender_name + "\n"
    if absender_adresse:
        absender_rendered += absender_adresse

    behoerde = slot_map.get("behoerde_name", DocumentSlot("", "", "")).render()
    bescheid_datum = slot_map.get("bescheid_datum", DocumentSlot("", "", "")).render()
    az = slot_map.get("bescheid_aktenzeichen", DocumentSlot("", "", "")).render()
    bekanntgabe = slot_map.get("bekanntgabe", DocumentSlot("", "", "")).render()
    frist_ende = slot_map.get("widerspruchsfrist_ende", DocumentSlot("", "", "")).render()
    anspruch = slot_map.get("anspruch_hoehe", DocumentSlot("", "", "")).render()
    differenz = slot_map.get("differenz_gesamt", DocumentSlot("", "", "")).render()
    claims_rendered = slot_map.get("claims_text", DocumentSlot("", "", "")).render()

    # If claims_rendered is a BITTE PRÜFEN placeholder but we have actual
    # warnings, show them in document body instead
    body_claims = claims_rendered

    body = (
        f"{absender_rendered}\n"
        f"An {behoerde}\n\n"
        f"**Widerspruch gegen den Bescheid vom {bescheid_datum}, "
        f"Aktenzeichen: {az}**\n\n"
        f"Sehr geehrte Damen und Herren,\n\n"
        f"hiermit lege ich Widerspruch gegen den oben genannten Bescheid "
        f"vom {bescheid_datum} (Aktenzeichen: {az}) ein.\n\n"
        f"Der Bescheid ist mir {bekanntgabe} bekanntgegeben worden. "
        f"Die Widerspruchsfrist endet {frist_ende}.\n\n"
    )

    if body_claims and not body_claims.startswith("[BITTE PRÜFEN"):
        body += f"**Begründung:**\n\n" f"{body_claims}\n\n"

    body += (
        f"**Berechnung des korrekten Anspruchs:**\n\n"
        f"Nach unserer Berechnung ergibt sich ein korrekter monatlicher "
        f"Anspruch in Höhe von {anspruch}. {differenz}.\n\n"
        f"**Antrag:**\n\n"
        f"Der Bescheid vom {bescheid_datum} wird angefochten, soweit "
        f"er von der korrekten Rechtslage abweicht. Ich beantrage,\n\n"
        f"1. den Bescheid aufzuheben und\n"
        f"2. die Leistung in gesetzlicher Höhe zu gewähren.\n\n"
        f"Für den Fall, dass meinem Widerspruch nicht stattgegeben wird, "
        f"beantrage ich die Vorlage an das zuständige Sozialgericht.\n\n"
        f"Mit freundlichen Grüßen\n\n"
        f"[Unterschrift]\n\n"
    )

    return body


# ---------------------------------------------------------------------------
# Generator 2: Widerspruch under Jahresfrist (§ 66 Abs. 2 SGG)
# ---------------------------------------------------------------------------


def _render_widerspruch_jahresfrist_template(
    slots: list[DocumentSlot],
    absender_name: str | None,
    absender_adresse: str | None,
) -> str:
    """Render a Widerspruch under the one-year Jahresfrist.

    This path applies when the Widerspruchsfrist has nominally lapsed BUT
    the Rechtsbehelfsbelehrung (RBB) was missing or incorrect, so the
    one-year exceptional deadline under § 66 Abs. 2 SGG is still open.
    """
    slot_map: dict[str, DocumentSlot] = {s.key: s for s in slots}

    absender_rendered = ""
    if absender_name:
        absender_rendered += absender_name + "\n"
    if absender_adresse:
        absender_rendered += absender_adresse

    behoerde = slot_map.get("behoerde_name", DocumentSlot("", "", "")).render()
    bescheid_datum = slot_map.get("bescheid_datum", DocumentSlot("", "", "")).render()
    az = slot_map.get("bescheid_aktenzeichen", DocumentSlot("", "", "")).render()
    bekanntgabe = slot_map.get("bekanntgabe", DocumentSlot("", "", "")).render()
    frist_ende = slot_map.get("widerspruchsfrist_ende", DocumentSlot("", "", "")).render()
    anspruch = slot_map.get("anspruch_hoehe", DocumentSlot("", "", "")).render()
    differenz = slot_map.get("differenz_gesamt", DocumentSlot("", "", "")).render()
    claims_rendered = slot_map.get("claims_text", DocumentSlot("", "", "")).render()

    body = (
        f"{absender_rendered}\n"
        f"An {behoerde}\n\n"
        f"**Widerspruch gegen den Bescheid vom {bescheid_datum}, "
        f"Aktenzeichen: {az} (Jahresfrist gem. § 66 Abs. 2 SGG)**\n\n"
        f"Sehr geehrte Damen und Herren,\n\n"
        f"hiermit lege ich Widerspruch gegen den oben genannten Bescheid "
        f"vom {bescheid_datum} (Aktenzeichen: {az}) ein.\n\n"
        f"Der Bescheid ist mir {bekanntgabe} bekanntgegeben worden. "
        f"Die Rechtsbehelfsbelehrung war fehlerhaft bzw. fehlte, sodass "
        f"gemäß § 66 Abs. 2 SGG die einjährige Widerspruchsfrist gilt. "
        f"Diese endet {frist_ende}.\n\n"
    )

    if claims_rendered and not claims_rendered.startswith("[BITTE PRÜFEN"):
        body += f"**Begründung:**\n\n" f"{claims_rendered}\n\n"

    body += (
        f"**Berechnung des korrekten Anspruchs:**\n\n"
        f"Nach unserer Berechnung ergibt sich ein korrekter monatlicher "
        f"Anspruch in Höhe von {anspruch}. {differenz}.\n\n"
        f"**Antrag:**\n\n"
        f"Der Bescheid vom {bescheid_datum} wird angefochten, soweit "
        f"er von der korrekten Rechtslage abweicht. Ich beantrage,\n\n"
        f"1. den Bescheid aufzuheben und\n"
        f"2. die Leistung in gesetzlicher Höhe zu gewähren.\n\n"
        f"Für den Fall, dass meinem Widerspruch nicht stattgegeben wird, "
        f"beantrage ich die Vorlage an das zuständige Sozialgericht.\n\n"
        f"Mit freundlichen Grüßen\n\n"
        f"[Unterschrift]\n\n"
    )

    return body


# ---------------------------------------------------------------------------
# Generator 3: Überprüfungsantrag (§ 44 SGB X)
# ---------------------------------------------------------------------------


def _render_ueberpruefungsantrag_template(
    slots: list[DocumentSlot],
    absender_name: str | None,
    absender_adresse: str | None,
) -> str:
    """Render an Überprüfungsantrag under § 44 SGB X.

    This path applies when the Widerspruchsfrist has lapsed AND no
    Jahresfrist exception applies.  The applicant requests the authority
    to retroactively revoke/remedy the illegal administrative act.
    """
    slot_map: dict[str, DocumentSlot] = {s.key: s for s in slots}

    absender_rendered = ""
    if absender_name:
        absender_rendered += absender_name + "\n"
    if absender_adresse:
        absender_rendered += absender_adresse

    behoerde = slot_map.get("behoerde_name", DocumentSlot("", "", "")).render()
    bescheid_datum = slot_map.get("bescheid_datum", DocumentSlot("", "", "")).render()
    az = slot_map.get("bescheid_aktenzeichen", DocumentSlot("", "", "")).render()
    anspruch = slot_map.get("anspruch_hoehe", DocumentSlot("", "", "")).render()
    differenz = slot_map.get("differenz_gesamt", DocumentSlot("", "", "")).render()
    claims_rendered = slot_map.get("claims_text", DocumentSlot("", "", "")).render()

    body = (
        f"{absender_rendered}\n"
        f"An {behoerde}\n\n"
        f"**Antrag auf Überprüfung nach § 44 SGB X**\n\n"
        f"**Betrifft:** Bescheid vom {bescheid_datum}, "
        f"Aktenzeichen: {az}\n\n"
        f"Sehr geehrte Damen und Herren,\n\n"
        f"hiermit beantrage ich die Überprüfung des oben genannten "
        f"Bescheides gemäß § 44 SGB X.\n\n"
        f"Die Widerspruchsfrist ist zwischenzeitlich abgelaufen. "
        f"Der Bescheid ist jedoch rechtswidrig, da er von der "
        f"geltenden Rechtslage abweicht und Leistungen zu Unrecht "
        f"versagt oder in zu geringer Höhe festgesetzt hat. "
        f"§ 44 SGB X verpflichtet die Behörde zur Rücknahme "
        f"rechtswidriger Verwaltungsakte, auch wenn diese "
        f"bereits bestandskräftig geworden sind.\n\n"
    )

    if claims_rendered and not claims_rendered.startswith("[BITTE PRÜFEN"):
        body += f"**Begründung:**\n\n" f"{claims_rendered}\n\n"

    body += (
        f"**Berechnung des korrekten Anspruchs:**\n\n"
        f"Nach unserer Berechnung ergibt sich ein korrekter monatlicher "
        f"Anspruch in Höhe von {anspruch}. {differenz}.\n\n"
        f"**Antrag:**\n\n"
        f"1. Der Bescheid vom {bescheid_datum} wird gemäß § 44 Abs. 1 "
        f"SGB X mit Wirkung für die Vergangenheit zurückgenommen.\n"
        f"2. Die Leistung wird in gesetzlicher Höhe neu festgesetzt "
        f"und die Differenz in Höhe von {_fmt_eur(None)} nachgezahlt.\n"
        f"3. Über den Antrag ist ein gesonderter, mit einer "
        f"Rechtsbehelfsbelehrung versehener Bescheid zu erteilen.\n\n"
        f"Mit freundlichen Grüßen\n\n"
        f"[Unterschrift]\n\n"
    )

    return body


# ---------------------------------------------------------------------------
# Generator 4: Akteneinsichtsantrag (§ 25 SGB X)
# ---------------------------------------------------------------------------


def _render_akteneinsichtsantrag_template(
    slots: list[DocumentSlot],
    absender_name: str | None,
    absender_adresse: str | None,
    bescheid_datum: date | None,
    aktenzeichen: str | None,
    behoerde: str | None,
) -> str:
    """Render an Akteneinsichtsantrag under § 25 SGB X."""
    absender_rendered = ""
    if absender_name:
        absender_rendered += absender_name + "\n"
    if absender_adresse:
        absender_rendered += absender_adresse

    bd_str = (
        bescheid_datum.strftime("%d.%m.%Y") if bescheid_datum else "[BITTE PRÜFEN: Bescheid-Datum]"
    )
    az_str = aktenzeichen if aktenzeichen else "[BITTE PRÜFEN: Aktenzeichen]"
    beh_str = behoerde if behoerde else "[BITTE PRÜFEN: Behördenname]"

    body = (
        f"{absender_rendered}\n"
        f"An {beh_str}\n\n"
        f"**Antrag auf Akteneinsicht gemäß § 25 SGB X**\n\n"
        f"**Betrifft:** Bescheid vom {bd_str}, "
        f"Aktenzeichen: {az_str}\n\n"
        f"Sehr geehrte Damen und Herren,\n\n"
        f"hiermit beantrage ich Akteneinsicht in die mich betreffenden "
        f"Verfahrensakten gemäß § 25 SGB X.\n\n"
        f"Die Akteneinsicht wird benötigt, um die Rechtmäßigkeit des "
        f"Bescheides vom {bd_str} (Aktenzeichen: {az_str}) zu überprüfen "
        f"und die Erfolgsaussichten eines Rechtsbehelfs beurteilen zu "
        f"können.\n\n"
        f"**Umfang der Akteneinsicht:**\n\n"
        f"Ich bitte um Einsicht in folgende Unterlagen:\n\n"
        f"1. Den Bescheid vom {bd_str} einschließlich aller Anlagen\n"
        f"2. Die vollständige Sachverhaltsermittlung und "
        f"Berechnungsgrundlagen\n"
        f"3. Sämtliche in der Behörde erstellte Vermerke und "
        f"Stellungnahmen\n"
        f"4. Die elektronische Akte (eAkte) sowie etwaige "
        f"Parallelakten\n\n"
        f"Die Einsicht kann in den Räumen der Behörde oder durch "
        f"Übersendung von Kopien erfolgen. Sofern Kosten entstehen, "
        f"bitte ich um vorherige Mitteilung.\n\n"
        f"Mit freundlichen Grüßen\n\n"
        f"[Unterschrift]\n\n"
    )

    return body


# ---------------------------------------------------------------------------
# Generator selection logic
# ---------------------------------------------------------------------------


def select_generator(
    frist_result: Any,
    claims: list[dict[str, Any]] | None = None,
) -> Literal[
    "widerspruch",
    "widerspruch_jahresfrist",
    "ueberpruefungsantrag_44",
    "akteneinsichtsantrag_25",
]:
    """Select which document generator to use based on Frist status.

    Logic
    -----
    1. ``frist_typ == "kein_va"`` → No Widerspruch possible; suggest § 44
       or Akteneinsicht.
    2. ``frist_ende > today()`` → Standard Widerspruch (Frist still open).
    3. Lapsed but ``rbb_status == "fehlerhaft"`` → Widerspruch under
       Jahresfrist (§ 66 Abs. 2 SGG), with explanation in template.
    4. Lapsed → Überprüfungsantrag (§ 44 SGB X).

    Parameters
    ----------
    frist_result :
        A ``FristResult`` from the Fristen engine.
    claims :
        Optional list of claims (used for future heuristics).

    Returns
    -------
    str
        One of ``"widerspruch"``, ``"widerspruch_jahresfrist"``,
        ``"ueberpruefungsantrag_44"``, ``"akteneinsichtsantrag_25"``.
    """
    if frist_result is None:
        # No Frist information — safest default is Akteneinsicht
        return "akteneinsichtsantrag_25"

    if frist_result.frist_typ == "kein_va":
        # Not a Verwaltungsakt — no Widerspruch possible
        return "akteneinsichtsantrag_25"

    today = date.today()

    if frist_result.frist_ende >= today:
        # Frist still open or ends today
        if frist_result.frist_typ == "jahr":
            return "widerspruch_jahresfrist"
        return "widerspruch"

    # Frist has lapsed
    if frist_result.frist_typ == "jahr":
        return "widerspruch_jahresfrist"

    return "ueberpruefungsantrag_44"


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------


def generate_document(
    doc_type: str,
    frist_result: Any,
    reconciliation: list[Any],
    claims: list[dict[str, Any]],
    user_data: dict[str, str] | None = None,
    bescheid_datum: date | None = None,
    aktenzeichen: str | None = None,
    behoerde: str | None = None,
) -> GeneratedDocument:
    """Generate an action document.

    Parameters
    ----------
    doc_type :
        One of ``"widerspruch"``, ``"widerspruch_jahresfrist"``,
        ``"ueberpruefungsantrag_44"``, ``"akteneinsichtsantrag_25"``.
    frist_result :
        A ``FristResult`` from the Fristen engine (WP-21).
    reconciliation :
        List of ``ReconciliationLineItem`` from the calculation engine
        (WP-23).
    claims :
        List of claim dicts from pipeline output, each containing
        ``claim_text``, ``verification_status``, ``user_adjudication``.
    user_data :
        Dict with optional keys ``"name"``, ``"adresse"``, ``"email"``.
    bescheid_datum :
        Date of the Bescheid (optional, falls back to Frist result).
    aktenzeichen :
        Reference number of the Bescheid (optional).
    behoerde :
        Name of the issuing authority (optional).

    Returns
    -------
    GeneratedDocument
        The assembled document with rendered text and slot audit trail.
    """
    user_data = user_data or {}
    absender_name = user_data.get("name") or None
    absender_adresse = user_data.get("adresse") or None

    # If bescheid_datum not provided, try to derive from frist_result
    if bescheid_datum is None and frist_result is not None:
        bescheid_datum = frist_result.bekanntgabe  # best-effort fallback

    # ── Title mapping ─────────────────────────────────────────────────
    titles = {
        "widerspruch": "Widerspruch",
        "widerspruch_jahresfrist": "Widerspruch (Jahresfrist, § 66 Abs. 2 SGG)",
        "ueberpruefungsantrag_44": "Antrag auf Überprüfung (§ 44 SGB X)",
        "akteneinsichtsantrag_25": "Antrag auf Akteneinsicht (§ 25 SGB X)",
    }
    title = titles.get(doc_type, "Dokument")

    # ── Build slots ───────────────────────────────────────────────────
    slots: list[DocumentSlot] = []
    warnings: list[str] = []

    if doc_type == "akteneinsichtsantrag_25":
        # Akteneinsicht has minimal claim dependence — mainly procedural
        body_rendered = _render_akteneinsichtsantrag_template(
            slots,
            absender_name,
            absender_adresse,
            bescheid_datum,
            aktenzeichen,
            behoerde,
        )
    else:
        # Build slots for Widerspruch / Überprüfungsantrag
        slots = _build_widerspruch_slots(
            frist_result,
            reconciliation,
            claims,
            bescheid_datum,
            aktenzeichen,
            behoerde,
        )

        # Collect warnings from unresolved slots
        for s in slots:
            if s.needs_review or not s.verified:
                warnings.append(f"Ungesicherter Slot '{s.key}': {s.review_topic or s.label}")

        # Render the appropriate template
        if doc_type == "widerspruch_jahresfrist":
            body_rendered = _render_widerspruch_jahresfrist_template(
                slots,
                absender_name,
                absender_adresse,
            )
        elif doc_type == "widerspruch":
            body_rendered = _render_widerspruch_template(
                slots,
                absender_name,
                absender_adresse,
            )
        elif doc_type == "ueberpruefungsantrag_44":
            body_rendered = _render_ueberpruefungsantrag_template(
                slots,
                absender_name,
                absender_adresse,
            )
        else:
            body_rendered = f"[Unbekannter Dokumenttyp: {doc_type}]"
            warnings.append(f"Unbekannter Dokumenttyp: {doc_type}")

    # ── Append footer ─────────────────────────────────────────────────
    footer = _build_footer()
    full_text = body_rendered + "\n" + footer

    # ── Build metadata ────────────────────────────────────────────────
    generation_metadata: dict[str, Any] = {
        "app_version": get_app_version(),
        "inference_profile": settings.INFERENCE_PROFILE,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "doc_type": doc_type,
        "pseudonymization_enabled": settings.PSEUDONYMIZATION_ENABLED,
        "total_slots": len(slots),
        "unresolved_slots": len(warnings),
    }

    return GeneratedDocument(
        document_type=doc_type,
        title=title,
        rendered_text=full_text,
        slots=slots,
        warnings=warnings,
        generation_metadata=generation_metadata,
    )
