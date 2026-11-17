"""Plain-language layer (roadmap P12, WP-122/WP-123/WP-125; D-068).

Fixed, reviewed copy in Bürgersprache, Leichte Sprache and plain English —
module copy for findings and deadlines (``modules/<id>/copy/``) and core copy
for the disclaimer summary, the AI notice and privacy
(``app/plain/core/``). The layer never generates language: it selects copy
and fills whitelisted placeholders from deterministic engine output.
Correctness is gated offline by ``python -m eval.plain_eval``.
"""
