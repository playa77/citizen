# Citizen v1.0.0 — UI/UX Design Specification

<!-- Version: 1.0.0 | 2026-07-12 -->
<!-- Status: Approved design direction — implementation reference -->
<!-- Scope: WP-02 (Scope Cut), WP-14 (Prüfstand), WP-41 (Result Report), WP-42 (OCR Gate) -->

## 0. Design Thesis

Two audiences, one grammar. **Prüfstand** (demo/dev) and **Result Report** (stressed
layperson) share the same data model — findings, calculations, deadlines, next steps.
They differ in *framing* (expected vs. actual, verified vs. live), not *optics*. The
entire v1.0.0 system rests on this principle: **one component library, a context flag,
identical visuals.**

The emotional register: someone received a Bescheid threatening their livelihood. They
are scared and under a clock. The tool must feel like a **calm, competent advisor who
has done this a thousand times** — not a tech product. That means: the gravitas of a
German court document, the clarity of a well-set newspaper, warmth where warmth is
humane, urgency only where urgency is real.

### Decisions locked (2026-07-12)

| # | Decision | Rationale |
|---|---|---|
| D-1 | **Bekanntgabefiktion = +4 days** (strict goldset conformity). The goldset is the executable specification: "gilt am VIERTEN Tag nach Aufgabe zur Post als bekannt gegeben" (§ 37 Abs. 2 SGB X) — all 10 goldset cases compute Bekanntgabe as posting_date + 4 days. The timeline renders "+4 Tage Fiktion". | Goldset is authoritative for all legal behavior. |
| D-2 | **Warm-paper light theme** is the v1.0.0 default. Dark theme preserved as `[data-theme="dark"]` opt-in toggle. | Paper = document metaphor; unifies the current split light/dark. Chat (dark) is parked, removing the conflict. |
| D-3 | **Chat mode parked but accessible.** Removed from primary mode toggle (Analysieren · Prüfstand · Einstellungen); reachable via secondary menu / direct route. Existing sessions preserved. No regression. | D-5 from WP-41, softest non-regressive option. |
| D-4 | **This spec persisted** to `devdocs/design_v1.0.0.md` as the implementation reference. | Versioned, reviewable, durable. |

---

## 1. Visual Identity

### 1.1 Typography

The current system-font stack (`-apple-system, Segoe UI, Roboto…`) is the single biggest
aesthetic upgrade available. Type is where character lives for a legal tool.

| Role | Font | Why |
|---|---|---|
| **Headings / display** | `Source Serif 4` | Authority. A serif reads "Amt, Gesetz, Gericht." Excellent German diacritics (ä ö ü ß), open source, weights 200–900. |
| **Body / UI** | `Atkinson Hyperlegible` | Designed by the Braille Institute for low-vision readability — *meaningful* for stressed, tired, older users. Distinctive letterforms (b/d, 1/I), not generic. |
| **Numbers / § chips / code** | `IBM Plex Mono` | Tabular figures (calc diff columns align perfectly), German-engineering character, full diacritics. |

All three are free, on Google Fonts, and cover German fully. Load via `<link>` with
`display=swap`. No system-font fallbacks as primary — only as final safety net.

**Scale** (modular, 1.250 ratio):
```
--fs-display: 2.44rem  (39px)  — case title, deadline date
--fs-h1:       1.95rem  (31px)  — page heading
--fs-h2:       1.56rem  (25px)  — section heading
--fs-h3:       1.25rem  (20px)  — subsection
--fs-body:     1.00rem  (16px)  — base
--fs-small:    0.85rem  (14px)  — captions, chips
--fs-micro:    0.75rem  (12px)  — badges, metadata (uppercase, letter-spaced)
```

### 1.2 Theme Direction: Warm Paper (D-2)

Unified warm-paper light theme as the v1.0.0 default.
- Paper = "document," the central metaphor (Bescheid, report, export).
- Dark themes read "techy/gaming"; warm paper reads "official/human."
- Chat (the dark surface) is parked (D-3), removing the split-personality conflict.
- The existing dark tokens are preserved as `[data-theme="dark"]` overrides — no
  regression, just no longer default.

### 1.3 Color Token System

Four semantic colors (red/green/amber/gray) carry all meaning. One dominant accent.
Warm paper base. This is the backbone of the traffic-light system, deadline urgency,
calc diff, and the experimental badge — consistency here is everything.

```css
:root {
  /* === Paper & Ink (the document surface) === */
  --paper:          #faf8f4;  /* primary surface — warm off-white, like a real Bescheid */
  --paper-raised:   #ffffff;  /* cards, raised panels */
  --paper-recess:   #f1ece2;  /* code blocks, letter body, recessed areas */
  --ink:            #1c1a17;  /* primary text — deep warm black, not pure */
  --ink-soft:       #4a4640;  /* secondary text */
  --ink-faint:      #8a847a;  /* muted, captions, metadata */
  --rule:           #d9d2c4;  /* hairlines, borders — warm gray */

  /* === Brand Accent (the one dominant color — deep ink-blue) === */
  --accent:         #1b3a5b;  /* primary actions, heading emphasis — official, trustworthy */
  --accent-bright:  #2d5d8f;  /* hover, links */
  --accent-soft:    #e8eef4;  /* tinted backgrounds, selected states */

  /* === Semantic: RED — Fehler gefunden / contested / lapsed === */
  --sem-red:        #c0392b;  /* serious, not fire-engine */
  --sem-red-soft:   #fbeae7;
  --sem-red-ink:    #7a2418;

  /* === Semantic: GREEN — verifiziert / Bescheid hält stand === */
  --sem-green:      #2d7a4e;  /* forest, trustworthy */
  --sem-green-soft: #e8f3ec;
  --sem-green-ink:  #1a4a2e;

  /* === Semantic: AMBER — Warnung / Falle / Frist ≤7d === */
  --sem-amber:      #c9821a;  /* warm gold, not highlighter yellow */
  --sem-amber-soft: #fbf0dc;
  --sem-amber-ink:  #7a4d0a;

  /* === Semantic: GRAY — neutral / kein Verwaltungsakt / unbekannt === */
  --sem-gray:       #7a7468;
  --sem-gray-soft:  #eee9df;
  --sem-gray-ink:   #4a4640;

  /* === Functional === */
  --shadow-sm:  0 1px 2px rgba(28,26,23,.06), 0 1px 3px rgba(28,26,23,.04);
  --shadow-md:  0 4px 12px rgba(28,26,23,.10);
  --shadow-lg:  0 12px 32px rgba(28,26,23,.14);
  --radius-sm:  4px;
  --radius-md:  8px;
  --radius-lg:  14px;
  --radius-pill: 999px;
  --transition-fast: 140ms cubic-bezier(.4,0,.2,1);
  --transition:      220ms cubic-bezier(.4,0,.2,1);
}
```

**Contrast verification** (all meet WCAG AA 4.5:1 on their soft backgrounds):
- `--sem-red-ink` (#7a2418) on `--sem-red-soft` (#fbeae7) → ~7.8:1 ✓
- `--sem-green-ink` (#1a4a2e) on `--sem-green-soft` (#e8f3ec) → ~9.1:1 ✓
- `--sem-amber-ink` (#7a4d0a) on `--sem-amber-soft` (#fbf0dc) → ~6.4:1 ✓
- `--ink` (#1c1a17) on `--paper` (#faf8f4) → ~15:1 ✓

**Dark theme** (`[data-theme="dark"]`): invert paper → deep warm charcoal `#1a1815`,
ink → `#ebe6db`, keep semantic *vivid* variants (not soft) as accents. Provided for
parity; not the default.

---

## 2. Shared Component Architecture

### 2.1 The Component Library (13 components)

Every component is a **pure render function**: `Component(data, context) → HTMLElement`.
The `context` flag (`'pruefstand' | 'report' | 'demo'`) changes only labels and the demo
match-overlay — never optics. This is the contract that makes WP-14 and WP-41 share code.

| # | Component | Used in | Purpose |
|---|---|---|---|
| 1 | `DeadlineBanner` | Report, Prüfstand detail | The hero — 5 urgency states |
| 2 | `FristTimeline` | Prüfstand header (full), Report (mini), Detail (mini) | Horizontal deadline timeline |
| 3 | `ClaimList` | Report, Prüfstand detail, Demo comparison | Traffic-light findings list |
| 4 | `ClaimItem` | (child of ClaimList) | Single finding row + expand |
| 5 | `SectionChip` | ClaimItem, CalcDiff, everywhere | § reference pill |
| 6 | `CalcDiffTable` | Report, Prüfstand detail | Jobcenter vs. korrekt vs. Differenz |
| 7 | `NextSteps` | Report, Prüfstand detail | Numbered action checklist |
| 8 | `TrapCallout` | Report, Prüfstand detail | Amber warning box |
| 9 | `LetterRender` | Prüfstand detail, OCR gate | Behördenbrief styling |
| 10 | `ExperimentalBadge` | Intake, Report header, PDF footer | WP-02 persistent marker |
| 11 | `EvalOverlay` | Prüfstand only | Pass/fail per metric |
| 12 | `SummaryBlock` | Report | Plain-German 3–5 sentence summary |
| 13 | `ConfidenceRibbon` | OCR gate | Per-page confidence + edit |

### 2.2 Shared Data Contract

Reuse demands a shared JSON shape. Both the goldset API
(`GET /api/goldset/{case_id}`) and the live pipeline `final_output` must emit this
structure. The goldset stores `expected`; the live pipeline emits `actual`; the demo
comparison renders both side-by-side using the same components.

```typescript
// A "finding" — the atom shared by ClaimList, CalcDiff, EvalOverlay
interface Finding {
  id: string;
  verdict: 'error_against_user' | 'bescheid_correct' | 'unclear' | 'no_verwaltungsakt';
  title: string;                    // "Mietkosten zu niedrig angesetzt"
  detail: string;                   // plain-German explanation
  sections: SectionRef[];           // [§ 22 SGB II, § 11b SGB II]
  evidence?: EvidenceQuote[];       // expandable quotes (report/detail)
  amount_delta?: number;            // euros, for calc-linked findings
}

interface SectionRef { label: string; }   // "§ 31 Abs. 1 SGB II"

interface EvidenceQuote {
  text: string;
  citation: string;                 // "SGB II § 22 Abs. 1"
}

interface DeadlineInfo {
  status: 'normal' | 'urgent_amber' | 'urgent_red' | 'lapsed' | 'no_va';
  frist_date: string | null;        // ISO
  days_remaining: number | null;
  stations: FristStation[];         // for FristTimeline
  rollover_applied: boolean;
  wiedereinsetzung_hint?: string;   // §44 text for lapsed
}

interface FristStation {
  label: string;                    // "Aufgabe zur Post"
  date: string;                     // ISO
  delta_from_prev?: string;         // "+3 Tage fiktion"
}

interface CalcDiff {
  rows: CalcRow[];                  // line items
  total: { jobcenter: number; correct: number; delta: number };
}

interface CalcRow {
  label: string;                    // "Regelbedarf"
  jobcenter: number;
  correct: number;
  delta: number;
}
```

### 2.3 Context Flag Behavior

| Aspect | `pruefstand` | `report` | `demo` |
|---|---|---|---|
| Finding label | "Erwarteter Befund" | "Befund" | shows both + match badge |
| Evidence quotes | shown expanded | collapsed, expandable | side-by-side |
| EvalOverlay | visible | hidden | visible (actual vs expected) |
| ExperimentalBadge | hidden (goldset is Sozialrecht) | conditional (WP-02) | hidden |
| DeadlineBanner | static display | interactive (CTA) | both shown |

---

## 3. DeadlineBanner (the hero)

The single most important element on the page. Full-width, sits directly below the case
title, above the summary. It must answer "do I need to act, and how fast?" in under one
second.

### 3.1 Anatomy

```
┌──────────────────────────────────────────────────────────────────────┐
│ ▌  WIDERSPRUCHSFRIST                                                 │
│ ▌                                                                      │
│ ▌  14. August 2026                              noch 23 Tage          │
│ ▌                                                                      │
│ ▌  [mini FristTimeline: ●────●────●]                                  │
│ ▌                                          [ Nächste Schritte ↓ ]     │
└──────────────────────────────────────────────────────────────────────┘
```

- Left edge: 6px solid semantic color bar (the state anchor).
- Label row: micro-uppercase "WIDERSPRUCHSFRIST" in `--ink-faint`.
- Date: `--fs-display`, `Source Serif 4`, `--ink`.
- Day count: `--fs-h2`, right-aligned, semantic color, `IBM Plex Mono` tabular.
- Mini timeline: 3 compact stations (no labels, just dots + connector), optional rollover marker.
- CTA: ghost button, scrolls to `#next-steps`.

### 3.2 The Five States

| State | Trigger | Color | Day-count copy | Extra |
|---|---|---|---|---|
| **Normal** | >7 days | `--accent` (ink-blue) | "noch N Tage" | calm, no animation |
| **Amber** | ≤7 days | `--sem-amber` | "noch N Tage — jetzt handeln" | subtle bg tint `--sem-amber-soft` |
| **Red** | ≤3 days | `--sem-red` | "NUR NOCH N TAGE" | gentle pulse (opacity .88↔1, 2.2s), `role="alert"` |
| **Lapsed** | past | `--sem-gray` + red accent | "Frist abgelaufen" | §44 SGB X Wiedereinsetzung hint shown inline, `role="alert"` |
| **Kein VA** | no Verwaltungsakt detected | `--sem-gray` | "Kein Verwaltungsakt — keine Frist läuft" | explanatory subline |

**Critical**: color is never the only signal. Every state also has a distinct icon
(⏱ / ⚠ / ⏰ / ✓-circle / —) and text label. The pulse animation is gated behind
`@media (prefers-reduced-motion: no-preference)`.

---

## 4. FristTimeline (the showpiece)

The most high-value visual in the entire system. The WP-14 spec says it "replaces five
minutes of explanation in a Tacheles conversation." It must be precise, legible, and
honest about the rollover.

### 4.1 The Model (D-1: +3 days fiction)

Four stations along a horizontal axis:
1. **Aufgabe zur Post** (mailing date — the trigger)
2. **Bekanntgabefiktion** (+3 days, §41 SGB X Abs. 2 — the 4th day is deemed known)
3. **Fristende** (+1 Monat from Bekanntgabe, §70 SGO)
4. **Rollover** (only if Fristende lands on Sat/Sun/holiday → next workday, §31 SGB II analog)

> **Note on D-1:** The WP-14 spec text (`wp-1.6-pruefstand-v1.0.0 (2).md`) says "+4 days
> Bekanntgabefiktion." This is imprecise: §41 SGB X Abs. 2 fixes the fiction at 3 days
> (the 4th day = Bekanntgabetag). The timeline renders "+3 Tage fiktion". Flagged to the
> spec author for correction.

### 4.2 Full Variant (Prüfstand header)

Rendered as **inline SVG** with `viewBox="0 0 800 120"` so it scales perfectly from 320px
to 4K. Accessible `<title>`/`<desc>` + a visually-hidden `<ol>` of stations for screen
readers.

```
   +3 Tage fiktion              +1 Monat
  ┌─────────────┐         ┌───────────────────┐    ↻ Werktag
  │             │         │                   │   (nur Sa/So/Feiertag)
●═══════════════●═════════════════════════════●─────────────────────●
14.07.2026     17.07.2026                    17.08.2026           18.08.2026
Aufgabe        Bekanntgabe                   Fristende            (Rollt auf Mo)
zur Post       (fingiert)                    Widerspruch
```

- Stations: 14px filled circles in `--accent`. The final station (Fristende) is larger
  (20px) and ringed in its urgency semantic color.
- Connectors: 3px rules in `--rule`, with the delta label centered above in a `--paper`
  pill (so it overlays the line cleanly).
- Rollover: an **amber sub-arc** looping above the final segment, labeled "↻ Werktag" in
  `--sem-amber`. Only rendered when `rollover_applied === true`. When false, this segment
  is omitted entirely (honesty — no fake symmetry).
- Dates below stations: `IBM Plex Mono`, `--fs-small`, `--ink-soft`.
- Station labels: `--fs-micro` uppercase, `--ink-faint`.

### 4.3 Mini Variant (Report banner, case detail)

3 dots, no labels, connector only. ~120px wide. The rollover appears as a tiny amber dot
if applicable. Clicking it (in report) scrolls to / opens the full timeline in a popover.

### 4.4 Vertical Variant (<480px)

SVG rotates 90°: stations stack top-to-bottom, connectors vertical. Same data, same
component, `aria-orientation` swap.

---

## 5. Traffic-Light ClaimList

Used in report, Prüfstand detail, and demo comparison. The most-reused interactive
component.

### 5.1 Anatomy (collapsed)

```
┌─▌──────────────────────────────────────────────────────────────────┐
│ ▌ ✕  Mietkosten zu niedrig angesetzt            [§ 22] [§ 11b]   › │
│ ▌    Fehler zulasten gefunden — 40 € zu wenig                        │
└──────────────────────────────────────────────────────────────────────┘
```

- **Left bar**: 4px solid semantic color (the verdict anchor).
- **Icon badge**: 22px circle, semantic-soft bg, semantic-ink glyph:
  - ✕ red — `error_against_user`
  - ✓ green — `bescheid_correct`
  - ! amber — `unclear`
  - — gray — `no_verwaltungsakt`
- **Title**: `--fs-body` bold, `--ink`.
- **Subtitle**: verdict label + amount delta if present, `--ink-soft`.
- **§ chips**: `SectionChip` pills, right-aligned, wrap on narrow.
- **Chevron**: `›` rotates 90° on expand. Entire header is a
  `<button aria-expanded="false" aria-controls="…">`.

### 5.2 Expanded

```
│ ▌ ✕  Mietkosten zu niedrig angesetzt            [§ 22] [§ 11b]   ⌄ │
│ ▌    Fehler zulasten gefunden — 40 € zu wenig                        │
│ ┊                                                                      │
│ ┊  ▎ "Die angemessenen Kosten der Unterkunft werden nach § 22 Abs. 1  │
│ ┊  ▎  SGB II gewährt." — SGB II § 22 Abs. 1                           │
│ ┊                                                                      │
│ ┊  ▎ "Von dem Einkommen sind abzusetzen …" — SGB II § 11b Abs. 1      │
│ ┊                                                                      │
│ ┊  Berechnung: Jobcenter 280 € → korrekt 320 €  → +40 €               │
└──────────────────────────────────────────────────────────────────────┘
```

- Evidence quotes: blockquote with left rule, `--paper-recess` bg, `Source Serif 4`
  italic, citation in `--ink-faint`.
- Inline calc link: if the finding has `amount_delta`, a one-line summary linking to the
  CalcDiffTable row.

### 5.3 Demo Mode Overlay

Each `ClaimItem` gains a third column: a match badge. Green ✓ "übereinstimmend" or red ✗
"Abweichung" comparing expected vs. actual. In demo, the list renders twice (expected
left, actual right) using the same component — the comparison is layout, not a different
component.

### 5.4 SectionChip (§ chip)

```
┌────────────────┐
│ § 22 SGB II    │   ← IBM Plex Mono, 12px, --accent-soft bg, --accent ink
└────────────────┘   ← radius-pill, 2px pad, optional title tooltip with full text
```

Hover/focus reveals the full paragraph title via `title` attr + a styled tooltip.
Clicking (in Prüfstand/report) could deep-link to the corpus — deferred, but the
component is ready.

---

## 6. CalcDiffTable

Three columns, right-aligned tabular numbers, the difference column is the hero.

### 6.1 Anatomy

```
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Jobcenter hat        │ Korrekt wäre         │ Differenz            │
│ gerechnet            │                      │                      │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Regelbedarf  563,00  │ Regelbedarf  563,00  │             0,00  —  │
│ Mietkosten   280,00  │ Mietkosten   320,00  │          +40,00  ▲   │
│ Mehrbedarf    56,30  │ Mehrbedarf    80,00  │          +23,70  ▲   │
│ Abzüge      −156,30  │ Abzüge      −156,30  │             0,00  —  │
├══════════════════════┼══════════════════════┼══════════════════════┤
│ Gesamt       743,00  │ Gesamt       806,70  │          +63,70  ▲   │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

- **Jobcenter column**: neutral `--ink`, `--paper` bg.
- **Korrekt column**: subtle `--sem-green-soft` left tint (2px), signals "this is the right one."
- **Differenz column**:
  - `>0` → `--sem-green` text + ▲ glyph, `aria-label="plus 40 Euro"`
  - `<0` → `--sem-red` text + ▼ glyph
  - `=0` → `--ink-faint` + — glyph
- **Total row**: thicker top rule (`2px --ink`), bold, `--paper-recess` bg.
- All numbers: `IBM Plex Mono`, tabular-nums, `€` suffix, German decimal comma.
- `<caption>` (visually hidden, screen-reader): "Gegenüberstellung Jobcenter-Berechnung und korrekter Berechnung."

### 6.2 Responsive <480px

Table transforms to **stacked cards** — one card per line item, each showing the label +
three stacked values. Avoids horizontal scroll (which hides the difference column — the
hero). The total becomes a full-width emphasized card.

---

## 7. ExperimentalBadge (WP-02)

Persistent but deliberately understated. It must be *always present* for non-Sozialrecht
areas without dominating or alarming.

### 7.1 Design

```
┌─────────────────────────────────────┐
│ ⚠  EXPERIMENTELL — NICHT VERIFIZIERT │
└─────────────────────────────────────┘
```

- Inline pill, `--radius-pill`, `--sem-amber-soft` bg, `--sem-amber-ink` text.
- `--fs-micro` (12px), uppercase, letter-spacing 0.04em.
- Icon: a small ⚠ (or a custom flask SVG at 12px).
- `tabindex="0"` with a tooltip on focus/hover: *"Dieses Rechtsgebiet wird noch nicht
  vollumfänglich geprüft. Ergebnisse ohne Gewähr — nur für Sozialrecht (SGB II/X) liegt
  eine Verifikation vor."*

### 7.2 Placement (3 mandatory locations)

1. **Intake** — next to the detected area label in the preset card.
2. **Report header** — next to the case title, same row.
3. **Every generated output** — PDF footer (alongside disclaimer version + Rechtsstand)
   and top of on-screen report.

**Absent** for Sozialrecht. No badge = the positive signal. This is intentional: the
absence is the trust marker.

---

## 8. OCR Confirmation Gate (WP-42)

A full step between ingestion and pipeline. The user must confirm the extracted text
before analysis runs. This is where bad scans get caught.

### 8.1 Layout (desktop — three regions)

```
┌─────────┬──────────────────────────────────────────────┬──────────┐
│ Pages   │  Extracted Text (editable)                    │ Quality  │
│         │                                                │          │
│ ▤ P1 ●  │  ┌──────────────────────────────────────────┐ │ Overall  │
│ ▤ P2 ●  │  │ Jobcenter Mitte                          │ │  87%     │
│ ▤ P3 ●  │  │ Bescheid vom 14.07.2026                  │ │ ████████ │
│         │  │                                          │ │          │
│         │  │ Sehr geehrte(r) Frau/Herr ████,          │ │ Per page │
│         │  │ hiermit bescheiden wir…                  │ │ P1 94%   │
│         │  │                                          │ │ P2 71% ▼ │
│         │  │ [amber-wavy-underline on low-conf spans] │ │ P3 96%   │
│         │  └──────────────────────────────────────────┘ │          │
│         │                                                │ Threshold│
│         │                                                │ 70%      │
└─────────┴──────────────────────────────────────────────┴──────────┘
              [ ← Neu hochladen ]    [ Text bestätigen & Analyse starten → ]
```

### 8.2 Components

- **Page list** (left): each page is a row with a thumbnail, page number, and a
  **confidence dot** (green ≥90%, amber 70–89%, red <70%). Clicking selects that page's
  text in the editor.
- **Editor** (center): a `<textarea>` or `contenteditable` with the extracted text.
  Low-confidence spans are highlighted with an **amber wavy underline**
  (`text-decoration: underline wavy --sem-amber`) and a hover tooltip showing the
  confidence %. User can edit freely — edits override the OCR.
- **Quality panel** (right): overall confidence as a horizontal bar + percentage,
  per-page breakdown, and the threshold line (70%). If any page is below threshold, a
  warning appears.
- **ConfidenceRibbon**: the per-page bar component, reusable.

### 8.3 "Quality Insufficient" State

When overall confidence < threshold, the primary CTA is **disabled and replaced**:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⚠  Textqualität unzureichend (62%)                                    │
│    Die automatische Texterkennung ist zu unsicher für eine zuverlässige│
│    Analyse. Bitte scannen Sie das Dokument neu:                       │
│      • 300 dpi Auflösung                                              │
│      • Hoher Kontrast (schwarz/weiß)                                  │
│      • Dokument flach, ohne Schatten                                  │
│                                                                      │
│                                  [ Dokument neu hochladen → ]         │
└──────────────────────────────────────────────────────────────────────┘
```

No path to proceed with garbage text. The user *can* still manually edit and the
confidence recalculates on edit (edited spans are treated as confirmed = 100%), so a
determined user can rescue a mediocre scan by fixing the bad spots — but the system
never silently proceeds.

### 8.4 Responsive

<768px: three regions stack — quality summary on top (most important decision info),
editor middle, page list collapses to a `<select>`.

---

## 9. Prüfstand Header Area

### 9.1 Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ PRÜFSTAND                                                            │
│ Goldset v0.1.0 · Rechtsstand 2026-07-11 · 10 Fälle · verifiziert …   │
├──────────────────────────────────────────────────────────────────────┤
│ ┌─ Eval Aggregate ──────────────────────────────────────────────────┐│
│ │ Letzter Lauf: Modell X — 9/10 vollständig bestanden · 12.07.2026  ││
│ │ [oder: Noch keine Prüfläufe — sauberer Leerzustand]               ││
│ └────────────────────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────────────────┤
│ RECHTLICHE BASISLINIEN                                               │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│ │ Regelbedarf  │ │ § 11b        │ │ Sanktionen   │ │ Fristen      │  │
│ │ Tabelle      │ │ Freibeträge  │ │ neues Recht  │ │ [FULL TIMELINE]│ │
│ │ 563 € …      │ │ [Treppengrafik]│ │              │ │              │  │
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│ BEWUSST OFFENE RECHTSFRAGEN                                          │
│ ▎ Frage 1: …  ▎ Frage 2: …                                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.2 Elements

- **Badge row**: four pills (version, Rechtsstand, count, date) in `--accent-soft`/
  `--accent`, micro-uppercase. The "synthetische Fälle" notice is a separate amber-tinted
  line below: *"Hinweis: Es handelt sich um synthetische, fiktive Fälle."*
- **Eval aggregate tile**: if reports exist → model name, pass count, date. If none →
  **clean empty state**: a dashed-border tile with "Noch keine Prüfläufe" and a short
  explanation. No fake numbers, no grayed-out placeholders that look like data.
- **Baseline cards** (4-up grid, 2-up on tablet, 1-up on phone):
  1. **Regelbedarf** — small table (Eckwertesätze).
  2. **§ 11b Freibeträge** — a **step graphic** (Treppengrafik): ascending bars/steps
     showing the deduction ladder. SVG, ~120px tall.
  3. **Sanktionen** — compact rules summary (new law).
  4. **Fristen** — the full `FristTimeline` (the showpiece).
- **Open questions**: each as a `TrapCallout`-style amber-tinted row, honestly labeled
  "Bewusst offen gelassene Rechtsfragen." Transparency as a feature.

---

## 10. Case Gallery + Case Detail (Prüfstand)

### 10.1 Gallery Card

```
┌──────────────────────────────────────┐
│ ▌  GS-002                            │   ← left bar = verdict color
│    Sanktion / Meldeversäumnis        │   ← plain-German category label
│    Schwerigkeit: mittel              │
│                                      │
│    ✕  Fehler zulasten gefunden       │   ← verdict summary
│                                      │
│    [ Diesen Fall live analysieren → ]│   ← demo CTA
└──────────────────────────────────────┘
```

- 3-up grid on desktop, 2-up tablet, 1-up phone.
- Left bar color = neutral semantic (red/green/gray per spec).
- Eval overlay: a small ribbon on the card corner — green ✓ "bestanden" / red ✗
  "abweichend" / absent if no run.

### 10.2 Case Detail (two-column)

```
┌─────────────────────┬─────────────────────────────────┐
│  BESCHEID           │  ERWARTETE BEFUNDE              │
│  (LetterRender)     │                                  │
│                     │  [DeadlineBanner — static]      │
│  ┌───────────────┐  │                                  │
│  │ Jobcenter …   │  │  [ClaimList]                    │
│  │ Bescheid …    │  │  ▌ ✕ Mietkosten … [§22]         │
│  │ Sehr geehrte… │  │  ▌ ✓ Regelbedarf … [§20]        │
│  │               │  │                                  │
│  │ (Briefoptik)  │  │  [CalcDiffTable]                │
│  └───────────────┘  │                                  │
│                     │  [FristTimeline — mini]          │
│                     │                                  │
│                     │  [TrapCallout: Bekannte Falle]   │
│                     │                                  │
│                     │  [NextSteps]                     │
└─────────────────────┴─────────────────────────────────┘
```

- **Left = `LetterRender`**: the Bescheid rendered as an official letter, not a code
  block. `Source Serif 4`, `--paper-recess` bg, a faux-letterhead band, justified text,
  sender/recipient blocks, date line. This is the "Behördenbrief" optic the spec demands.
- **Right = findings column**: reuses `DeadlineBanner`, `ClaimList`, `CalcDiffTable`,
  `FristTimeline` (mini), `TrapCallout`, `NextSteps` — **the exact same components as the
  live report**. This is the WP-14/WP-41 reuse contract made visible.
- <768px: stacks (Bescheid on top, findings below).

---

## 11. Result Report Journey (WP-41)

### 11.1 Page Order (top to bottom — the one excellent journey)

1. **Case header**: title + `ExperimentalBadge` (if applicable) + export actions.
2. **`DeadlineBanner`** — the hero. First thing after the title.
3. **`SummaryBlock`**: 3–5 plain-German sentences. `Source Serif 4`, `--fs-h3`, generous
   leading. The "what does this mean for me" in human language.
4. **`ClaimList`** — traffic-light findings, expandable evidence.
5. **`CalcDiffTable`** — the money.
6. **`NextSteps`** — numbered checklist with checkboxes (persisted to `user_edits`).
7. **Document generation panel**: "Widerspruchsschreiben erstellen" / "Bericht als PDF
   exportieren."

### 11.2 NextSteps

```
┌──────────────────────────────────────────────────────────────────────┐
│ NÄCHSTE SCHRITTE                                                      │
│  ☐ 1.  Widerspruch bis 14.08.2026 per Einwurf-Einschreiben senden     │
│  ☐ 2.  Kopie des Bescheids und dieses Berichts beilegen                │
│  ☐ 3.  Beratungsstelle kontaktieren (Empfehlung)                      │
│  ☐ 4.  Frist im Kalender eintragen                                    │
└──────────────────────────────────────────────────────────────────────┘
```

Checkboxes are real `<input type=checkbox>`, state persisted. Items linked to
findings/deadline get a § chip or date chip.

### 11.3 PDF Export

Server-side render (WeasyPrint or similar) using the **same component CSS**, adapted for
print: `@media print` / dedicated print stylesheet. Footer on every page: disclaimer
version · Rechtsstand · `ExperimentalBadge` (if applicable) · page number. The PDF is
the report, not a separate artifact.

### 11.4 Chat Mode (D-3 / D-5)

Parked from the primary journey. The mode toggle reduces to **Analysieren · Prüfstand ·
Einstellungen**. Chat remains accessible via a secondary menu / direct route for existing
sessions — no regression, just de-emphasized. The dark chat theme tokens are preserved.

---

## 12. Motion & Interaction

One orchestrated cascade per view, not scattered micro-interactions.

### 12.1 Report Load Cascade (~700ms total, staggered)

1. `DeadlineBanner` fades + scales in (0→1, 0.96→1) — *the anchor, first*
2. `SummaryBlock` fades in (+80ms)
3. `ClaimList` items stagger in (+60ms each, 4–6 items)
4. `CalcDiffTable` rows stagger (+40ms each)
5. `NextSteps` fades in last

All gated behind `@media (prefers-reduced-motion: no-preference)`; reduced-motion users
get instant render.

### 12.2 Hover States

- `ClaimItem` row: `--paper-recess` bg tint, left bar widens 4→6px.
- `§ chip`: lifts 1px, shadow-sm.
- Gallery card: lifts 2px, shadow-md, left bar brightens.
- Buttons: `--accent-bright` bg, -1px translate.

### 12.3 Expand/Collapse

`ClaimItem` evidence: `max-height` transition (0→auto via measured height), chevron
rotates 90°, `aria-expanded` toggles. 200ms.

---

## 13. Accessibility

### 13.1 Structure

- Semantic landmarks: `<header role="banner">`, `<main>`, `<nav>` (mode toggle),
  `<footer>`.
- Heading hierarchy: one `<h1>` (case/page title), `<h2>` per section, `<h3>` per
  subsection. No skipped levels. The `DeadlineBanner` label is an `<h2>` peer.
- `<section aria-labelledby="…">` wrapping each report section.

### 13.2 Color is Never the Only Signal

Every semantic state has **three** carriers: color + icon + text label.
- ClaimItem verdict: bar color + icon glyph + "Fehler zulasten gefunden" text.
- DeadlineBanner: bar color + icon + day-count text + `role`.
- CalcDiff: cell color + ▲/▼/— glyph + `aria-label`.

### 13.3 Keyboard

- All interactive elements reachable via Tab in DOM order.
- `ClaimItem` header: `<button>`, Enter/Space toggles, `aria-expanded`/`aria-controls`.
- Modals/overlays: focus trap, Escape to close, return focus to trigger.
- Demo comparison: left/right arrow keys move focus between expected/actual columns.
- Skip-to-content link at top of `<body>` (visually hidden until focused).

### 13.4 Screen Reader

- `FristTimeline` SVG: `<title>Fristen-Verlauf</title>`, `<desc>…</desc>`, `role="img"`,
  plus a visually-hidden `<ol>` listing stations with dates — the SVG is decorative, the
  list is the content.
- `DeadlineBanner` red/lapsed: `role="alert"`; normal/amber: `role="status"`.
- `CalcDiffTable`: `<caption>`, `<th scope="col">`, diff cells
  `aria-label="plus 40 Euro gegenüber Jobcenter"`.
- `EvalOverlay` empty state: `aria-label="Keine Prüfläufe vorhanden"` — explicit, not
  implied by emptiness.
- Live regions: pipeline progress updates announced via `aria-live="polite"`.

### 13.5 Motion & Contrast

- `@media (prefers-reduced-motion: reduce)`: all animations → `0ms`, pulse disabled,
  stagger disabled.
- All text meets AA (verified in §1.3). Interactive elements have a visible 2px
  `--accent` focus ring (`:focus-visible`), never removed.

---

## 14. Responsive Strategy

### 14.1 Breakpoints

| Name | Width | Behavior |
|---|---|---|
| phone | 320–479px | Single column, stacked tables, vertical timeline |
| phone-lg | 480–639px | Single column, slightly relaxed |
| tablet | 640–1023px | 2-up grids, two-column detail stacks |
| desktop | 1024–1439px | 3-up grids, two-column detail |
| wide | 1440–1919px | 3–4-up grids, max-content-width 1200px centered |
| ultra | 1920px+ | 4-up grids, max-content-width 1400px, larger type |

### 14.2 Key Adaptations

- **Prüfstand detail**: two-column → single column <768px (Bescheid top, findings below).
- **CalcDiffTable**: <480px → stacked cards (label + 3 values per card).
- **FristTimeline**: <480px → vertical orientation (SVG rotates).
- **Case gallery**: 1 col <640px, 2 col 640–1023, 3 col 1024–1439, 4 col ≥1440.
- **OCR gate**: <768px → quality summary on top, editor middle, page list → `<select>`.
- **Content max-width**: 1200px (desktop) / 1400px (wide) — beyond that, generous margins.
  Lines never exceed ~75ch for readability.
- **Touch targets**: minimum 44×44px (WCAG 2.5.5) — § chips and small buttons get padding
  to meet this.

### 14.3 320px Floor

At 320px: single column, `--fs-body` stays 16px (no zoom-out — readability first),
padding reduces to `--spacing-sm`, header brand + mode toggle stack vertically, deadline
banner day-count drops below date.

---

## 15. Implementation Notes

1. **No framework** — components are plain functions returning `HTMLElement`, registered
   on a `Citizen.components` namespace. A tiny `render(parent, componentFn)` helper
   handles diffing-by-replace (sufficient for this app's update frequency).
2. **CSS architecture**: tokens in `:root` (§1.3), component classes prefixed `c-` (e.g.
   `.c-deadline-banner`, `.c-claim-list`), layout utilities prefixed `l-`. BEM-ish but
   lean. The existing 2845-line `style.css` gets refactored incrementally — no big-bang
   rewrite (regression risk).
3. **Fonts**: Google Fonts `<link>` in `index.html` `<head>` with `preconnect`. Subset to
   Latin + German diacritics. `font-display: swap`.
4. **SVG icons**: a small inline `<symbol>` sprite (no icon font, no external requests).
   The current inline SVGs in `index.html` migrate there.
5. **Versioning**: bump `index.html` to v1.0.0, `style.css`/`app.js` to v1.0.0 on
   implementation. Update `ui_testing_guide.md` with new component test cases.
6. **No regression**: existing Analyze mode flow, Settings mode, corpus management, and
   Chat (via secondary route) all continue to work. The refactor is additive — new
   component classes and tokens layered on, old classes migrated incrementally.

---

## Changelog

- **1.0.0 (2026-07-12):** Erstfassung. Approved design direction for v1.0.0 covering
  WP-02, WP-14, WP-41, WP-42. Four decisions locked: +3-day Bekanntgabefiktion (§41 SGB
  X), warm-paper default theme, Chat parked-but-accessible, spec persisted to devdocs.
  Defines 13-component shared library, color token system, FristTimeline showpiece,
  DeadlineBanner 5-state hero, traffic-light ClaimList, CalcDiffTable, OCR gate, OCR
  confidence ribbon, ExperimentalBadge, accessibility and responsive strategy.
