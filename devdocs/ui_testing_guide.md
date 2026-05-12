# Citizen UI — Comprehensive Human Testing Guide

**Version:** 0.2.0  
**Last Updated:** 2026-05-12  
**Purpose:** Exhaustive manual testing coverage for every UI element, user flow, decision tree, and edge case.

---

## Table of Contents

1. [Test Environment Setup](#1-test-environment-setup)
2. [Disclaimer Modal](#2-disclaimer-modal)
3. [Mode Toggle](#3-mode-toggle)
4. [Analyze Mode — File Upload](#4-analyze-mode--file-upload)
5. [Analyze Mode — Corpus Management](#5-analyze-mode--corpus-management)
6. [Analyze Mode — Text Extraction (OCR)](#6-analyze-mode--text-extraction-ocr)
7. [Analyze Mode — Analysis Pipeline](#7-analyze-mode--analysis-pipeline)
8. [Analyze Mode — Results Display](#8-analyze-mode--results-display)
9. [Analyze Mode — Error Handling](#9-analyze-mode--error-handling)
10. [Chat Mode — Sidebar & Conversation List](#10-chat-mode--sidebar--conversation-list)
11. [Chat Mode — New Conversation](#11-chat-mode--new-conversation)
12. [Chat Mode — Conversation Selection](#12-chat-mode--conversation-selection)
13. [Chat Mode — Conversation Deletion](#13-chat-mode--conversation-deletion)
14. [Chat Mode — Message Sending](#14-chat-mode--message-sending)
15. [Chat Mode — SSE Streaming (Chat+RAG)](#15-chat-mode--sse-streaming-chatrag)
16. [Chat Mode — SSE Streaming (Pipeline Mode)](#16-chat-mode--sse-streaming-pipeline-mode)
17. [Chat Mode — Document Upload](#17-chat-mode--document-upload)
18. [Chat Mode — Document Chips](#18-chat-mode--document-chips)
19. [Chat Mode — Drag & Drop](#19-chat-mode--drag--drop)
20. [Chat Mode — Error Handling](#20-chat-mode--error-handling)
21. [Cross-Cutting Concerns](#21-cross-cutting-concerns)
22. [Responsive Design](#22-responsive-design)
23. [Browser Compatibility](#23-browser-compatibility)
24. [Quick Smoke Test Checklist](#24-quick-smoke-test-checklist)

---

## 1. Test Environment Setup

### Prerequisites
- Running Citizen backend (`docker-compose up` or direct `uvicorn`)
- PostgreSQL 16 with pgvector extension
- Valid `OPENROUTER_API_KEY` in `.env`
- Corpus has been seeded at least once (or test corpus update flow first)

### Test Data
Prepare these files for testing:
| File | Type | Size | Purpose |
|------|------|------|---------|
| `test_small.pdf` | PDF | <1 MB | Normal upload |
| `test_large.pdf` | PDF | >25 MB | Size rejection |
| `test_image.jpg` | JPG | <25 MB | Image upload |
| `test_image.png` | PNG | <25 MB | Image upload |
| `test.txt` | TXT | any | Type rejection |
| `test_empty.pdf` | PDF | any | Empty/edge case |
| `test_multi_page.pdf` | PDF | <25 MB | Multi-page OCR |

### Browser Setup
- Open DevTools (F12) → Network tab to observe API calls
- Open DevTools → Console to observe errors
- Open DevTools → Application → Local Storage to inspect `legal_disclaimer_accepted_v1`

---

## 2. Disclaimer Modal

### 2.1 Initial Load — First Visit

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-01 | Open app with **no** `legal_disclaimer_accepted_v1` in localStorage | Disclaimer modal appears as full-screen overlay. App (`#app`) is hidden. |
| D-02 | Observe modal content | Title reads "Rechtlicher Hinweis". Disclaimer text loads from `/api/v1/meta/disclaimer/text` and renders as HTML. |
| D-03 | Observe "Bestätigen" button state | Button is **disabled** (greyed out, `opacity: 0.5`, `cursor: not-allowed`). |
| D-04 | Observe checkbox state | Checkbox is **unchecked**. |
| D-05 | Click "Bestätigen" while checkbox is unchecked | Nothing happens. Button is disabled. |
| D-06 | Check the checkbox | "Bestätigen" button becomes **enabled**. |
| D-07 | Uncheck the checkbox | "Bestätigen" button becomes **disabled** again. |
| D-08 | Check checkbox, then click "Bestätigen" | Modal disappears. App becomes visible. `legal_disclaimer_accepted_v1` is written to localStorage with `version` and `timestamp`. |
| D-09 | Verify localStorage after acceptance | Key `legal_disclaimer_accepted_v1` exists with JSON: `{"version": "<server_version>", "timestamp": "<ISO8601>", "ip_hash": ""}`. Key `legal_disclaimer_version_v1` equals the version string. |

### 2.2 Subsequent Visits — Same Version

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-10 | Reload page after accepting disclaimer (same server version) | Disclaimer modal does **not** appear. App loads directly. |
| D-11 | Verify `X-Disclaimer-Ack` header | All API requests include `X-Disclaimer-Ack` header with the stored version. |

### 2.3 Version Mismatch

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-12 | Manually change `legal_disclaimer_version_v1` in localStorage to a different value, then reload | Disclaimer modal appears again. Old localStorage keys are cleared. |
| D-13 | Server returns new disclaimer version (simulate by changing server-side version) | On next page load, `checkDisclaimerStatus()` detects mismatch, clears localStorage, shows modal. |

### 2.4 API Failure During Disclaimer Check

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-14 | Block `/api/v1/meta/disclaimer/version` (e.g., stop backend), then reload | `checkDisclaimerStatus()` catches error, returns `false`. Disclaimer modal appears. |
| D-15 | Block `/api/v1/meta/disclaimer/text`, then load modal | Disclaimer text area shows "Fehler beim Laden des Disclaimer-Textes." |

### 2.5 403 Mid-Session

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-16 | Accept disclaimer, then manually clear localStorage, then trigger any API call | Server returns 403 with `disclaimer_required`. `handleApiError()` clears localStorage, shows disclaimer modal, throws error. |
| D-17 | Accept disclaimer, change version in localStorage to mismatch, trigger API call | Server returns 403 with `disclaimer_version_mismatch`. Same behavior as D-16. |

### 2.6 Modal Visual States

| ID | Action | Expected Result |
|----|--------|-----------------|
| D-18 | Resize browser to <640px width with modal open | Modal content padding reduces. Still scrollable if content overflows. |
| D-19 | Modal with very long disclaimer text | Text area scrolls internally (`max-height: 300px`, `overflow-y: auto`). Modal itself scrolls if needed (`max-height: 85vh`). |

---

## 3. Mode Toggle

### 3.1 Initial State

| ID | Action | Expected Result |
|----|--------|-----------------|
| M-01 | App loads for the first time (after disclaimer) | Default mode is "Analysieren". Analyze mode is visible, Chat mode is hidden. "Analysieren" button has `.active` class. |
| M-02 | Observe mode toggle buttons | Two buttons in header: "Analysieren" (with document icon) and "Chat" (with speech bubble icon). "Analysieren" is highlighted (white background, white text). "Chat" is semi-transparent. |

### 3.2 Switching to Chat Mode

| ID | Action | Expected Result |
|----|--------|-----------------|
| M-03 | Click "Chat" button | Analyze mode hides. Chat mode appears. "Chat" button becomes active. "Analysieren" button becomes inactive. |
| M-04 | First switch to Chat mode | Conversations are loaded from `GET /api/v1/conversations`. Sidebar renders conversation list or empty state. |
| M-05 | Switch to Chat mode again (conversations already loaded) | Conversations are **not** re-fetched (`state.conversations.length > 0` check). |

### 3.3 Switching Back to Analyze Mode

| ID | Action | Expected Result |
|----|--------|-----------------|
| M-06 | Click "Analysieren" button | Chat mode hides. Analyze mode appears. "Analysieren" button becomes active. |
| M-07 | Switch back to Analyze mode while a chat stream is active | Mode switch still works (no guard against switching during streaming — test this). Analyze mode state is preserved (file, extracted text, etc.). |

### 3.4 Repeated Toggling

| ID | Action | Expected Result |
|----|--------|-----------------|
| M-08 | Rapidly click between modes 5+ times | No visual glitches. Only the target mode is visible. No duplicate event listeners. |
| M-09 | Click the already-active mode button | `switchMode()` returns early (`if (mode === state.currentMode) return`). Nothing changes. |

### 3.5 Mobile Mode Toggle

| ID | Action | Expected Result |
|----|--------|-----------------|
| M-10 | Resize to <640px width | Header layout stacks vertically. Mode toggle buttons center-align. |

---

## 4. Analyze Mode — File Upload

### 4.1 Upload Area — Visual States

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-01 | Observe upload area on load | Dashed border, light background. Contains upload icon, "PDF, JPG oder PNG hier ablegen oder klicken", "Max. 25 MB". |
| U-02 | Hover over upload area | Border color changes to primary blue. Background gets subtle blue tint. |
| U-03 | Observe "Text extrahieren" button | Button is **disabled** (no file selected). Full width, primary color but greyed out. |

### 4.2 File Selection — Click

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-04 | Click the upload area | Native file picker opens. Only `.pdf`, `.jpg`, `.jpeg`, `.png` files are selectable. |
| U-05 | Select a valid PDF (<25 MB) | File info bar appears showing filename + "Entfernen" button. "Text extrahieren" button enables. |
| U-06 | Select a valid JPG | Same as U-05. |
| U-07 | Select a valid PNG | Same as U-05. |

### 4.3 File Selection — Drag & Drop

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-08 | Drag a valid PDF over the upload area | `dragover` event prevented. No visual change (no drag-over class on analyze mode upload area). |
| U-09 | Drop a valid PDF on the upload area | File is accepted. File info bar appears. Button enables. |
| U-10 | Drop a file outside the upload area | Browser default behavior (opens file in new tab or downloads). File is NOT processed. |

### 4.4 File Validation — Size

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-11 | Select a file >25 MB | Error message appears: "Datei zu groß. Maximale Größe ist 25 MB." File is rejected. State unchanged. |
| U-12 | Select a file exactly 25 MB (25,000,000 bytes) | File is accepted (check is `file.size > maxSize`, so exactly 25MB passes). |
| U-13 | Select a file at 25,000,001 bytes | File is rejected with size error. |

### 4.5 File Validation — Type

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-14 | Select a `.txt` file | Error: "Ungültiger Dateityp. Erlaubt: PDF, JPG, PNG." |
| U-15 | Select a `.docx` file | Same error as U-14. |
| U-16 | Select a file with no extension | Depends on MIME type detection. If MIME is not in allowed list, rejected. |
| U-17 | Select a `.PDF` (uppercase) file | Depends on OS MIME type. On Linux, may be `application/pdf` and accepted. Test this. |

### 4.6 File Removal

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-18 | Select a file, then click "Entfernen" | File info bar hides. File input cleared. "Text extrahieren" button disables. Button text resets to "Text extrahieren". |
| U-19 | Remove file after extraction | Same as U-18, plus: analysis section hides, results section hides, `state.extractedText` and `state.hasExtracted` reset. |
| U-20 | Select a new file without removing old one | Old file is replaced. File info updates to new filename. |

### 4.7 Upload Button States

| ID | Action | Expected Result |
|----|--------|-----------------|
| U-21 | Button text before any extraction | "Text extrahieren" |
| U-22 | Button text during extraction | "Wird extrahiert..." (first time) or "Wird erneut extrahiert..." (subsequent) |
| U-23 | Button text after successful extraction | "Erneut extrahieren" |
| U-24 | Button disabled during extraction | Yes, `elements.uploadBtn.disabled = true` |
| U-25 | Button after extraction error | Re-enabled. Text shows "Text extrahieren" (if `hasExtracted` is false) or "Erneut extrahieren" (if true). |

---

## 5. Analyze Mode — Corpus Management

### 5.1 Initial State

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-01 | Observe Corpus section | Title "Corpus-Verwaltung". Description text about local legal corpus. Three-step list (Scraping, Embedding, Speicherung). "Corpus aktualisieren" button. |
| C-02 | Progress bar and result area | Both hidden on initial load. |

### 5.2 Starting Corpus Update

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-03 | Click "Corpus aktualisieren" | Button disables, text changes to "Corpus-Aktualisierung läuft …". Progress bar appears. Substage text: "Auftrag wird eingereiht …". |
| C-04 | Click button again while update is running | `handleCorpusUpdate()` returns early (`if (state.corpusJobId) return`). Nothing happens. |
| C-05 | Observe POST request | `POST /api/v1/corpus/update` is sent. Response contains `job_id`. |

### 5.3 Polling Progress

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-06 | After job starts, observe polling | `GET /api/v1/corpus/status/{job_id}` called every 2 seconds. |
| C-07 | Scraping substage | Substage text: "Rechtsquellen werden abgerufen und aufbereitet …". If `chunks_scraped > 0`: "N Textblöcke bisher abgerufen". Progress bar shows indeterminate animation (shimmer). |
| C-08 | Embedding substage | Substage text: "Vektordarstellungen (Embeddings) werden generiert …". If chunks: "N Textblöcke werden verarbeitet". |
| C-09 | Upserting substage | Substage text: "Einträge werden in der Datenbank gespeichert …". If chunks: "N Textblöcke in DB". |
| C-10 | Unknown substage | Substage text does not change (no matching label in `substageLabels`). |

### 5.4 Corpus Update — Success

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-11 | Update completes with `chunks_processed > 0` | Progress bar hides. Green success message: "Corpus-Aktualisierung abgeschlossen: N Texteinträge wurden verarbeitet und gespeichert." Button re-enables, text: "Corpus aktualisieren". |
| C-12 | Update completes with `chunks_processed === 0` | Yellow warning message: "Corpus-Aktualisierung abgeschlossen, aber es wurden keine Einträge gefunden. Bitte prüfen Sie die Netzwerkverbindung und die Verfügbarkeit von gesetze-im-internet.de." |

### 5.5 Corpus Update — Failure

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-13 | Update fails (server error) | Red error message: "Corpus-Aktualisierung fehlgeschlagen: <error message>". Button re-enables. |
| C-14 | Polling returns 404 (job not found) | Error: "Auftrag nicht mehr im Speicher — bitte erneut versuchen." |
| C-15 | Network error during polling | `showCorpusError()` called with error message. Red error displayed. Button re-enables. |
| C-16 | Network error during initial POST | `showCorpusError()` called. Red error displayed. |

### 5.6 Corpus Update — Timer Cleanup

| ID | Action | Expected Result |
|----|--------|-----------------|
| C-17 | Start update, then navigate away (switch modes) | Polling continues (no cleanup on mode switch). Test if this causes issues. |
| C-18 | Start update, then start another update (after first completes) | New `jobId` is set. Old polling timer is cleared via `clearTimeout`. |

---

## 6. Analyze Mode — Text Extraction (OCR)

### 6.1 Successful Extraction

| ID | Action | Expected Result |
|----|--------|-----------------|
| E-01 | Upload a PDF with text, click "Text extrahieren" | `POST /api/v1/ingest` sent with file as FormData. Button shows "Wird extrahiert..." during request. |
| E-02 | After successful extraction | Analysis section appears. Text preview shows first 500 characters + "(N Zeichen extrahiert — Vorschau zeigt erste 500)". Button text: "Erneut extrahieren". |
| E-03 | Text preview scrollability | If extracted text >500 chars, preview area scrolls (`max-height: 200px`, `overflow-y: auto`). |
| E-04 | Extract same file again | Button shows "Wird erneut extrahiert...". New extraction replaces old `extractedText`. |

### 6.2 Extraction — Empty Result

| ID | Action | Expected Result |
|----|--------|-----------------|
| E-05 | Upload a PDF with no extractable text (image-only without OCR) | Depends on OCR pipeline. If text is empty string, preview shows empty with "0 Zeichen extrahiert". |

### 6.3 Extraction — API Errors

| ID | Action | Expected Result |
|----|--------|-----------------|
| E-06 | Backend returns 4xx/5xx | Error message displayed in error display area. Button re-enables. |
| E-07 | Network failure during upload | `fetch` throws. Error caught in catch block. Error message displayed. |
| E-08 | Backend returns 403 (disclaimer) | `handleApiError` triggers disclaimer modal. |

---

## 7. Analyze Mode — Analysis Pipeline

### 7.1 Starting Analysis

| ID | Action | Expected Result |
|----|--------|-----------------|
| A-01 | Click "Analyse starten" after extraction | Analysis section hides. Progress section appears. All 7 stages show `○` icon. Progress bar at 0%. |
| A-02 | Click "Analyse starten" without extraction | `handleAnalyze()` returns early (`if (!state.extractedText) return`). Nothing happens. |
| A-03 | Click "Analyse starten" twice rapidly | First click starts analysis. Second click: button is in hidden section, so not clickable. |

### 7.2 SSE Stream — Stage Progression

| ID | Action | Expected Result |
|----|--------|-----------------|
| A-04 | Stage "normalization" starts (`status: "running"`) | Stage icon changes to `◐` (pulsing animation). Stage gets `.active` class. Progress bar moves to ~14%. |
| A-05 | Stage "normalization" completes (`status: "complete"`) | Icon changes to `✓` (green). Stage gets `.complete` class. |
| A-06 | Stage "classification" runs | Icon `◐`, active class. Progress ~29%. |
| A-07 | Stage "decomposition" runs | Icon `◐`, active class. Progress ~43%. |
| A-08 | Stage "retrieval" runs | Icon `◐`, active class. Progress ~57%. |
| A-09 | Stage "claims" runs | Icon `◐`, active class. Progress ~71%. |
| A-10 | Stage "verification" runs | Icon `◐`, active class. Progress ~86%. |
| A-11 | Stage "generation" runs | Icon `◐`, active class. Progress ~100%. |
| A-12 | All stages complete | All 7 stages show `✓` (green). Progress bar at 100%. |

### 7.3 SSE Stream — Error During Pipeline

| ID | Action | Expected Result |
|----|--------|-----------------|
| A-13 | Server sends `{"error": true, "detail": "..."}` | Error display shows the detail message. Progress section hides. Analysis section re-appears. |
| A-14 | Network drops mid-stream | `reader.read()` throws. Error caught. Progress hides, analysis section re-appears. |
| A-15 | Server sends malformed JSON in SSE | `JSON.parse` fails. Error logged to console. Stream continues (event skipped). |

### 7.4 SSE Stream — Edge Cases

| ID | Action | Expected Result |
|----|--------|-----------------|
| A-16 | Server sends event with unknown stage name | `querySelector` returns null. Event is silently ignored. |
| A-17 | Server sends event with no `stage` field and no `final_output` | Event is ignored (no matching condition in `handleSSEEvent`). |
| A-18 | Server sends `final_output` before all stages complete | Results render immediately. Progress section hides. Remaining stage events (if any) are ignored (progress section is hidden). |
| A-19 | Server sends multiple `final_output` events | `resultsContainer.innerHTML = ''` clears previous. Only last output is shown. |

---

## 8. Analyze Mode — Results Display

### 8.1 Results Rendering

| ID | Action | Expected Result |
|----|--------|-----------------|
| R-01 | After pipeline completes | Results section appears. 6 result sections rendered in order: Sachverhalt, Rechtliche Würdigung, Ergebnis, Handlungsempfehlung, Entwurf, Unsicherheiten. |
| R-02 | Each result section | Has a colored left border (4px primary blue). Title in primary blue with bottom border. Content area with `white-space: pre-wrap`. |
| R-03 | Section with empty/missing content | Shows "—" (em-dash). |
| R-04 | Section with multi-line content | Line breaks preserved (`\n` → `<br>`). HTML escaped. |
| R-05 | Section with HTML-like content | Content is escaped (e.g., `<script>` renders as text, not executed). |

### 8.2 Results — Re-analysis

| ID | Action | Expected Result |
|----|--------|-----------------|
| R-06 | Click "Erneut extrahieren" then "Analyse starten" | Old results cleared. New pipeline runs. New results replace old. |
| R-07 | Remove file, upload new file, extract, analyze | Old results cleared during file removal. New results for new document. |

---

## 9. Analyze Mode — Error Handling

### 9.1 Error Display

| ID | Action | Expected Result |
|----|--------|-----------------|
| ER-01 | Any error occurs | Red error box appears below sections. Contains error message text. |
| ER-02 | Error is cleared (`showError(null)`) | Error box hides. |
| ER-03 | New error replaces old error | Error box content updates. Box remains visible. |
| ER-04 | Error with special characters | Text is set via `textContent`, so HTML-safe. |

### 9.2 Error Recovery

| ID | Action | Expected Result |
|----|--------|-----------------|
| ER-05 | Upload fails → fix issue → upload again | Error clears on new upload attempt (`showError(null)` at start of `handleUpload`). |
| ER-06 | Analysis fails → fix issue → analyze again | Error clears on new analysis attempt. |

---

## 10. Chat Mode — Sidebar & Conversation List

### 10.1 Initial Load

| ID | Action | Expected Result |
|----|--------|-----------------|
| S-01 | Switch to Chat mode with no conversations | Sidebar shows "Neue Unterhaltung" button at top. Empty state: chat icon + "Noch keine Unterhaltungen". |
| S-02 | Switch to Chat mode with existing conversations | Conversation list renders. Each item shows: title (truncated to 30 chars + …), relative date, optional message preview (truncated to 55 chars). |
| S-03 | Conversation list sort order | Most recently updated first (`updated_at` descending). |

### 10.2 Conversation List — Loading Error

| ID | Action | Expected Result |
|----|--------|-----------------|
| S-04 | `GET /api/v1/conversations` fails | Error message appears in sidebar: "Fehler beim Laden der Unterhaltungen." (red text). |
| S-05 | Error state → successful reload | Error hides. List renders normally. |

### 10.3 Conversation List — Visual States

| ID | Action | Expected Result |
|----|--------|-----------------|
| S-06 | Hover over conversation item | Background changes to `--chat-surface-hover`. |
| S-07 | Active conversation item | Blue left border. Background `--chat-surface-active`. |
| S-08 | Very long conversation title | Truncated with `…` (via CSS `text-overflow: ellipsis`). |
| S-09 | Conversation with no title | Shows "Unterhaltung" as fallback. |

### 10.4 Conversation List — Scroll

| ID | Action | Expected Result |
|----|--------|-----------------|
| S-10 | 50+ conversations in list | List scrolls internally. Custom scrollbar (4px, dark). "Neue Unterhaltung" button stays fixed at top. |

---

## 11. Chat Mode — New Conversation

### 11.1 Creating with Title

| ID | Action | Expected Result |
|----|--------|-----------------|
| N-01 | Click "Neue Unterhaltung" | Native `prompt()` dialog appears: "Titel der Unterhaltung (optional):". |
| N-02 | Enter a title, click OK | `POST /api/v1/conversations` sent with title as FormData. New conversation appears at top of list. Automatically selected. |
| N-03 | Title appears in chat header | Chat header shows the entered title. Document title updates to "Citizen — <title>". |
| N-04 | Chat input enables | Textarea becomes enabled. Send button still disabled (empty input). |

### 11.2 Creating without Title

| ID | Action | Expected Result |
|----|--------|-----------------|
| N-05 | Click "Neue Unterhaltung", leave prompt empty, click OK | Title defaults to "Unterhaltung". Conversation created with this title. |
| N-06 | Click "Neue Unterhaltung", enter only whitespace, click OK | `title.trim()` is empty. Title defaults to "Unterhaltung". |
| N-07 | Click "Neue Unterhaltung", click Cancel | `prompt()` returns `null`. `finalTitle` becomes "Unterhaltung". Conversation is still created. |

### 11.3 Creation Failure

| ID | Action | Expected Result |
|----|--------|-----------------|
| N-08 | Backend returns error on create | Error toast appears in chat: "Fehler beim Erstellen der Unterhaltung." Button re-enables. No conversation added to list. |
| N-09 | Network error on create | Same as N-08. |

### 11.4 Button State During Creation

| ID | Action | Expected Result |
|----|--------|-----------------|
| N-10 | Click "Neue Unterhaltung", observe button during request | Button is disabled (`elements.newConversationBtn.disabled = true`). |
| N-11 | After creation completes (success or failure) | Button re-enables. |

---

## 12. Chat Mode — Conversation Selection

### 12.1 Selecting a Conversation

| ID | Action | Expected Result |
|----|--------|-----------------|
| CS-01 | Click a conversation in the sidebar | `GET /api/v1/conversations/{id}` fetches full detail. Messages render in chat area. Documents render as chips. Chat title updates. Delete button appears. Input enables. |
| CS-02 | Click the already-active conversation | `selectConversation()` returns early. No API call. Nothing changes. |
| CS-03 | Select conversation with many messages | All messages render. Chat scrolls to bottom. |
| CS-04 | Select conversation with no messages | Empty state appears: microphone icon + "Starten Sie eine neue Unterhaltung" + "oder wählen Sie eine bestehende aus". |
| CS-05 | Select conversation with documents | Document chips appear above input area. |

### 12.2 Selection — Sidebar Update

| ID | Action | Expected Result |
|----|--------|-----------------|
| CS-06 | After selecting, sidebar highlights the active item | Active conversation gets `.active` class (blue border). |
| CS-07 | Select different conversation | Previous loses `.active`. New gets `.active`. |

### 12.3 Selection — Mobile Sidebar

| ID | Action | Expected Result |
|----|--------|-----------------|
| CS-08 | On mobile (<768px), select a conversation | Sidebar closes automatically (`closeSidebar()` called). |

### 12.4 Selection Failure

| ID | Action | Expected Result |
|----|--------|-----------------|
| CS-09 | Backend returns error on conversation detail fetch | Error toast: "Fehler beim Laden der Unterhaltung." Chat area unchanged. |
| CS-10 | Conversation was deleted by another session | Error from API. Error toast shown. |

---

## 13. Chat Mode — Conversation Deletion

### 13.1 Delete Flow

| ID | Action | Expected Result |
|----|--------|-----------------|
| CD-01 | Select a conversation, observe delete button | Trash icon button appears in chat header (right side). |
| CD-02 | No conversation selected | Delete button is hidden (`.hidden` class). |
| CD-03 | Click delete button | Native `confirm()` dialog: "Möchten Sie diese Unterhaltung wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden." |
| CD-04 | Click "Cancel" on confirm dialog | Nothing happens. Conversation remains. |
| CD-05 | Click "OK" on confirm dialog | `DELETE /api/v1/conversations/{id}` sent. Conversation removed from list. Chat area resets to empty state. |

### 13.2 After Deletion — State Reset

| ID | Action | Expected Result |
|----|--------|-----------------|
| CD-06 | Verify chat area after deletion | Messages cleared. Empty state shown. Title: "Citizen Chat". Delete button hidden. Input disabled. Send button disabled. Document chips hidden. Document title: "Citizen — Legal Reasoning Engine". |
| CD-07 | Verify sidebar after deletion | Conversation removed from list. If no conversations remain, empty state shown. |
| CD-08 | Verify state after deletion | `activeConversationId = null`, `conversationDocuments = []`, `isStreaming = false`. |

### 13.3 Delete — Edge Cases

| ID | Action | Expected Result |
|----|--------|-----------------|
| CD-09 | Delete the only conversation | Sidebar shows empty state. Chat area shows empty state. |
| CD-10 | Delete a conversation while it's streaming | `isStreaming` is reset to false. AbortController is NOT aborted (no guard). Test if this causes issues. |
| CD-11 | Delete fails (API error) | Error toast: "Fehler beim Löschen der Unterhaltung." Conversation remains. |

---

## 14. Chat Mode — Message Sending

### 14.1 Input Area — Visual States

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-01 | No conversation selected | Textarea is **disabled** (`disabled` attribute). Placeholder: "Nachricht eingeben...". Send button disabled. Attach button enabled. |
| MS-02 | Conversation selected, input empty | Textarea enabled. Send button **disabled** (grey, `opacity: 0.4`). |
| MS-03 | Conversation selected, input has text | Send button **enabled** (blue, full opacity). |
| MS-04 | During streaming | Textarea disabled. Send button disabled. Attach button disabled. |

### 14.2 Input Area — Auto-resize

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-05 | Type a single line | Textarea stays at 1 row height. |
| MS-06 | Type multiple lines | Textarea grows up to `max-height: 150px`, then scrolls internally. |
| MS-07 | Paste a long text | Textarea resizes to fit (up to 150px). |
| MS-08 | Delete text to make it shorter | Textarea shrinks back down. |

### 14.3 Input Area — Keyboard

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-09 | Press Enter (no Shift) | Message sends. Newline is NOT inserted. |
| MS-10 | Press Shift+Enter | Newline inserted. Message does NOT send. |
| MS-11 | Press Enter with empty input | `sendMessage()` returns early (trim check). Nothing happens. |
| MS-12 | Press Enter during streaming | `sendMessage()` returns early (`isStreaming` check). Nothing happens. |

### 14.4 Send Button

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-13 | Click send button with text | Message sends. Same as Enter key. |
| MS-14 | Click send button with empty input | `handleChatSend()` checks `value.trim()`. Nothing happens. |
| MS-15 | Click send button during streaming | `handleChatSend()` checks `isStreaming`. Nothing happens. |

### 14.5 Auto-Create Conversation on First Message

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-16 | With no conversation selected, type a message and send | Conversation auto-created. Title is first 40 chars of message + "…" (if >40 chars). Then message sends. |
| MS-17 | Auto-created conversation appears in sidebar | Added to top of list. Selected as active. |
| MS-18 | Auto-create fails | Input re-enables. Send button re-enables. Error shown. No message sent. |
| MS-19 | Message ≤40 chars as auto-title | Full message used as title (no truncation). |

### 14.6 Message Sending — Immediate UI

| ID | Action | Expected Result |
|----|--------|-----------------|
| MS-20 | Send a message | User message bubble appears immediately (right-aligned, blue). Input clears. Input height resets to auto. |
| MS-21 | After user message | Assistant placeholder appears with typing indicator (3 bouncing dots). |
| MS-22 | Chat scrolls to bottom | After user message and after assistant placeholder. |

---

## 15. Chat Mode — SSE Streaming (Chat+RAG Mode)

### 15.1 Token Streaming

| ID | Action | Expected Result |
|----|--------|-----------------|
| ST-01 | Send a message (no documents attached, not first message) | `POST /api/v1/conversations/{id}/messages` sent. SSE stream starts. |
| ST-02 | First token arrives (`type: "token"`) | Typing indicator removed. Content starts appearing in assistant bubble. |
| ST-03 | Subsequent tokens | Content appends in real-time. Bubble updates with `formatMessageContent()`. Chat scrolls to bottom on each token. |
| ST-04 | Bold formatting (`**text**`) | Renders as `<strong>` with accent color. |
| ST-05 | Italic formatting (`*text*`) | Renders as `<em>` with muted color. |
| ST-06 | Line breaks in content | Rendered as `<br>`. |
| ST-07 | HTML in content | Escaped (e.g., `<script>` shown as text). |

### 15.2 Stream Completion

| ID | Action | Expected Result |
|----|--------|-----------------|
| ST-08 | `type: "done"` event with `full_response` | Bubble content replaced with final formatted version. Timestamp added below bubble. |
| ST-09 | `type: "done"` without `full_response` | Bubble keeps streamed content. Timestamp added. |
| ST-10 | After stream completes | Input re-enables. Send button re-enables. Attach button re-enables. Input focused. Conversation list refreshed (updates timestamps). |

### 15.3 Stream — Error Events

| ID | Action | Expected Result |
|----|--------|-----------------|
| ST-11 | Server sends `{"error": true, "detail": "..."}` | Bubble content replaced with red error box: "Fehler: <detail>". |
| ST-12 | Network drops mid-stream | `fetch` throws. If typing indicator still present, replaced with error: "Fehler: <message>". |
| ST-13 | User aborts stream (if AbortController used) | `AbortError` caught. Stream stops silently. Input re-enables. |

### 15.4 Stream — Malformed Data

| ID | Action | Expected Result |
|----|--------|-----------------|
| ST-14 | Server sends non-JSON after `data: ` | `JSON.parse` fails. Error logged to console. Event skipped. Stream continues. |
| ST-15 | Server sends empty `data: ` line | Skipped (`if (!dataStr) continue`). |
| ST-16 | Line without `data: ` prefix | Skipped. |

---

## 16. Chat Mode — SSE Streaming (Pipeline Mode)

Pipeline mode triggers when the **first message** in a conversation has documents attached.

### 16.1 Pipeline Stage Events

| ID | Action | Expected Result |
|----|--------|-----------------|
| PL-01 | Send first message with document(s) attached | Typing indicator replaced by pipeline progress UI: progress bar + stage label. |
| PL-02 | Stage `running` event | Label updates: "<StageName> wird ausgeführt …". |
| PL-03 | Stage `complete` event | Progress bar fills proportionally. Label: "<StageName> abgeschlossen (N/7)". |
| PL-04 | All 7 stages complete | Progress bar at 100%. Label shows last stage completed. |

### 16.2 Pipeline Final Output

| ID | Action | Expected Result |
|----|--------|-----------------|
| PL-05 | `final_output` event arrives | Pipeline progress replaced by collapsible result sections. 6 sections rendered. |
| PL-06 | First section is open by default | "Sachverhalt" section shows `▶` arrow rotated 90°, body visible. |
| PL-07 | Other sections are collapsed | Arrow pointing right (`▶`), body hidden (`max-height: 0`). |
| PL-08 | Click a collapsed section header | Section expands (arrow rotates, body slides down). |
| PL-09 | Click an expanded section header | Section collapses (arrow rotates back, body slides up). |
| PL-10 | Multiple sections open simultaneously | All independently toggleable. |
| PL-11 | Section with empty content | Shows "—". |

### 16.3 Pipeline → Chat Transition

| ID | Action | Expected Result |
|----|--------|-----------------|
| PL-12 | After pipeline completes, send another message (no new docs) | Second message uses Chat+RAG mode (token streaming, not pipeline). |
| PL-13 | After pipeline, send message with new docs | Should use pipeline mode again (depends on backend logic). Test this. |

---

## 17. Chat Mode — Document Upload

### 17.1 Attach Button

| ID | Action | Expected Result |
|----|--------|-----------------|
| DU-01 | Click attach button with active conversation | Native file picker opens. Accepts `.pdf,.jpg,.jpeg,.png`. Multiple files allowed. |
| DU-02 | Click attach button with no active conversation | Error toast: "Bitte erst eine Unterhaltung auswählen oder erstellen." File picker does NOT open. |
| DU-03 | Attach button during streaming | Button is disabled. Click does nothing. |

### 17.2 File Selection for Chat

| ID | Action | Expected Result |
|----|--------|-----------------|
| DU-04 | Select one valid file | Uploading chip appears (pulsing animation). `POST /api/v1/conversations/{id}/documents` sent. |
| DU-05 | Select multiple valid files | Multiple chips appear. Files uploaded sequentially (`for...of` with `await`). |
| DU-06 | Select file >25 MB | Error toast: `Datei "<name>" zu groß (max. 25 MB).` File skipped. |
| DU-07 | Select invalid file type | Error toast: `Datei "<name>" hat ungültigen Typ. Erlaubt: PDF, JPG, PNG.` File skipped. |
| DU-08 | Mix of valid and invalid files | Valid files upload. Invalid files show individual errors. |

### 17.3 Upload Success

| ID | Action | Expected Result |
|----|--------|-----------------|
| DU-09 | Upload completes | Uploading chip replaced by normal chip (with remove button). System message appears: "Dokument '<name>' wurde hinzugefügt". |
| DU-10 | Document added to state | `state.conversationDocuments` includes the new document. |

### 17.4 Upload Failure

| ID | Action | Expected Result |
|----|--------|-----------------|
| DU-11 | Upload fails (API error) | Error toast: "Fehler beim Hochladen des Dokuments: <message>". Uploading chip removed. |
| DU-12 | Upload fails (network error) | Same as DU-11. |

---

## 18. Chat Mode — Document Chips

### 18.1 Chip Display

| ID | Action | Expected Result |
|----|--------|-----------------|
| DC-01 | Conversation has documents | Chip bar appears above input area. Each chip shows: document icon, filename (truncated to 160px), × remove button. |
| DC-02 | No documents | Chip bar hidden. |
| DC-03 | Many documents | Chips wrap to multiple lines (`flex-wrap: wrap`). |

### 18.2 Chip — Remove

| ID | Action | Expected Result |
|----|--------|-----------------|
| DC-04 | Click × on a chip | `DELETE /api/v1/conversations/{id}/documents/{docId}` sent. Chip removed from bar. |
| DC-05 | Remove last document | Chip bar hides. |
| DC-06 | Remove fails (API error) | Error toast: "Fehler beim Entfernen des Dokuments." Chip remains. |

### 18.3 Chip — Visual States

| ID | Action | Expected Result |
|----|--------|-----------------|
| DC-07 | Hover over chip | Border turns blue. Background darkens. |
| DC-08 | Hover over × button | Button background turns red (semi-transparent). × turns red. |
| DC-09 | Uploading chip | Pulsing animation (`opacity` oscillates 0.6–1.0). No remove button. |

---

## 19. Chat Mode — Drag & Drop

### 19.1 Drag Over Chat Area

| ID | Action | Expected Result |
|----|--------|-----------------|
| DD-01 | Drag a file over the chat messages area | Chat area gets blue dashed outline (`outline: 2px dashed`). Background gets subtle blue tint. |
| DD-02 | Drag file away from chat area | Visual indicators removed. |
| DD-03 | Drag file from outside chat area to inside, then back out | Indicators appear then disappear. |

### 19.2 Drop on Chat Area

| ID | Action | Expected Result |
|----|--------|-----------------|
| DD-04 | Drop a file with active conversation | File uploads via `uploadChatDocument()`. Same flow as attach button. |
| DD-05 | Drop a file with no active conversation | Error toast: "Bitte erst eine Unterhaltung auswählen oder erstellen." File NOT uploaded. |
| DD-06 | Drop multiple files | All files uploaded sequentially. |
| DD-07 | Drop during streaming | `uploadChatDocument` is called. Test if this should be blocked (no guard in drop handler). |

---

## 20. Chat Mode — Error Handling

### 20.1 Error Toast

| ID | Action | Expected Result |
|----|--------|-----------------|
| CE-01 | Any chat error occurs | Red error box appears at bottom of messages. |
| CE-02 | Error auto-dismiss | Error disappears after 6 seconds. |
| CE-03 | Multiple errors in quick succession | Each creates a new error div. All auto-dismiss independently. |
| CE-04 | Error while scrolled up | Error appears at bottom. Chat does NOT auto-scroll (scrollToBottom is called but user may have scrolled up). |

### 20.2 Inline Error (in Assistant Bubble)

| ID | Action | Expected Result |
|----|--------|-----------------|
| CE-05 | SSE stream error | Assistant bubble shows red error box instead of content. |
| CE-06 | API error during message send | If typing indicator still present, replaced with error. Otherwise error toast shown. |

---

## 21. Cross-Cutting Concerns

### 21.1 localStorage Persistence

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-01 | Accept disclaimer, close tab, reopen | Disclaimer not shown again (same version). |
| CC-02 | Clear all localStorage, reload | Disclaimer modal appears. |
| CC-03 | Corrupted localStorage JSON | `JSON.parse` fails in `checkDisclaimerStatus()`. Returns `false`. Modal appears. |
| CC-04 | `getDisclaimerAckHeader()` with corrupted data | Returns `null`. Header not sent. |

### 21.2 Rate Limiting

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-05 | Send 60+ requests in 60 seconds | Backend returns 429. Observe UI behavior (no special 429 handling in frontend — falls through to generic error). |
| CC-06 | Rate limit error message | Generic error display or toast with HTTP status text. |

### 21.3 API Base Path

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-07 | All API calls use `/api/v1/` prefix | Verify in Network tab. |
| CC-08 | Static files served from `/static/` | CSS and JS load correctly. |

### 21.4 Keyboard Shortcuts

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-09 | Press Escape in Chat mode | Sidebar closes (mobile). |
| CC-10 | Press Escape in Analyze mode | Nothing happens (listener only active in chat mode). |
| CC-11 | Press Escape with sidebar already closed | `closeSidebar()` called. No-op. |

### 21.5 Console Errors

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-12 | Normal operation | No console errors. |
| CC-13 | Network offline during operation | Errors caught and displayed. No uncaught exceptions. |

### 21.6 Memory Leaks

| ID | Action | Expected Result |
|----|--------|-----------------|
| CC-14 | Create and delete 20 conversations | No memory growth. Event listeners cleaned up. |
| CC-15 | Rapid mode switching 50 times | No duplicate event listeners. No memory growth. |
| CC-16 | Corpus polling timer on page unload | Timer is NOT cleared on page unload (potential issue). Test if this causes problems. |

---

## 22. Responsive Design

### 22.1 Breakpoint: 768px (Chat Mode)

| ID | Action | Expected Result |
|----|--------|-----------------|
| RD-01 | Resize to 767px width in Chat mode | Sidebar slides off-screen (`transform: translateX(-100%)`). Hamburger menu button appears in chat header. |
| RD-02 | Click hamburger menu button | Sidebar slides in from left (`transform: translateX(0)`). Dark overlay appears behind sidebar. |
| RD-03 | Click overlay | Sidebar closes. Overlay hides. |
| RD-04 | Press Escape | Sidebar closes. Overlay hides. |
| RD-05 | Select conversation on mobile | Sidebar auto-closes. |
| RD-06 | Message bubbles at 768px | Max width 90% (vs 75% on desktop). |
| RD-07 | Resize back to 769px | Sidebar visible again. Hamburger button hides (`display: none`). |

### 22.2 Breakpoint: 640px (Analyze Mode)

| ID | Action | Expected Result |
|----|--------|-----------------|
| RD-08 | Resize to 639px in Analyze mode | Header stacks vertically. Mode toggle centers. Font sizes reduce. Stage list becomes single column. |
| RD-09 | Modal at 639px | Padding reduces. |

### 22.3 Breakpoint: 480px (Chat Mode)

| ID | Action | Expected Result |
|----|--------|-----------------|
| RD-10 | Resize to 479px in Chat mode | Message bubbles max 95% width. Chat title font smaller. Document chip names truncated to 100px. |

### 22.4 Input Area — Focus State

| ID | Action | Expected Result |
|----|--------|-----------------|
| RD-11 | Focus the chat textarea | Input container border turns blue (`--chat-primary`). |

---

## 23. Browser Compatibility

Test on:
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)
- [ ] Mobile Chrome (Android)
- [ ] Mobile Safari (iOS)

Key areas to verify per browser:
- SSE streaming (`ReadableStream`, `getReader`)
- `AbortController`
- `FormData` uploads
- CSS custom properties
- CSS animations (pulse, typing-bounce, shimmer, message-appear)
- `text-overflow: ellipsis`
- Flexbox layout
- `position: fixed` sidebar on mobile
- `prompt()` and `confirm()` native dialogs

---

## 24. Quick Smoke Test Checklist

Run these 20 tests for a basic confidence check:

- [ ] **SMK-01:** First visit → disclaimer modal → check checkbox → acknowledge → app loads
- [ ] **SMK-02:** Reload page → no disclaimer (already accepted)
- [ ] **SMK-03:** Switch to Chat mode → sidebar loads conversations
- [ ] **SMK-04:** Switch back to Analyze mode → UI intact
- [ ] **SMK-05:** Upload a PDF via click → file info appears → button enables
- [ ] **SMK-06:** Upload a PDF via drag & drop → same result
- [ ] **SMK-07:** Try uploading a .txt file → error message
- [ ] **SMK-08:** Try uploading a >25MB file → error message
- [ ] **SMK-09:** Click "Text extrahieren" → preview appears → button changes to "Erneut extrahieren"
- [ ] **SMK-10:** Click "Analyse starten" → 7-stage progress → results appear
- [ ] **SMK-11:** Click "Corpus aktualisieren" → progress bar → success/error message
- [ ] **SMK-12:** Create new chat conversation with title → appears in sidebar → selected
- [ ] **SMK-13:** Send a message → user bubble → typing indicator → assistant response streams in
- [ ] **SMK-14:** Send message with no conversation → auto-creates conversation → message sends
- [ ] **SMK-15:** Attach document in chat → chip appears → system message
- [ ] **SMK-16:** Remove document chip → chip disappears
- [ ] **SMK-17:** Delete conversation → confirm → removed from sidebar → chat resets
- [ ] **SMK-18:** Drag & drop file on chat area → uploads to active conversation
- [ ] **SMK-19:** Resize to mobile width → sidebar collapses → hamburger menu works
- [ ] **SMK-20:** Check console throughout → no uncaught errors

---

## Appendix A: API Endpoints Reference

| Method | Endpoint | UI Trigger |
|--------|----------|------------|
| `GET` | `/api/v1/meta/disclaimer/version` | Page load |
| `GET` | `/api/v1/meta/disclaimer/text` | Disclaimer modal open |
| `POST` | `/api/v1/ingest` | "Text extrahieren" button |
| `POST` | `/api/v1/analyze` | "Analyse starten" button |
| `POST` | `/api/v1/corpus/update` | "Corpus aktualisieren" button |
| `GET` | `/api/v1/corpus/status/{job_id}` | Polling every 2s |
| `GET` | `/api/v1/conversations` | Switch to Chat mode, after message send |
| `POST` | `/api/v1/conversations` | "Neue Unterhaltung", auto-create on first message |
| `GET` | `/api/v1/conversations/{id}` | Click conversation in sidebar |
| `DELETE` | `/api/v1/conversations/{id}` | Delete button → confirm |
| `POST` | `/api/v1/conversations/{id}/messages` | Send message (Enter or click send) |
| `POST` | `/api/v1/conversations/{id}/documents` | Attach button, drag & drop |
| `GET` | `/api/v1/conversations/{id}/documents` | (loaded as part of conversation detail) |
| `DELETE` | `/api/v1/conversations/{id}/documents/{did}` | × on document chip |

## Appendix B: State Object Reference

```javascript
state = {
    // Analyze mode
    file: null,                  // File object from input
    extractedText: null,         // String from OCR
    disclaimerVersion: null,     // Server disclaimer version
    sessionId: null,             // Unused currently
    hasExtracted: false,         // Whether OCR completed
    corpusJobId: null,           // Active corpus job ID
    corpusPollingTimer: null,    // setTimeout ID for polling

    // Chat mode
    currentMode: 'analyze',      // 'analyze' | 'chat'
    conversations: [],           // Array of conversation summaries
    activeConversationId: null,  // Currently selected conversation
    conversationDocuments: [],   // Documents in active conversation
    isStreaming: false,          // Whether SSE stream is active
    streamingAbortController: null, // AbortController for stream
}
```

## Appendix C: CSS Class Reference for Visual State Testing

| Class | Element | Visual Effect |
|-------|---------|---------------|
| `.hidden` | Any | `display: none !important` |
| `.active` | `.mode-btn` | White bg, white text, shadow |
| `.active` | `.stage` | Pulsing blue icon |
| `.complete` | `.stage` | Green checkmark icon |
| `.active` | `.conversation-item` | Blue border, darker bg |
| `.open` | `.chat-sidebar` | `translateX(0)` (mobile) |
| `.open` | `.result-collapsible` | Arrow rotated, body visible |
| `.visible` | `.sidebar-overlay` | `display: block` |
| `.drag-over` | `#chat-mode` | Blue dashed outline on messages |
| `.uploading` | `.chat-doc-chip` | Pulsing opacity animation |
| `.streaming` | `.message-bubble` | (class added but no CSS rule — verify intent) |
| `.indeterminate` | `.corpus-progress-fill` | Shimmer animation |
| `.success` | `.corpus-result` | Green bg/border/text |
| `.error` | `.corpus-result` | Red bg/border/text |
| `.warning` | `.corpus-result` | Yellow bg/border/text |
| `.chat-error-inline` | `div` | Red bg, red border, red text |
