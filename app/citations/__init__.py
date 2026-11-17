"""German legal citation parsing and verification (WP-114).

``parser`` finds statute citations (``§ 44 Abs. 1 Satz 2 SGB X``,
``§§ 535 ff. BGB``, ``Art. 3 Abs. 1 GG``), ECLIs and BSG docket numbers in
text, with character spans — the extraction pattern of the BSD-licensed
eyecite project, reimplemented here (MIT) for German citation forms; no
eyecite code is used. ``verify`` checks each citation against the ingested
corpus: is the cited § (and Absatz) present, is the decision ingested?
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114: initial version.
