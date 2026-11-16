"""Action-draft renderer (WP-40; generic since WP-93, ARCHITECTURE.md § 3.6).

Renders building-block drafts declared by modules
(``document_templates`` in ``module.yaml``, e.g.
``modules/sozialrecht/documents/templates.yaml``: Widerspruch, Widerspruch
unter Jahresfrist, Überprüfungsantrag, Akteneinsichtsantrag). The module
supplies titles, slot definitions, template text and the generator-selection
table; the core owns the slot mechanism, the guardrail and the footer.

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

# Semantic Version: 0.4.0 | 2026-11-16 — WP-96: provenance names the module
# whose template rendered the draft (citizen-provenance-v1.1).
# 0.3.0 | 2026-11-16 — WP-93: templates, slot definitions and
# generator selection moved into module data; this file is the generic
# renderer (output byte-identical for the sozialrecht drafts).
# 0.2.0 | 2026-08-25 — Art. 50(2) EU AI Act (D-032):
# GeneratedDocument carries a machine-readable `provenance` marker (no
# `disclosure` — that was already delivered with the analysis result).

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import get_app_version, get_app_version_tag, settings
from app.services.disclosure import ProvenanceMarker, build_disclosure_and_provenance

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
        Template id declared by the module (e.g. ``"widerspruch"``).
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
    provenance :
        Art. 50(2) machine-readable marker for the AI-generated document text
        (D-032). Deliberately no ``disclosure`` field: document generation is
        a downstream action from a completed analysis whose response already
        carried the disclosure; repeating it would imply a second
        first-exposure event.
    """

    document_type: str
    title: str
    rendered_text: str
    slots: list[DocumentSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: ProvenanceMarker | None = None


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
        if any(kw.lower() in claim_text for kw in topic_keywords) and validate_slot_claim(claim):
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
                return val if isinstance(val, int | float) else None
        elif isinstance(item, dict) and item.get("label") == label:
            val = item.get("korrekt")
            return val if isinstance(val, int | float) else None
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
# Module templates
# ---------------------------------------------------------------------------


class _SlotValues(dict[str, str]):
    """``str.format_map`` mapping: a slot the template names but the slot set
    lacks renders as an empty review placeholder (v2.0.0 semantics)."""

    def __missing__(self, key: str) -> str:
        return DocumentSlot("", "", "").render()


def _templates(module_id: str | None) -> tuple[str, dict[str, Any]]:
    from app.modules.areas import area_tables
    from app.modules.runtime import document_templates

    resolved = module_id or area_tables().default_module
    data = document_templates(resolved)
    if data is None:
        raise ValueError(f"module {resolved!r} declares no document templates")
    return resolved, data


def _format_input(value: Any) -> str | None:
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return value or None


def _find_reconciliation_attr(reconciliation: list[Any], label: str, attr: str) -> Any:
    """First matching line item's *attr* (dataclass or dict), unfiltered."""
    for item in reconciliation:
        if hasattr(item, "label") and hasattr(item, attr):
            if item.label == label:
                return getattr(item, attr)
        elif isinstance(item, dict) and item.get("label") == label:
            return item.get(attr)
    return None


def _claims_slot(definition: dict[str, Any], claims: list[dict[str, Any]]) -> DocumentSlot:
    """Collect all verified + confirmed claims; unverified ones become topics."""
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

    claims_value = verified_claims_text if verified_claims_text else None
    claims_review = bool(unverified_topics) or not verified_claims_text
    claims_topic = (
        "; ".join(unverified_topics[:3]) if unverified_topics else definition["review_topic"]
    )
    return DocumentSlot(
        key=definition["key"],
        label=definition["label"],
        source="claim",
        value=claims_value,
        verified=bool(verified_claims_text),
        needs_review=claims_review and not verified_claims_text,
        review_topic=claims_topic if claims_review and not verified_claims_text else "",
    )


def _build_slot(
    definition: dict[str, Any],
    *,
    frist_result: Any,
    reconciliation: list[Any],
    claims: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> DocumentSlot:
    kind = definition["kind"]
    topic = definition["review_topic"]
    if kind == "input":
        raw = inputs.get(definition["input"])
        value = _format_input(raw)
        return DocumentSlot(
            key=definition["key"],
            label=definition["label"],
            source="user_input",
            value=value if isinstance(raw, date) else raw,
            verified=bool(value),
            needs_review=not value,
            review_topic=topic if not value else "",
        )
    if kind == "frist_date":
        formatted = (
            getattr(frist_result, definition["field"]).strftime("%d.%m.%Y")
            if frist_result is not None
            else None
        )
        return DocumentSlot(
            key=definition["key"],
            label=definition["label"],
            source="fristen",
            value=(definition.get("prefix", "") + formatted) if formatted else None,
            verified=bool(formatted),
            needs_review=not formatted,
            review_topic=topic if not formatted else "",
        )
    if kind == "calc_amount":
        amount = _find_reconciliation_value(reconciliation, definition["line"])
        return DocumentSlot(
            key=definition["key"],
            label=definition["label"],
            source="berechnung",
            value=_fmt_eur(amount),
            verified=amount is not None,
            needs_review=amount is None,
            review_topic=topic if amount is None else "",
        )
    if kind == "calc_difference":
        line_diff = _find_reconciliation_attr(reconciliation, definition["line"], "differenz")
        fallback = _find_reconciliation_value(reconciliation, definition["fallback_korrekt_line"])
        slot_diff = line_diff if line_diff is not None else fallback
        tolerance = float(definition["tolerance_eur"])
        texts = definition["texts"]
        diff_text: str | None
        if slot_diff is not None:
            amount_str = f"{abs(slot_diff):.2f}"
            if slot_diff > tolerance:
                diff_text = texts["positive"].format(amount=amount_str)
            elif slot_diff < -tolerance:
                diff_text = texts["negative"].format(amount=amount_str)
            else:
                diff_text = texts["zero"].format(amount=amount_str)
        else:
            diff_text = None
        return DocumentSlot(
            key=definition["key"],
            label=definition["label"],
            source="berechnung",
            value=diff_text,
            verified=slot_diff is not None,
            needs_review=slot_diff is None,
            review_topic=topic if slot_diff is None else "",
        )
    if kind == "claims":
        return _claims_slot(definition, claims)
    raise ValueError(f"unknown document slot kind: {kind!r}")


def _render_parts(parts: list[dict[str, Any]], values: _SlotValues) -> str:
    body = ""
    for part in parts:
        gate = part.get("when_resolved")
        if gate is not None:
            rendered = values[gate]
            if not rendered or rendered.startswith("[BITTE PRÜFEN"):
                continue
        body += str(part["text"]).format_map(values)
    return body


# ---------------------------------------------------------------------------
# Generator selection logic
# ---------------------------------------------------------------------------


def select_generator(
    frist_result: Any,
    claims: list[dict[str, Any]] | None = None,
    *,
    module_id: str | None = None,
) -> str:
    """Select which document template to use based on the Frist status.

    The selection table is module data (``selection`` in the module's
    document templates). For the sozialrecht module:

    1. no Frist information or ``frist_typ == "kein_va"`` → Akteneinsicht;
    2. ``frist_ende >= today()`` → Widerspruch (Jahresfrist variant for
       ``frist_typ == "jahr"``);
    3. lapsed → Widerspruch under Jahresfrist for ``"jahr"``, else
       Überprüfungsantrag (§ 44 SGB X).

    Parameters
    ----------
    frist_result :
        A ``FristResult`` from the Fristen core.
    claims :
        Optional list of claims (used for future heuristics).
    module_id :
        Module whose templates apply; ``None`` → ``DEFAULT_MODULE``.

    Returns
    -------
    str
        A template id declared by the module.
    """
    _, data = _templates(module_id)
    selection = data["selection"]

    if frist_result is None:
        # No Frist information — module's safest default
        return str(selection["no_deadline"])

    by_typ = selection.get("by_frist_typ") or {}
    if frist_result.frist_typ in by_typ:
        return str(by_typ[frist_result.frist_typ])

    branch = selection["open"] if frist_result.frist_ende >= date.today() else selection["lapsed"]
    return str((branch.get("by_frist_typ") or {}).get(frist_result.frist_typ, branch["default"]))


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
    *,
    module_id: str | None = None,
) -> GeneratedDocument:
    """Generate an action document from a module template.

    Parameters
    ----------
    doc_type :
        Template id declared by the module (e.g. ``"widerspruch"``).
    frist_result :
        A ``FristResult`` from the Fristen core (WP-21/WP-92).
    reconciliation :
        List of reconciliation line items from the module calculator
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
    module_id :
        Module whose templates apply; ``None`` → ``DEFAULT_MODULE``.

    Returns
    -------
    GeneratedDocument
        The assembled document with rendered text and slot audit trail.
    """
    resolved_module, data = _templates(module_id)
    user_data = user_data or {}
    absender_name = user_data.get("name") or None
    absender_adresse = user_data.get("adresse") or None

    # If bescheid_datum not provided, try to derive from frist_result
    if bescheid_datum is None and frist_result is not None:
        bescheid_datum = frist_result.bekanntgabe  # best-effort fallback

    absender_rendered = ""
    if absender_name:
        absender_rendered += absender_name + "\n"
    if absender_adresse:
        absender_rendered += absender_adresse

    inputs: dict[str, Any] = {
        "bescheid_datum": bescheid_datum,
        "aktenzeichen": aktenzeichen,
        "behoerde": behoerde,
    }

    template = (data.get("templates") or {}).get(doc_type)
    title = str(template["title"]) if template else "Dokument"

    # ── Build slots ───────────────────────────────────────────────────
    slots: list[DocumentSlot] = []
    warnings: list[str] = []
    values = _SlotValues(absender=absender_rendered)

    if template is not None and not template.get("uses_slots", True):
        # Procedural drafts without claim dependence: request inputs only.
        for name, spec in (template.get("inputs") or {}).items():
            formatted = _format_input(inputs.get(spec["input"]))
            values[name] = formatted or f"[BITTE PRÜFEN: {spec['review_topic']}]"
        body_rendered = _render_parts(template["parts"], values)
    else:
        slots = [
            _build_slot(
                definition,
                frist_result=frist_result,
                reconciliation=reconciliation,
                claims=claims,
                inputs=inputs,
            )
            for definition in data.get("slots") or ()
        ]

        # Collect warnings from unresolved slots
        for slot in slots:
            if slot.needs_review or not slot.verified:
                warnings.append(
                    f"Ungesicherter Slot '{slot.key}': {slot.review_topic or slot.label}"
                )

        if template is not None:
            values.update({slot.key: slot.render() for slot in slots})
            body_rendered = _render_parts(template["parts"], values)
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

    # Art. 50(2) marker (D-032): built through the same shared helper the SSE
    # emitters use, so provenance content stays identical across surfaces for
    # the same request. The helper never raises.
    # Provenance v1.1 (WP-96): the module whose template rendered the draft.
    _, document_provenance = build_disclosure_and_provenance(settings, [resolved_module])

    return GeneratedDocument(
        document_type=doc_type,
        title=title,
        rendered_text=full_text,
        slots=slots,
        warnings=warnings,
        generation_metadata=generation_metadata,
        provenance=document_provenance,
    )
