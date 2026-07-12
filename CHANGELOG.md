# Changelog

All notable changes to the Citizen project are documented in this file.
Newest entries first. Dates in ISO 8601.

---

## 2026-07-12 — v1.0.0 UI/UX design direction approved

### Added
- `devdocs/design_v1.0.0.md` — comprehensive UI/UX design specification for the v1.0.0
  release. Covers four work packages: WP-02 (Scope Cut / Experimental Badge), WP-14
  (Prüfstand View), WP-41 (Result Report & Case Journey Redesign), WP-42 (OCR
  Confirmation Gate). Defines a 13-component shared library, color token system, the
  FristTimeline showpiece, DeadlineBanner 5-state hero, traffic-light ClaimList,
  CalcDiffTable, OCR confidence gate, accessibility and responsive strategy.

### Decisions locked (design review)
- **D-1: Bekanntgabefiktion = +4 days** (strict goldset conformity). The goldset is the
  executable specification for all legal behavior — § 37 Abs. 2 SGB X is rendered as posting_date
  + 4 days. FristTimeline renders "+4 Tage Fiktion".
- **D-2: Warm-paper light theme** is the v1.0.0 default. Dark theme preserved as
  `[data-theme="dark"]` opt-in toggle. Unifies the current split light (Analyze) /
  dark (Chat) personality.
- **D-3: Chat mode parked but accessible.** Removed from primary mode toggle
  (Analysieren · Prüfstand · Einstellungen); reachable via secondary menu / direct route.
  Existing sessions preserved. No regression.
- **D-4: Design spec persisted** to `devdocs/design_v1.0.0.md` as implementation
  reference.

### Notes
- No code changes yet — this is design/strategy only. Implementation pending alignment
  on component build order.
- Typography direction: Source Serif 4 (headings) + Atkinson Hyperlegible (body) +
  IBM Plex Mono (numbers/§ chips). All Google Fonts, full German diacritic support.
- The existing `style.css` (v0.3.0, 2845 lines) will be refactored incrementally — no
  big-bang rewrite (regression risk). New component classes prefixed `c-`, tokens in
  `:root`.
