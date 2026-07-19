/**
 * Citizen — Legal Reasoning Engine Frontend
 *     @version 1.0.0
 *
 * Handles:
 * - Disclaimer acceptance modal with localStorage persistence
 * - Document upload and OCR via /api/v1/ingest
 * - Corpus update via /api/v1/corpus/update with status polling
 * - SSE streaming analysis via /api/v1/analyze
 * - 6-section output rendering
 * - Conversational chat interface with sidebar
 * - Multi-turn conversations with SSE streaming (pipeline + RAG modes)
 * - Document upload within conversations
 * - Mode toggle between Analyze, Prüfstand, Chat, and Settings views
 * - WP-14 Prüfstand: goldset browser, eval overlay, demo mode with comparison
 */

(function() {
    'use strict';

    // =========================================================================
    // Configuration
    // =========================================================================

    const STORAGE_KEY = 'legal_disclaimer_accepted_v1';
    const STORAGE_VERSION_KEY = 'legal_disclaimer_version_v1';
    const API_BASE = '/api/v1';

    // Stage name mapping (for display)
    const stageNames = {
        normalization: 'Normalisierung',
        classification: 'Klassifikation',
        decomposition: 'Fragezerlegung',
        retrieval: 'Retrieval',
        construction: 'Anspruchsaufbau',
        verification: 'Verifikation',
        adversarial_review: 'Rechtsprüfung (Adversarial)',
        calculation_check: 'Berechnungsprüfung',
        generation: 'Ausgabe',
    };

    const pipelineStages = Object.keys(stageNames);

    const pipelineSectionLabels = {
        sachverhalt: 'Sachverhalt',
        rechtliche_wuerdigung: 'Rechtliche Würdigung',
        ergebnis: 'Ergebnis',
        handlungsempfehlung: 'Handlungsempfehlung',
        entwurf: 'Entwurf',
        unsicherheiten: 'Unsicherheiten',
        adversarial_pruefung: 'Adversariale Rechtsprüfung',
        berechnungspruefung: 'Berechnungsprüfung',
    };

    // =========================================================================
    // DOM Elements — Analyze Mode (existing)
    // =========================================================================

    const elements = {
        disclaimerModal: document.getElementById('disclaimer-modal'),
        disclaimerText: document.getElementById('disclaimer-text'),
        disclaimerCheckbox: document.getElementById('disclaimer-checkbox'),
        acknowledgeBtn: document.getElementById('acknowledge-btn'),
        app: document.getElementById('app'),
        analyzeMode: document.getElementById('analyze-mode'),
        uploadSection: document.getElementById('upload-section'),
        uploadArea: document.getElementById('upload-area'),
        fileInput: document.getElementById('file-input'),
        fileInfo: document.getElementById('file-info'),
        filename: document.getElementById('filename'),
        removeFile: document.getElementById('remove-file'),
        uploadBtn: document.getElementById('upload-btn'),
        textEditor: document.getElementById('text-editor'),
        useTextBtn: document.getElementById('use-text-btn'),
        analysisSection: document.getElementById('analysis-section'),
        textPreview: document.getElementById('text-preview'),
        analyzeBtn: document.getElementById('analyze-btn'),
        // New: 3-step flow
        stepIndicator: document.getElementById('step-indicator'),
        intakeSection: document.getElementById('intake-section'),
        intakeMessages: document.getElementById('intake-messages'),
        intakeInput: document.getElementById('intake-input'),
        intakeSendBtn: document.getElementById('intake-send-btn'),
        intakeConfirmBtn: document.getElementById('intake-confirm-btn'),
        intakeBackBtn: document.getElementById('intake-back-btn'),
        intakeTurnCounter: document.getElementById('intake-turn-counter'),
        confirmationSection: document.getElementById('confirmation-section'),
        confirmationBackBtn: document.getElementById('confirmation-back-btn'),
        presetCardBody: document.getElementById('preset-card-body'),
        presetCardSummary: document.getElementById('preset-card-summary'),
        presetCardMissing: document.getElementById('preset-card-missing'),
        presetCardMissingText: document.getElementById('preset-card-missing-text'),
        presetLoadMissingBtn: document.getElementById('preset-load-missing-btn'),
        missingSourcesModal: document.getElementById('missing-sources-modal'),
        missingSourcesList: document.getElementById('missing-sources-list'),
        missingSourcesMessage: document.getElementById('missing-sources-message'),
        missingSourcesCancelBtn: document.getElementById('missing-sources-cancel-btn'),
        missingSourcesLoadBtn: document.getElementById('missing-sources-load-btn'),
        progressSection: document.getElementById('progress-section'),
        progressBar: document.getElementById('progress-bar'),
        stageList: document.getElementById('stage-list'),
        streamOutput: document.getElementById('stream-output'),
        streamOutputContent: document.getElementById('stream-output-content'),
        // Result Report (WP-41) — #results-section was renamed to #result-report-section;
        // resultsSection is kept as an alias so existing call sites keep working.
        resultsSection: document.getElementById('result-report-section'),
        // Result Report (WP-41)
        resultReportSection: document.getElementById('result-report-section'),
        resultReportContent: document.getElementById('result-report-content'),
        errorDisplay: document.getElementById('error-display'),
        corpusUpdateBtn: document.getElementById('corpus-update-btn'),
        corpusProgress: document.getElementById('corpus-progress'),
        corpusProgressFill: document.getElementById('corpus-progress-fill'),
        corpusSubstage: document.getElementById('corpus-substage'),
        corpusChunksCount: document.getElementById('corpus-chunks-count'),
        corpusResult: document.getElementById('corpus-result'),
        // Mode toggle
        modeAnalyzeBtn: document.getElementById('mode-analyze-btn'),
        modeChatBtn: document.getElementById('mode-chat-btn'),
        rechtsstandValue: document.getElementById('rechtsstand-value'),
        rechtsstandIndicator: document.getElementById('rechtsstand-indicator'),
        profileBanner: document.getElementById('profile-banner'),
        profileBannerLabel: document.getElementById('profile-banner-label'),
        footerProfile: document.getElementById('footer-profile'),
        // Chat mode
        chatMode: document.getElementById('chat-mode'),
        chatSidebar: document.getElementById('chat-sidebar'),
        conversationList: document.getElementById('conversation-list'),
        conversationEmpty: document.getElementById('conversation-empty'),
        conversationError: document.getElementById('conversation-error'),
        newConversationBtn: document.getElementById('new-conversation-btn'),
        chatHeader: document.getElementById('chat-header'),
        sidebarToggle: document.getElementById('sidebar-toggle'),
        chatTitle: document.getElementById('chat-title'),
        chatDeleteBtn: document.getElementById('chat-delete-btn'),
        chatMessages: document.getElementById('chat-messages'),
        chatEmptyState: document.getElementById('chat-empty-state'),
        chatDocChips: document.getElementById('chat-doc-chips'),
        chatInputArea: document.getElementById('chat-input-area'),
        chatInput: document.getElementById('chat-input'),
        chatSendBtn: document.getElementById('chat-send-btn'),
        chatAttachBtn: document.getElementById('chat-attach-btn'),
        chatFileInput: document.getElementById('chat-file-input'),
        // Settings mode
        settingsMode: document.getElementById('settings-mode'),
        modeSettingsBtn: document.getElementById('mode-settings-btn'),
        settingsSourceList: document.getElementById('settings-source-list'),
        settingsSourceCount: document.getElementById('settings-source-count'),
        settingsSelectAll: document.getElementById('settings-select-all'),
        settingsLoading: document.getElementById('settings-loading'),
        settingsError: document.getElementById('settings-error'),
        settingsSaveBtn: document.getElementById('settings-save-btn'),
        settingsReloadBtn: document.getElementById('settings-reload-btn'),
        settingsStatus: document.getElementById('settings-status'),
        settingsProgress: document.getElementById('settings-progress'),
        settingsProgressFill: document.getElementById('settings-progress-fill'),
        settingsSubstage: document.getElementById('settings-substage'),
        settingsChunksCount: document.getElementById('settings-chunks-count'),
        // Case Chat elements
        caseChatSection: document.getElementById('case-chat-section'),
        caseSidebar: document.getElementById('case-sidebar'),
        caseSessionList: document.getElementById('case-session-list'),
        caseSessionEmpty: document.getElementById('case-session-empty'),
        caseTitle: document.getElementById('case-title'),
        caseHeader: document.getElementById('case-header'),
        caseExportBtn: document.getElementById('case-export-btn'),
        caseCompareBtn: document.getElementById('case-compare-btn'),
        caseDeleteBtn: document.getElementById('case-delete-btn'),
        caseSections: document.getElementById('case-sections'),
        caseChatMessages: document.getElementById('case-chat-messages'),
        caseChatEmpty: document.getElementById('case-chat-empty'),
        caseChatInput: document.getElementById('case-chat-input'),
        caseChatSendBtn: document.getElementById('case-chat-send-btn'),
        caseCompareOverlay: document.getElementById('case-compare-overlay'),
        caseCompareSelect: document.getElementById('case-compare-select'),
        caseCompareLoad: document.getElementById('case-compare-load'),
        caseCompareClose: document.getElementById('case-compare-close'),
        caseComparePanels: document.getElementById('case-compare-panels'),
        caseCompareLeft: document.getElementById('case-compare-left'),
        caseCompareRight: document.getElementById('case-compare-right'),
        // Prüfstand mode (WP-14)
        pruefstandMode: document.getElementById('pruefstand-mode'),
        modePruefstandBtn: document.getElementById('mode-pruefstand-btn'),
        pruefstandLoading: document.getElementById('pruefstand-loading'),
        pruefstandError: document.getElementById('pruefstand-error'),
        pruefstandContent: document.getElementById('pruefstand-content'),
        pruefstandGallerySection: document.getElementById('pruefstand-gallery-section'),
        pruefstandGallery: document.getElementById('pruefstand-gallery'),
        pruefstandDetailSection: document.getElementById('pruefstand-detail-section'),
        pruefstandDetailContent: document.getElementById('pruefstand-detail-content'),
        pruefstandBackBtn: document.getElementById('pruefstand-back-btn'),
        pruefstandDemoSection: document.getElementById('pruefstand-demo-section'),
        pruefstandDemoContent: document.getElementById('pruefstand-demo-content'),
        pruefstandDemoBackBtn: document.getElementById('pruefstand-demo-back-btn'),
        footerProfilePruefstand: document.getElementById('footer-profile-pruefstand'),
    };

    // =========================================================================
    // State
    // =========================================================================

    let state = {
        // Analyze mode state
        file: null,
        extractedText: null,
        disclaimerVersion: null,
        sessionId: null,
        hasExtracted: false,
        corpusJobId: null,
        corpusPollingTimer: null,
        // 3-step intake flow
        currentStep: 1,
        intakeSession: null,         // {id, status, turn_count, max_turns, primary_area, secondary_areas, intake_result}
        intakeSelectedAreas: [],     // user-edited list of legal_areas (starts from LLM suggestion)
        intakeAvailableSources: [],  // from /api/v1/corpus/available-sources
        intakeMissingSources: [],    // per-area readiness check
        // Chat mode state
        currentMode: 'analyze',
        conversations: [],
        activeConversationId: null,
        conversationDocuments: [],
        // Settings mode state
        availableSources: [],
        selectedSources: [],
        settingsDirty: false,
        settingsJobId: null,
        settingsPollingTimer: null,
        isStreaming: false,
        streamingAbortController: null,
        // Case Chat state
        activeCaseId: null,
        activeCaseData: null,
        caseSessions: [],
        caseChatAbortController: null,
        caseIsStreaming: false,
        compareCaseData: null,
        // Prüfstand mode state (WP-14)
        goldsetData: null,           // full goldset manifest from GET /api/v1/goldset
        goldsetCaseDetail: null,     // current case detail from GET /api/v1/goldset/{id}
        evalReports: [],             // eval report summaries from GET /api/v1/eval/reports
        pruefstandDemoStreaming: false,
        pruefstandDemoResult: null,  // final pipeline output from demo analysis
    };

    // =========================================================================
    // Disclaimer Management
    // =========================================================================

    async function checkDisclaimerStatus() {
        try {
            const response = await fetch(API_BASE + '/meta/disclaimer/version');
            if (!response.ok) {
                console.warn('Disclaimer endpoint not available');
                return true;
            }
            const data = await response.json();
            state.disclaimerVersion = data.version;

            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) {
                return false;
            }

            const parsed = JSON.parse(stored);
            if (parsed.version !== state.disclaimerVersion) {
                localStorage.removeItem(STORAGE_KEY);
                localStorage.removeItem(STORAGE_VERSION_KEY);
                return false;
            }

            return true;
        } catch (err) {
            console.error('Error checking disclaimer status:', err);
            return false;
        }
    }

    async function loadDisclaimerText() {
        try {
            const response = await fetch(API_BASE + '/meta/disclaimer/text');
            if (!response.ok) {
                elements.disclaimerText.textContent = 'Fehler beim Laden des Disclaimer-Textes.';
                return;
            }
            const data = await response.json();
            elements.disclaimerText.innerHTML = data.text;
        } catch (err) {
            elements.disclaimerText.textContent = 'Fehler beim Laden des Disclaimer-Textes.';
        }
    }

    function showDisclaimerModal() {
        elements.disclaimerModal.classList.remove('hidden');
        elements.app.classList.add('hidden');
        loadDisclaimerText();
    }

    function hideDisclaimerModal() {
        elements.disclaimerModal.classList.add('hidden');
        elements.app.classList.remove('hidden');

        const acceptanceData = {
            version: state.disclaimerVersion,
            timestamp: new Date().toISOString(),
            ip_hash: '',
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(acceptanceData));
        localStorage.setItem(STORAGE_VERSION_KEY, state.disclaimerVersion);
    }

    function handleDisclaimerCheckbox() {
        elements.acknowledgeBtn.disabled = !elements.disclaimerCheckbox.checked;
    }

    function handleAcknowledge() {
        if (elements.disclaimerCheckbox.checked) {
            hideDisclaimerModal();
        }
    }

    // =========================================================================
    // API Helpers
    // =========================================================================

    function getDisclaimerAckHeader() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return null;
        try {
            const parsed = JSON.parse(stored);
            return parsed.version || null;
        } catch {
            return null;
        }
    }

    function buildHeaders(extra = {}) {
        const headers = { ...extra };
        const ack = getDisclaimerAckHeader();
        if (ack) {
            headers['X-Disclaimer-Ack'] = ack;
        }
        return headers;
    }

    async function handleApiError(response) {
        if (response.status === 403) {
            const data = await response.json();
            if (data.error === 'disclaimer_required' || data.error === 'disclaimer_version_mismatch') {
                localStorage.removeItem(STORAGE_KEY);
                localStorage.removeItem(STORAGE_VERSION_KEY);
                showDisclaimerModal();
                throw new Error('Disclaimer muss erneut bestätigt werden.');
            }
        }
        const text = await response.text();
        let message = `HTTP ${response.status}`;
        try {
            const json = JSON.parse(text);
            message = json.detail || json.message || message;
        } catch {
            message = text || message;
        }
        throw new Error(message);
    }

    // =========================================================================
    // Rechtsstand Indicator
    // =========================================================================

    /** Fetch legal-timestamp endpoint and update the Rechtsstand display. */
    async function fetchRechtsstand() {
        try {
            const resp = await fetch(API_BASE + '/meta/legal-timestamp', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });
            if (!resp.ok) {
                elements.rechtsstandValue.textContent = 'unbekannt';
                return;
            }
            const data = await resp.json();

            // Use corpus_freshness as the primary date; fall back to parameter_freshness
            const freshnessStr = data.corpus_freshness || data.parameter_freshness;
            if (!freshnessStr) {
                elements.rechtsstandValue.textContent = 'keine Daten';
                return;
            }

            // Format DD.MM.YYYY
            const parts = freshnessStr.split('-');
            const formatted = parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : freshnessStr;
            elements.rechtsstandValue.textContent = formatted;

            // Check if older than 90 days
            const freshnessDate = new Date(freshnessStr + 'T00:00:00');
            const now = new Date();
            const diffDays = (now - freshnessDate) / (1000 * 60 * 60 * 24);
            if (diffDays > 180) {
                elements.rechtsstandIndicator.classList.add('rechtsstand--stale');
            } else if (diffDays > 90) {
                elements.rechtsstandIndicator.classList.add('rechtsstand--warning');
            }
        } catch {
            elements.rechtsstandValue.textContent = 'Fehler';
        }
    }

    /** Fetch active inference profile and update the header banner + footer. */
    async function fetchActiveProfile() {
        try {
            const resp = await fetch(API_BASE + '/meta/active-profile', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });
            if (!resp.ok) {
                elements.profileBannerLabel.textContent = 'Profil-Fehler';
                elements.profileBanner.className = 'profile-banner profile-banner--not-signed';
                return;
            }
            const data = await resp.json();

            // Update header banner
            elements.profileBannerLabel.textContent = data.profile;
            const avvClass = data.avv_status === 'signed' ? 'profile-banner--signed'
                : data.data_residency === 'on-prem' ? 'profile-banner--on-prem'
                : 'profile-banner--not-signed';
            elements.profileBanner.className = 'profile-banner ' + avvClass;
            elements.profileBanner.title = data.label;

            // Update footer
            const profileText = data.label + ' | AVV: ' + data.avv_status;
            elements.footerProfile.textContent = profileText;
            if (elements.footerProfilePruefstand) {
                elements.footerProfilePruefstand.textContent = profileText;
            }
        } catch {
            elements.profileBannerLabel.textContent = '?';
            elements.profileBanner.className = 'profile-banner profile-banner--not-signed';
            elements.footerProfile.textContent = '';
            if (elements.footerProfilePruefstand) {
                elements.footerProfilePruefstand.textContent = '';
            }
        }
    }

    // =========================================================================
    // File Upload (Analyze Mode)
    // =========================================================================

    function handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        const maxSize = 25 * 1024 * 1024;
        if (file.size > maxSize) {
            showError('Datei zu groß. Maximale Größe ist 25 MB.');
            return;
        }

        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'text/plain', 'text/html', 'message/rfc822'];
        if (!allowedTypes.includes(file.type)) {
            showError('Ungültiger Dateityp. Erlaubt: PDF, JPG, PNG, TXT, HTML, EML.');
            return;
        }

        state.file = file;
        elements.filename.textContent = file.name;
        elements.fileInfo.classList.remove('hidden');
        elements.uploadBtn.disabled = false;
        // Clear text editor (inputs are mutually exclusive)
        elements.textEditor.value = '';
        elements.useTextBtn.disabled = true;
    }

    function handleFileDrop(event) {
        event.preventDefault();
        const file = event.dataTransfer.files[0];
        if (file) {
            const dt = new DataTransfer();
            dt.items.add(file);
            elements.fileInput.files = dt.files;
            handleFileSelect({ target: { files: dt.files } });
        }
    }

    function handleDragOver(event) {
        event.preventDefault();
    }

    function handleRemoveFile() {
        state.file = null;
        state.extractedText = null;
        state.hasExtracted = false;
        elements.fileInput.value = '';
        elements.fileInfo.classList.add('hidden');
        elements.uploadBtn.disabled = true;
        elements.uploadBtn.textContent = 'Text extrahieren';
        elements.analysisSection.classList.add('hidden');
        elements.resultsSection.classList.add('hidden');
        // Clear text editor too (inputs are mutually exclusive)
        elements.textEditor.value = '';
        elements.useTextBtn.disabled = true;
    }

    // =========================================================================
    // Text Editor (Analyze Mode — alternative to file upload)
    // =========================================================================

    function handleTextEditorInput() {
        const hasContent = elements.textEditor.value.trim().length > 0;
        elements.useTextBtn.disabled = !hasContent;
    }

    function handleUseText() {
        const text = elements.textEditor.value.trim();
        if (!text) return;

        showError(null);
        // Clear any selected file (mutual exclusivity)
        state.file = null;
        state.hasExtracted = false;
        elements.fileInput.value = '';
        elements.fileInfo.classList.add('hidden');
        elements.uploadBtn.disabled = true;
        elements.uploadBtn.textContent = 'Text extrahieren';

        state.extractedText = text;
        state.hasExtracted = true;

        const fullLength = state.extractedText.length;
        elements.textPreview.innerHTML =
            truncateText(state.extractedText, 500)
            + `\n\n<span class="char-count">(${fullLength} Zeichen erfasst — Vorschau zeigt erste 500)</span>`;
        elements.analysisSection.classList.remove('hidden');
        elements.resultsSection.classList.add('hidden');
    }

    async function handleUpload() {
        if (!state.file) return;

        showError(null);
        elements.uploadBtn.disabled = true;
        elements.uploadBtn.textContent = state.hasExtracted ? 'Wird erneut extrahiert...' : 'Wird extrahiert...';

        try {
            const formData = new FormData();
            formData.append('file', state.file);

            const response = await fetch(API_BASE + '/ingest', {
                method: 'POST',
                headers: buildHeaders(),
                body: formData,
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.extractedText = data.text;
            state.hasExtracted = true;

            const fullLength = state.extractedText.length;
            elements.textPreview.innerHTML =
                truncateText(state.extractedText, 500)
                + `\n\n<span class="char-count">(${fullLength} Zeichen extrahiert — Vorschau zeigt erste 500)</span>`;
            elements.analysisSection.classList.remove('hidden');
            elements.resultsSection.classList.add('hidden');
        } catch (err) {
            showError(err.message);
        } finally {
            elements.uploadBtn.disabled = false;
            elements.uploadBtn.textContent = state.hasExtracted ? 'Erneut extrahieren' : 'Text extrahieren';
        }
    }

    // =========================================================================
    // Analysis (Analyze Mode)
    // =========================================================================

    async function handleAnalyze() {
        if (!state.extractedText) return;

        showError(null);
        elements.analysisSection.classList.add('hidden');
        elements.progressSection.classList.add('hidden');
        elements.resultsSection.classList.add('hidden');
        elements.errorDisplay.classList.add('hidden');

        document.querySelectorAll('#analyze-mode .stage').forEach(stage => {
            stage.classList.remove('complete', 'active');
            stage.querySelector('.stage-icon').textContent = '○';
        });

        elements.progressBar.style.width = '0%';
        elements.progressSection.classList.remove('hidden');

        // Hide and clear stream output
        elements.streamOutput.classList.add('hidden');
        elements.streamOutputContent.textContent = '';

        // Remove any existing corpus health warning
        const existingWarning = elements.progressSection.querySelector('.corpus-health-warning');
        if (existingWarning) existingWarning.remove();

        try {
            const response = await fetch(API_BASE + '/analyze', {
                method: 'POST',
                headers: buildHeaders({
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                }),
                body: JSON.stringify({
                    text: state.extractedText,
                    legal_areas: state.intakeSelectedAreas || [],
                    intake_session_id: state.intakeSession ? state.intakeSession.id : null,
                }),
            });

            if (response.status === 409) {
                // Pre-flight: missing corpus sources — show actionable modal
                const data = await response.json();
                showMissingSourcesModal(data.detail || data);
                elements.progressSection.classList.add('hidden');
                return;
            }

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            await processSSEStream(response);
        } catch (err) {
            showError(err.message);
            elements.progressSection.classList.add('hidden');
            elements.analysisSection.classList.remove('hidden');
        }
    }

    async function processSSEStream(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    try {
                        const event = JSON.parse(data);
                        handleSSEEvent(event);
                    } catch (err) {
                        console.error('Failed to parse SSE event:', err);
                    }
                }
            }
        }
    }

    function handleSSEEvent(event) {
        if (event.error) {
            showError(event.detail || 'Analyse fehlgeschlagen');
            return;
        }

        // WP-42: OCR quality event — show ConfidenceRibbon in progress area
        if (event.stage === 'ocr_quality') {
            handleOcrQualityEvent(event);
            return;
        }

        // Corpus health warning event
        if (event.stage === 'corpus_health') {
            handleCorpusHealthEvent(event);
            return;
        }

        // Stream output events — show live model output
        if (event.stage === 'stream_output') {
            handleStreamOutputEvent(event);
            return;
        }

        if (event.stage) {
            updateStage(event.stage, event.status, event.payload);
        }

        if (event.final_output) {
            renderResults(event.final_output);
        }
        if (event.case_run_id) {
            // Persist and auto-navigate to case chat
            state.activeCaseId = event.case_run_id;
            // Update the doc-generation button now that we have a case_run_id
            updateDocActionButton(event.case_run_id);
            if (state._pendingCaseOutput) {
                loadCaseSession(event.case_run_id, state._pendingCaseOutput);
                state._pendingCaseOutput = null;
            } else {
                loadCaseSession(event.case_run_id);
            }
            loadCaseSessions();
        }
    }

    function handleStreamOutputEvent(event) {
        const lines = (event.payload && event.payload.lines) || [];
        if (lines.length > 0) {
            elements.streamOutput.classList.remove('hidden');
            elements.streamOutputContent.textContent = lines.join('\n');
            // Auto-scroll to bottom of stream output
            elements.streamOutputContent.scrollTop = elements.streamOutputContent.scrollHeight;
        }
    }

    function handleCorpusHealthEvent(event) {
        const payload = event.payload || {};
        const warnings = payload.warnings || [];
        const message = payload.message || '';

        if (event.status === 'warning') {
            // Show warning message in the progress area
            const warningEl = document.createElement('div');
            warningEl.className = 'corpus-health-warning';
            warningEl.innerHTML = `
                <span class="corpus-health-icon">⚠️</span>
                <span class="corpus-health-text">${escapeHtml(message)}</span>
            `;
            // Insert after progress bar
            const progressSection = elements.progressSection;
            const existing = progressSection.querySelector('.corpus-health-warning');
            if (existing) {
                existing.remove();
            }
            progressSection.insertBefore(warningEl, elements.stageList);
        }
    }

    /**
     * Handle OCR quality SSE events (WP-42).
     * Renders a ConfidenceRibbon in the progress section.
     */
    function handleOcrQualityEvent(event) {
        const payload = event.payload || {};
        const status = event.status || 'info'; // 'warning', 'info', or 'error'

        // Remove any existing OCR quality ribbon
        const existing = document.querySelector('.c-confidence-ribbon');
        if (existing) existing.remove();

        const ribbon = document.createElement('div');
        ribbon.className = 'c-confidence-ribbon level-' + (payload.level || 'good');
        ribbon.id = 'ocr-quality-ribbon';

        const scorePct = payload.score !== undefined ? Math.round(payload.score * 100) : 0;
        const levelLabels = {
            good: 'Gut',
            acceptable: 'Ausreichend',
            poor: 'Gering',
            unusable: 'Unbrauchbar',
        };
        const levelLabel = levelLabels[payload.level] || payload.level || 'Unbekannt';

        // Build header
        let html = '<div class="c-confidence-ribbon-header">';
        html += '<div class="c-confidence-ribbon-label">OCR-Qualität</div>';
        html += '<div class="c-confidence-ribbon-level-badge">' + escapeHtml(levelLabel) + '</div>';
        html += '<div class="c-confidence-ribbon-score">' + scorePct + '%</div>';
        html += '</div>';

        // Score bar
        html += '<div class="c-confidence-ribbon-track">';
        html += '<div class="c-confidence-ribbon-fill" style="width: ' + scorePct + '%;"></div>';
        html += '</div>';

        // Details
        html += '<div class="c-confidence-ribbon-details">';

        // Language detection
        if (payload.language_detected) {
            const langLabel = payload.language_detected === 'de' ? 'Deutsch' : 'Unbekannt';
            html += '<div class="c-confidence-ribbon-detail-row">';
            html += '<span>Sprache</span><span>' + escapeHtml(langLabel) + '</span>';
            html += '</div>';
        }

        // Readable words
        if (payload.readable_words_pct !== undefined) {
            const rwPct = Math.round(payload.readable_words_pct * 100);
            html += '<div class="c-confidence-ribbon-detail-row">';
            html += '<span>Lesbare Wörter</span><span>' + rwPct + '%</span>';
            html += '</div>';
        }

        // Warnings (shown if present)
        const warnings = payload.warnings || [];
        if (warnings.length > 0) {
            for (const w of warnings) {
                const cssClass = status === 'warning'
                    ? 'c-confidence-ribbon-warning'
                    : 'c-confidence-ribbon-detail-row';
                html += '<div class="' + cssClass + '">' + escapeHtml(w) + '</div>';
            }
        }

        // Issues list
        const issues = payload.issues || [];
        if (issues.length > 0) {
            html += '<ul class="c-confidence-ribbon-issues">';
            for (const issue of issues) {
                html += '<li>' + escapeHtml(issue) + '</li>';
            }
            html += '</ul>';
        }

        // Recommendations
        const recommendations = payload.recommendations || [];
        if (recommendations.length > 0) {
            html += '<ul class="c-confidence-ribbon-recommendations">';
            for (const rec of recommendations) {
                html += '<li>' + escapeHtml(rec) + '</li>';
            }
            html += '</ul>';
        }

        html += '</div>'; // .c-confidence-ribbon-details

        ribbon.innerHTML = html;

        // Insert the ribbon at the top of the progress section (after progress bar)
        const progressSection = elements.progressSection;
        const progressBar = elements.progressBar;
        if (progressBar && progressBar.parentElement) {
            progressBar.parentElement.after(ribbon);
        } else {
            progressSection.insertBefore(ribbon, elements.stageList);
        }

        // If quality is "unusable", show error and stop further processing
        if (payload.level === 'unusable') {
            const errorMsg = 'OCR-Qualität unzureichend. Die Analyse kann nicht gestartet werden. ' +
                'Bitte laden Sie das Dokument in höherer Qualität (300 dpi, Schwarz/Weiß) hoch ' +
                'oder geben Sie den Text manuell ein.';
            showError(errorMsg);
        }
    }

    function updateStage(stageName, status, payload) {
        const stage = document.querySelector(`#analyze-mode .stage[data-stage="${stageName}"]`);
        if (!stage) return;

        const icon = stage.querySelector('.stage-icon');

        if (status === 'complete') {
            stage.classList.remove('active');
            stage.classList.add('complete');
            icon.textContent = '✓';
            icon.classList.add('complete');
        } else if (status === 'running') {
            stage.classList.add('active');
            icon.textContent = '◐';
        }

        const currentIndex = pipelineStages.indexOf(stageName);
        const progress = ((currentIndex + 1) / pipelineStages.length) * 100;
        elements.progressBar.style.width = `${progress}%`;
    }

    function renderResults(output) {
        // Save the output for when case_run_id arrives
        state._pendingCaseOutput = output;
        // Hide progress section, show the Result Report
        elements.progressSection.classList.add('hidden');
        elements.streamOutput.classList.add('hidden');
        renderResultReport(output, state.activeCaseId);
    }

    // =========================================================================
    // Result Report (WP-41) — rich report using shared components
    // Reuses: renderDeadlineBanner, renderFristTimelineSVG, renderCalcDiffTable,
    // renderClaimItem, c-trap-callout, c-next-steps from WP-14.
    // =========================================================================

    /**
     * Render the full Result Report into #result-report-section.
     * Page order per design doc §11.1:
     *   1. Case header (title + export)
     *   2. DeadlineBanner (hero)
     *   3. SummaryBlock (ergebnis section)
     *   4. ClaimList (findings from adversarial + berechnungspruefung)
     *   5. CalcDiffTable (from berechnungspruefung)
     *   6. FristTimeline (mini)
     *   7. TrapCallouts (from unsicherheiten)
     *   8. NextSteps (from handlungsempfehlung)
     *   9. Document generation panel
     *  10. Footer (disclaimer + metadata)
     */
    function renderResultReport(output, caseRunId) {
        if (!output || typeof output !== 'object') {
            elements.resultReportContent.innerHTML =
                '<div class="report-error">Keine Ausgabedaten erhalten.</div>';
            elements.resultReportSection.classList.remove('hidden');
            elements.caseChatSection.classList.add('hidden');
            return;
        }

        // Extract structured data from the pipeline's final_output dict.
        const fristData = extractFristFromOutput(output);
        const calcData = extractCalcFromOutput(output);
        const findings = extractFindingsFromOutput(output);
        const traps = extractTrapsFromOutput(output);
        const nextSteps = extractNextStepsFromOutput(output);
        const assessment = determineOverallAssessment(output, findings, calcData);

        // 1. Case header actions (back + chat buttons)
        const actionsEl = document.getElementById('report-case-actions');
        if (actionsEl) {
            actionsEl.innerHTML =
                '<button class="btn btn-small" id="report-back-btn" title="Zurück zur Eingabe">← Neuer Fall</button>' +
                '<button class="btn btn-small" id="report-chat-btn" title="Fall im Chat öffnen">Chat öffnen</button>';
        }

        // 2. DeadlineBanner (hero) — 5 urgency states via renderDeadlineBanner
        const deadlineEl = document.getElementById('deadline-banner');
        if (deadlineEl) {
            deadlineEl.innerHTML = renderDeadlineBanner(fristData);
        }

        // 3. Summary block — overall assessment + plain-German ergebnis text
        const summaryEl = document.getElementById('result-summary');
        if (summaryEl) {
            summaryEl.innerHTML = renderSummaryBlock(output, assessment);
        }

        // 4. Findings (ClaimList) — traffic-light items via renderClaimItem(ctx='report')
        const findingsEl = document.getElementById('findings-list');
        if (findingsEl) {
            if (findings.length > 0) {
                let html = '<h3 class="report-section-heading">Befunde</h3>';
                html += '<div class="c-claim-list">';
                for (const f of findings) {
                    html += renderClaimItem(f, 'report');
                }
                html += '</div>';
                findingsEl.innerHTML = html;
            } else {
                findingsEl.innerHTML = '';
            }
        }

        // 5. CalcDiffTable — only populated if reconciliation data exists
        const calcEl = document.getElementById('calculation-diff');
        if (calcEl) {
            if (calcData.rows.length > 0) {
                let html = '<h3 class="report-section-heading">Berechnung</h3>';
                html += renderCalcDiffTable(calcData.rows);
                if (calcData.summary) {
                    html += '<div class="report-calc-summary">' + escapeHtml(calcData.summary) + '</div>';
                }
                calcEl.innerHTML = html;
            } else {
                calcEl.innerHTML = '';
            }
        }

        // 6. FristTimeline — full SVG timeline via renderFristTimelineSVG
        const fristEl = document.getElementById('frist-timeline');
        if (fristEl) {
            if (fristData && fristData.aufgabe_zur_post) {
                fristEl.innerHTML = '<h3 class="report-section-heading">Fristen-Verlauf</h3>' +
                    '<div class="c-frist-timeline">' + renderFristTimelineSVG(fristData, true) + '</div>';
            } else {
                fristEl.innerHTML = '';
            }
        }

        // 7. Trap callouts — amber warning boxes via .c-trap-callout
        const trapsEl = document.getElementById('traps-list');
        if (trapsEl) {
            if (traps.length > 0) {
                let html = '<h3 class="report-section-heading">Bekannte Fallen &amp; Unsicherheiten</h3>';
                for (const trap of traps) {
                    html += '<div class="c-trap-callout"><strong>Falle:</strong> ' + escapeHtml(trap) + '</div>';
                }
                trapsEl.innerHTML = html;
            } else {
                trapsEl.innerHTML = '';
            }
        }

        // 8. Next steps — numbered action checklist via .c-next-steps
        const stepsEl = document.getElementById('next-steps');
        if (stepsEl) {
            if (nextSteps.length > 0) {
                let html = '<div class="c-next-steps">';
                html += '<h4>Nächste Schritte</h4>';
                html += '<ol class="next-steps-list">';
                for (const step of nextSteps) {
                    html += '<li>' + escapeHtml(step) + '</li>';
                }
                html += '</ol></div>';
                stepsEl.innerHTML = html;
            } else {
                stepsEl.innerHTML = '';
            }
        }

        // 9. Document generation panel — POST /api/v1/documents/generate
        const docEl = document.getElementById('doc-actions');
        if (docEl) {
            docEl.innerHTML = renderDocActions(caseRunId);
        }

        // 10. Footer — disclaimer version + active inference profile
        const footerEl = document.getElementById('report-footer');
        if (footerEl) {
            footerEl.innerHTML = renderReportFooter();
        }

        elements.resultReportSection.classList.remove('hidden');
        elements.caseChatSection.classList.add('hidden');

        // Wire up all buttons inside the report
        wireReportButtons(caseRunId);

        // Copy the active inference-profile label into the footer
        const footerProfile = document.getElementById('report-footer-profile');
        if (footerProfile && elements.footerProfile) {
            footerProfile.textContent = elements.footerProfile.textContent;
        }
    }

    /**
     * Render the summary block: verdict badge + plain-German ergebnis text.
     * Uses the assessment (green/red/gray) determined from findings + calc.
     */
    function renderSummaryBlock(output, assessment) {
        const ergebnisText = output.ergebnis || '';
        if (!ergebnisText) return '';

        let html = '<h3 class="report-section-heading">Zusammenfassung</h3>';
        html += '<div class="report-summary ' + assessment.cssClass + '">';
        html += '<div class="report-summary-verdict">';
        html += '<span class="verdict-dot ' + assessment.color + '"></span>';
        html += '<span class="report-summary-label">' + escapeHtml(assessment.label) + '</span>';
        html += '</div>';
        html += '<div class="report-summary-text">' + escapeHtml(ergebnisText) + '</div>';
        html += '</div>';
        return html;
    }

    /**
     * Render the document-generation panel: three doc-type buttons + status/output areas.
     * Buttons are disabled until a case_run_id is known.
     */
    function renderDocActions(caseRunId) {
        const disabled = caseRunId ? '' : ' disabled';
        let html = '<h3 class="report-section-heading">Dokument erstellen</h3>';
        html += '<div class="report-doc-buttons">';
        html += '<button class="btn btn-primary report-doc-btn" id="doc-gen-widerspruch-btn" ' +
                'data-doc-type="widerspruch"' + disabled + '>✎ Widerspruchsschreiben erstellen</button>';
        html += '<button class="btn btn-small report-doc-btn" id="doc-gen-akteneinsicht-btn" ' +
                'data-doc-type="akteneinsichtsantrag_25"' + disabled + '>Akteneinsicht beantragen</button>';
        html += '<button class="btn btn-small report-doc-btn" id="doc-gen-ueberpruefung-btn" ' +
                'data-doc-type="ueberpruefungsantrag_44"' + disabled + '>Überprüfungsantrag (§ 44)</button>';
        html += '</div>';
        html += '<div class="report-doc-status hidden" id="report-doc-status"></div>';
        html += '<div class="report-doc-output hidden" id="report-doc-output"></div>';
        return html;
    }

    /**
     * Render the report footer: disclaimer line + active profile placeholder.
     */
    function renderReportFooter() {
        let html = '<p class="report-footer-disclaimer">Citizen v1.0.0 — Automatisierte Rechtsanalyse ohne Gewähr</p>';
        html += '<p class="footer-profile" id="report-footer-profile"></p>';
        return html;
    }

    /**
     * Update the doc-generation buttons once case_run_id is known.
     */
    function updateDocActionButton(caseRunId) {
        document.querySelectorAll('#result-report-section .report-doc-buttons button').forEach(btn => {
            btn.disabled = false;
            btn.dataset.caseRunId = caseRunId;
        });
    }

    /**
     * Wire up all buttons in the result report.
     */
    function wireReportButtons(caseRunId) {
        const backBtn = document.getElementById('report-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                elements.resultReportSection.classList.add('hidden');
                elements.uploadSection.classList.remove('hidden');
                elements.stepIndicator.classList.remove('hidden');
                // Reset to step 1
                state.currentStep = 1;
                showStep(1);
            });
        }

        const chatBtn = document.getElementById('report-chat-btn');
        if (chatBtn) {
            chatBtn.addEventListener('click', () => {
                if (state.activeCaseId) {
                    loadCaseSession(state.activeCaseId);
                }
            });
        }

        // Document generation buttons
        document.querySelectorAll('#result-report-section .report-doc-buttons button').forEach(btn => {
            btn.addEventListener('click', () => {
                const docType = btn.dataset.docType;
                const runId = caseRunId || state.activeCaseId || btn.dataset.caseRunId;
                if (runId) {
                    generateDocument(docType, runId);
                }
            });
        });
    }

    /**
     * Generate a document via POST /api/v1/documents/generate.
     */
    async function generateDocument(docType, caseRunId) {
        const statusEl = document.getElementById('report-doc-status');
        const outputEl = document.getElementById('report-doc-output');
        if (!statusEl || !outputEl) return;

        statusEl.textContent = 'Dokument wird erstellt …';
        statusEl.classList.remove('hidden');
        outputEl.classList.add('hidden');

        try {
            const response = await fetch(API_BASE + '/documents/generate', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json', 'Accept': 'application/json' }),
                body: JSON.stringify({
                    case_run_id: caseRunId,
                    doc_type: docType,
                }),
            });
            if (!response.ok) {
                await handleApiError(response);
                return;
            }
            const data = await response.json();

            statusEl.textContent = 'Dokument erstellt: ' + (data.title || docType);
            statusEl.classList.add('report-doc-success');

            // Render the document text
            let html = '<div class="report-doc-rendered">';
            html += '<div class="report-doc-rendered-header">';
            html += '<span class="report-doc-type">' + escapeHtml(data.document_type || docType) + '</span>';
            html += '<button class="btn btn-small" id="doc-copy-btn">Kopieren</button>';
            html += '<button class="btn btn-small" id="doc-download-btn">Herunterladen</button>';
            html += '</div>';
            html += '<pre class="report-doc-text">' + escapeHtml(data.rendered_text || '') + '</pre>';
            if (data.warnings && data.warnings.length > 0) {
                html += '<div class="report-doc-warnings"><strong>Hinweise:</strong><ul>';
                for (const w of data.warnings) {
                    html += '<li>' + escapeHtml(w) + '</li>';
                }
                html += '</ul></div>';
            }
            html += '</div>';
            outputEl.innerHTML = html;
            outputEl.classList.remove('hidden');

            // Wire copy/download
            const copyBtn = document.getElementById('doc-copy-btn');
            if (copyBtn) {
                copyBtn.addEventListener('click', () => {
                    navigator.clipboard.writeText(data.rendered_text || '').then(() => {
                        copyBtn.textContent = 'Kopiert!';
                        setTimeout(() => { copyBtn.textContent = 'Kopieren'; }, 2000);
                    });
                });
            }
            const downloadBtn = document.getElementById('doc-download-btn');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', () => {
                    downloadText((data.title || docType) + '.txt', data.rendered_text || '');
                });
            }
        } catch (err) {
            statusEl.textContent = 'Fehler: ' + err.message;
            statusEl.classList.add('report-doc-error');
        }
    }

    // -------------------------------------------------------------------------
    // Pipeline output extractors — parse the pipeline's final_output dict
    // into the shapes expected by the shared render functions.
    // -------------------------------------------------------------------------

    /**
     * Extract frist data from pipeline output.
     * The pipeline may store frist info in the generation stage output or
     * in a dedicated frist_berechnung key. We try to reconstruct from
     * the sachverhalt/rechtliche_wuerdigung text if structured data is absent.
     */
    function extractFristFromOutput(output) {
        // Check for structured frist data (injected by pipeline or stage logs)
        if (output.frist_berechnung && typeof output.frist_berechnung === 'object') {
            return normalizeFristData(output.frist_berechnung);
        }
        // Try parsing a JSON string
        if (output.frist_berechnung && typeof output.frist_berechnung === 'string') {
            try {
                return normalizeFristData(JSON.parse(output.frist_berechnung));
            } catch { /* fall through */ }
        }
        // No structured frist data — return null (banner shows "Keine Fristdaten")
        return null;
    }

    /**
     * Normalize a frist dict (from pipeline or stage logs) into the shape
     * expected by renderDeadlineBanner and renderFristTimelineSVG.
     */
    function normalizeFristData(raw) {
        if (!raw || typeof raw !== 'object') return null;
        return {
            frist_ende: raw.frist_ende || raw.fristEnde || null,
            frist_ende_rechnerisch: raw.frist_ende_rechnerisch || null,
            bekanntgabe_fiktion: raw.bekanntgabe || raw.bekanntgabe_fiktion || null,
            aufgabe_zur_post: raw.aufgabe_zur_post || null,
            bescheid_datum: raw.bescheid_datum || null,
            status: raw.frist_typ === 'kein_va' ? 'kein_verwaltungsakt' : (raw.status || null),
            rollover_applied: raw.rollover_applied || false,
            oq1_flag: raw.oq1_flag || false,
        };
    }

    /**
     * Extract calculation diff rows from berechnungspruefung.
     * The pipeline stores this as a JSON string with structure:
     *   { calculations_found: [...], overall_assessment: {...} }
     * Each calculation has: label, jobcenter_wert, korrekter_wert, differenz, etc.
     */
    function extractCalcFromOutput(output) {
        const result = { rows: [], summary: null };
        let calcRaw = output.berechnungspruefung;
        if (!calcRaw) return result;

        // Parse JSON string if needed
        if (typeof calcRaw === 'string') {
            try {
                calcRaw = JSON.parse(calcRaw);
            } catch {
                // Not JSON — it's an error message string
                return { rows: [], summary: calcRaw };
            }
        }
        if (!calcRaw || typeof calcRaw !== 'object') return result;

        // Extract summary
        const overall = calcRaw.overall_assessment || {};
        if (overall.summary) {
            let summary = overall.summary;
            if (overall.total_discrepancies && overall.total_discrepancies > 0) {
                summary += ' (' + overall.total_discrepancies + ' Abweichung(en)';
                if (overall.total_amount_eur) {
                    summary += ', ' + formatEuro(overall.total_amount_eur);
                }
                summary += ')';
            }
            result.summary = summary;
        }

        // Extract rows from calculations_found
        const calcs = calcRaw.calculations_found || [];
        for (const calc of calcs) {
            const jobcenter = calc.jobcenter_wert ?? calc.jobcenter_ergebnis ?? calc.authority_value ?? null;
            const correct = calc.korrekter_wert ?? calc.korrekt ?? calc.deterministic_result ?? null;
            const delta = calc.differenz ?? calc.discrepancy_amount_eur ?? null;
            // Only include rows that have at least one numeric value
            if (jobcenter !== null || correct !== null) {
                result.rows.push({
                    label: calc.label || calc.computation_label || 'Wert',
                    jobcenter: jobcenter !== null ? Number(jobcenter) : null,
                    correct: correct !== null ? Number(correct) : null,
                    delta: delta !== null && delta !== undefined ? Number(delta) :
                           (jobcenter !== null && correct !== null ? round2(correct - jobcenter) : null),
                });
            }
        }
        return result;
    }

    /**
     * Extract findings (claims) from adversarial_pruefung.
     * The pipeline stores this as a JSON string with structure:
     *   { reviews: [...], overall_assessment: {...} }
     * Each review has: claim_text, verdict, key_risks, etc.
     */
    function extractFindingsFromOutput(output) {
        const findings = [];
        let advRaw = output.adversarial_pruefung;
        if (!advRaw) return findings;

        if (typeof advRaw === 'string') {
            try {
                advRaw = JSON.parse(advRaw);
            } catch {
                return findings; // error message string — skip
            }
        }
        if (!advRaw || typeof advRaw !== 'object') return findings;

        const reviews = advRaw.reviews || [];
        for (const review of reviews) {
            findings.push({
                id: review.claim_id || review.id || '',
                issue: review.claim_text || review.claim || review.issue || '',
                assessment: review.verdict || review.assessment || '',
                norm_chain: review.norm_chain || review.relevant_norms || [],
                sub_issues: review.key_risks || [],
            });
        }

        // Also extract procedural errors as findings
        const overall = advRaw.overall_assessment || {};
        const procErrors = overall.procedural_errors_found || [];
        for (const err of procErrors) {
            if (typeof err === 'string') {
                findings.push({
                    id: 'proc-error',
                    issue: err,
                    assessment: 'rechtswidrig_zulasten',
                    norm_chain: [],
                    sub_issues: [],
                });
            } else if (err && err.error) {
                findings.push({
                    id: err.id || 'proc-error',
                    issue: err.error || err.description || '',
                    assessment: 'rechtswidrig_zulasten',
                    norm_chain: err.norms || [],
                    sub_issues: [],
                });
            }
        }
        return findings;
    }

    /**
     * Extract trap callouts from the unsicherheiten section.
     * The pipeline output has a text block; we split by bullet points.
     */
    function extractTrapsFromOutput(output) {
        const traps = [];
        const unsicher = output.unsicherheiten || '';
        if (!unsicher) return traps;

        // Split by bullet markers (•, -, *) and filter
        const lines = unsicher.split('\n');
        let current = '';
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                if (current) { traps.push(current); current = ''; }
                continue;
            }
            if (/^[•\-\*]\s/.test(trimmed)) {
                if (current) traps.push(current);
                current = trimmed.replace(/^[•\-\*]\s*/, '');
            } else {
                current = current ? current + ' ' + trimmed : trimmed;
            }
        }
        if (current) traps.push(current);
        return traps;
    }

    /**
     * Extract next steps from handlungsempfehlung.
     * Split by numbered items or bullet points.
     */
    function extractNextStepsFromOutput(output) {
        const steps = [];
        const raw = output.handlungsempfehlung || '';
        if (!raw) return steps;

        // Try splitting by numbered list (1. 2. 3.)
        const numbered = raw.match(/\d+\.\s+[^\n]+/g);
        if (numbered && numbered.length > 0) {
            for (const item of numbered) {
                steps.push(item.replace(/^\d+\.\s*/, '').trim());
            }
            return steps;
        }

        // Try splitting by bullets
        const lines = raw.split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (/^[•\-\*]\s/.test(trimmed)) {
                steps.push(trimmed.replace(/^[•\-\*]\s*/, ''));
            } else if (trimmed && !trimmed.match(/^\d+\./)) {
                // Non-empty, non-numbered line — include as a step
                steps.push(trimmed);
            }
        }
        // Filter out empty/placeholder steps
        return steps.filter(s => s.length > 3);
    }

    /**
     * Determine the overall assessment for the summary block.
     * Uses the ergebnis text, findings, and calc data to pick a verdict.
     */
    function determineOverallAssessment(output, findings, calcData) {
        const ergebnis = (output.ergebnis || '').toLowerCase();

        // Check for kein Verwaltungsakt
        if (ergebnis.includes('kein verwaltungsakt') || ergebnis.includes('kein va')) {
            return { color: 'gray', label: 'Kein Verwaltungsakt', cssClass: 'report-summary-gray' };
        }

        // Check findings for errors
        const errorCount = findings.filter(f =>
            (f.assessment || '').includes('rechtswidrig_zulasten') ||
            (f.assessment || '').includes('error_against_user')
        ).length;

        // Check calc for discrepancies
        const calcDiscrepancies = calcData.rows.filter(r =>
            r.delta !== null && r.delta !== undefined && Math.abs(r.delta) > 0.01
        ).length;

        if (errorCount > 0 || calcDiscrepancies > 0) {
            if (ergebnis.includes('teilweise') || (errorCount > 0 && calcDiscrepancies === 0)) {
                return { color: 'red', label: 'Fehler zulasten gefunden', cssClass: 'report-summary-red' };
            }
            return { color: 'red', label: 'Fehler zulasten gefunden', cssClass: 'report-summary-red' };
        }

        // Check for "hält stand" / "rechtmaessig"
        if (ergebnis.includes('hält') && ergebnis.includes('stand') ||
            ergebnis.includes('rechtmaessig') || ergebnis.includes('rechtmäßig')) {
            return { color: 'green', label: 'Bescheid hält der Prüfung stand', cssClass: 'report-summary-green' };
        }

        // Default: neutral/unclear
        return { color: 'gray', label: 'Prüfung abgeschlossen', cssClass: 'report-summary-gray' };
    }

    function round2(val) {
        return Math.round(val * 100) / 100;
    }

    // =========================================================================
    // Prüfstand Mode (WP-14) — Goldset Browser, Eval Overlay, Demo Mode
    // =========================================================================

    /**
     * Fetch the goldset manifest and render the header + gallery.
     * The YAML is parsed server-side; this function only ever touches JSON.
     */
    async function fetchGoldset() {
        if (!elements.pruefstandLoading) return;
        elements.pruefstandLoading.classList.remove('hidden');
        elements.pruefstandError.classList.add('hidden');
        elements.pruefstandContent.classList.add('hidden');
        elements.pruefstandGallerySection.classList.add('hidden');

        try {
            const response = await fetch(API_BASE + '/goldset', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });
            if (!response.ok) {
                // Do NOT call handleApiError — that can trigger showDisclaimerModal
                // which hides the entire app. Show a Prüfstand-specific error instead.
                let errMsg = `HTTP ${response.status}`;
                try {
                    const body = await response.json();
                    errMsg = body.detail || body.message || errMsg;
                    if (body.error === 'disclaimer_required' || body.error === 'disclaimer_version_mismatch') {
                        errMsg = 'Bitte bestätigen Sie zuerst den Haftungsausschluss im Analyse-Tab.';
                    }
                } catch { /* use default */ }
                throw new Error(errMsg);
            }
            state.goldsetData = await response.json();
            renderPruefstandHeader(state.goldsetData);
            renderCaseGallery(state.goldsetData.cases);
            elements.pruefstandContent.classList.remove('hidden');
            elements.pruefstandGallerySection.classList.remove('hidden');
        } catch (err) {
            elements.pruefstandError.textContent = 'Fehler beim Laden des Goldsets: ' + err.message;
            elements.pruefstandError.classList.remove('hidden');
        } finally {
            elements.pruefstandLoading.classList.add('hidden');
        }
    }

    /**
     * Fetch eval report summaries and render the aggregate tile.
     * Empty state is a clean "Noch keine Prüfläufe" — never fake numbers.
     */
    async function fetchEvalReports() {
        try {
            const response = await fetch(API_BASE + '/eval/reports', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });
            if (!response.ok) return;
            const data = await response.json();
            state.evalReports = data.reports || [];
            // Update the eval overlay in the DOM if the header has been rendered
            const overlayContainer = document.getElementById('eval-overlay-container');
            if (overlayContainer) {
                overlayContainer.innerHTML = renderEvalOverlay(state.evalReports);
            }
        } catch (err) {
            // Silent fail — eval overlay is non-critical
            console.error('Eval reports fetch failed:', err);
        }
    }

    /**
     * Fetch a single goldset case (full detail) and render the two-column view.
     */
    async function fetchGoldsetCase(caseId) {
        elements.pruefstandDetailContent.innerHTML = '<div class="pruefstand-loading">Fall wird geladen …</div>';
        elements.pruefstandGallerySection.classList.add('hidden');
        elements.pruefstandDetailSection.classList.remove('hidden');

        try {
            const response = await fetch(API_BASE + '/goldset/' + encodeURIComponent(caseId), {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });
            if (!response.ok) {
                await handleApiError(response);
                return;
            }
            state.goldsetCaseDetail = await response.json();
            elements.pruefstandDetailContent.innerHTML = renderCaseDetail(state.goldsetCaseDetail);
            wireDetailButtons(caseId);
        } catch (err) {
            elements.pruefstandDetailContent.innerHTML =
                '<div class="pruefstand-error">Fehler beim Laden des Falls: ' + escapeHtml(err.message) + '</div>';
        }
    }

    /**
     * Start a demo analysis: POST the goldset case text through the pipeline.
     * Streams SSE events, then shows the comparison view.
     */
    async function startDemoAnalysis(caseId) {
        if (state.pruefstandDemoStreaming) return;
        state.pruefstandDemoStreaming = true;
        state.pruefstandDemoResult = null;

        elements.pruefstandDetailSection.classList.add('hidden');
        elements.pruefstandDemoSection.classList.remove('hidden');
        elements.pruefstandDemoContent.innerHTML = renderDemoProgress(caseId);

        const stagesOrder = ['normalization', 'classification', 'decomposition', 'retrieval',
            'construction', 'verification', 'adversarial_review', 'calculation_check', 'generation'];

        try {
            const response = await fetch(
                API_BASE + '/goldset/' + encodeURIComponent(caseId) + '/analyze',
                {
                    method: 'POST',
                    headers: buildHeaders({ 'Accept': 'text/event-stream' }),
                }
            );
            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            const completedStages = new Set();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        // Handle stage progress
                        if (event.stage && event.stage !== 'stream_output' && event.stage !== 'corpus_health') {
                            if (event.status === 'complete' || event.status === 'done') {
                                completedStages.add(event.stage);
                                updateDemoProgress(event.stage, 'complete');
                            } else if (event.status === 'running' || event.status === 'started') {
                                updateDemoProgress(event.stage, 'active');
                            }
                        }
                        // Handle final output (from the goldset route's final event)
                        if (event.final_output) {
                            state.pruefstandDemoResult = event.final_output;
                        }
                        // Handle error
                        if (event.error) {
                            throw new Error(event.detail || 'Pipeline fehlgeschlagen');
                        }
                    } catch (parseErr) {
                        // Re-throw if it's our explicit error
                        if (parseErr.message && parseErr.message.includes('Pipeline')) throw parseErr;
                        console.error('SSE parse error:', parseErr);
                    }
                }
            }

            // Render comparison view
            if (state.pruefstandDemoResult && state.goldsetCaseDetail) {
                elements.pruefstandDemoContent.innerHTML =
                    renderDemoComparison(state.goldsetCaseDetail, state.pruefstandDemoResult);
            } else if (state.goldsetCaseDetail) {
                // Pipeline finished but no final_output — show what we have
                elements.pruefstandDemoContent.innerHTML =
                    '<div class="pruefstand-error">Pipeline abgeschlossen, aber keine Ausgabe erhalten.</div>';
            }
        } catch (err) {
            elements.pruefstandDemoContent.innerHTML =
                '<div class="pruefstand-error">Demo-Analyse fehlgeschlagen: ' + escapeHtml(err.message) + '</div>';
        } finally {
            state.pruefstandDemoStreaming = false;
        }
    }

    function updateDemoProgress(stageName, status) {
        const stageEl = document.querySelector('.demo-progress-stage[data-stage="' + stageName + '"]');
        if (!stageEl) return;
        stageEl.classList.remove('active', 'complete');
        stageEl.classList.add(status);
        const icon = stageEl.querySelector('.demo-progress-stage-icon');
        if (icon) {
            icon.textContent = status === 'complete' ? '✓' : '◉';
        }
    }

    // -------------------------------------------------------------------------
    // Render functions — return HTML strings
    // -------------------------------------------------------------------------

    /**
     * Render the Prüfstand header: badges, eval tile, baseline cards, open questions.
     */
    function renderPruefstandHeader(data) {
        const g = data.goldset;
        const badges = [
            { label: 'Goldset', value: 'v' + g.version },
            { label: 'Rechtsstand', value: formatDate(g.rechtsstand) },
            { label: 'Fälle', value: g.case_count },
            { label: 'Referenzdatum', value: formatDate(g.evaluation_reference_date) },
        ];

        let html = '<div class="pruefstand-badges">';
        for (const b of badges) {
            html += '<span class="pruefstand-badge"><strong>' + escapeHtml(b.label) +
                    ':</strong> ' + escapeHtml(String(b.value)) + '</span>';
        }
        html += '</div>';
        html += '<p class="pruefstand-notice">Hinweis: Es handelt sich um synthetische, fiktive Fälle.</p>';

        // Eval overlay tile
        html += '<div id="eval-overlay-container">' + renderEvalOverlay(state.evalReports) + '</div>';

        // Baseline cards
        html += '<h2 class="pruefstand-section-heading">Rechtliche Basislinien</h2>';
        html += '<div class="pruefstand-baseline-grid">';
        html += renderBaselineRegelbedarf(g.legal_baseline);
        html += renderBaselineFreibetraege(g.legal_baseline);
        html += renderBaselineSanktionen(g.legal_baseline);
        html += renderBaselineFristen(g.legal_baseline);
        html += '</div>';

        // Open questions
        if (g.open_questions && g.open_questions.length > 0) {
            html += '<h2 class="pruefstand-section-heading">Bewusst offene Rechtsfragen</h2>';
            html += '<div class="open-questions-section">';
            for (const q of g.open_questions) {
                html += '<div class="open-question-item">';
                html += '<div class="open-question-topic">' + escapeHtml(q.topic) + '</div>';
                html += '<div class="open-question-note">' + escapeHtml(q.note) + '</div>';
                html += '</div>';
            }
            html += '</div>';
        }

        elements.pruefstandContent.innerHTML = html;
    }

    /**
     * Render the eval overlay tile — latest run summary or clean empty state.
     */
    function renderEvalOverlay(reports) {
        if (!reports || reports.length === 0) {
            return '<div class="c-eval-overlay">' +
                '<div class="eval-tile eval-tile-empty" aria-label="Keine Prüfläufe vorhanden">' +
                '<div class="eval-tile-icon">○</div>' +
                '<div class="eval-tile-body">' +
                '<div class="eval-tile-title">Eval-Status</div>' +
                '<div class="eval-tile-summary">Noch keine Prüfläufe</div>' +
                '</div></div></div>';
        }

        // Show the latest report (first in the list — sorted reverse by filename)
        const latest = reports[0];
        const agg = latest.aggregate || {};
        const passCount = agg.fully_passed_cases !== undefined ? agg.fully_passed_cases : '—';
        const totalCount = latest.case_count || '—';

        return '<div class="c-eval-overlay">' +
            '<div class="eval-tile eval-tile-populated">' +
            '<div class="eval-tile-icon">✓</div>' +
            '<div class="eval-tile-body">' +
            '<div class="eval-tile-title">Letzter Prüflauf</div>' +
            '<div class="eval-tile-summary">' + escapeHtml(String(passCount)) + '/' +
            escapeHtml(String(totalCount)) + ' Fälle vollständig bestanden</div>' +
            '</div>' +
            '<div class="eval-tile-meta">' +
            (latest.git_sha ? 'SHA ' + escapeHtml(latest.git_sha.slice(0, 7)) + '<br>' : '') +
            (latest.run_timestamp ? escapeHtml(formatDateTime(latest.run_timestamp)) : '') +
            '</div></div></div>';
    }

    function renderBaselineRegelbedarf(lb) {
        const rb = lb.regelbedarf_2026 || {};
        let body = '';
        if (rb.note) {
            body += '<p class="baseline-card-note">' + escapeHtml(rb.note.slice(0, 120)) + '…</p>';
        }
        body += '<table class="baseline-table">';
        if (rb.rbs1_alleinstehend !== undefined) {
            body += '<tr><td>Alleinstehend (RBS 1)</td><td>' + formatEuro(rb.rbs1_alleinstehend) + '</td></tr>';
        }
        if (rb.rbs2_partner !== undefined) {
            body += '<tr><td>Partner (RBS 2)</td><td>' + formatEuro(rb.rbs2_partner) + '</td></tr>';
        }
        body += '</table>';
        return '<div class="baseline-card"><h4>Regelbedarf 2026</h4>' + body + '</div>';
    }

    function renderBaselineFreibetraege(lb) {
        const ek = lb.einkommen_absetzbetraege_11b || {};
        let body = '';
        if (ek.grundabsetzung !== undefined) {
            body += '<table class="baseline-table"><tr><td>Grundabsetzung</td><td>' +
                    formatEuro(ek.grundabsetzung) + '</td></tr></table>';
        }
        // Step graphic (Treppengrafik)
        if (ek.staffel && ek.staffel.length > 0) {
            body += '<div class="freibetrag-staircase">';
            ek.staffel.forEach((step, i) => {
                const heightClass = 'stair-step-height-' + Math.min(i + 1, 3);
                body += '<div class="stair-step ' + heightClass + '">' +
                    '<span class="stair-step-pct">' + step.prozent + '%</span>' +
                    '<span class="stair-step-range">' + formatEuro(step.von) + '–' + formatEuro(step.bis) + '</span>' +
                    '</div>';
            });
            body += '</div>';
        }
        return '<div class="baseline-card"><h4>§ 11b Freibeträge</h4>' + body + '</div>';
    }

    function renderBaselineSanktionen(lb) {
        const sk = lb.sanktionen_neues_recht || {};
        let body = '<div class="sanktionen-summary">';
        if (sk.pflichtverletzung_31a) {
            const p = sk.pflichtverletzung_31a;
            body += '<p><strong>§ 31a Pflichtverletzung:</strong> ' +
                    (p.minderung_prozent_regelbedarf || '?') + '% für ' +
                    (p.dauer_monate || '?') + ' Monate</p>';
        }
        if (sk.meldeversaeumnis_32) {
            const m = sk.meldeversaeumnis_32;
            body += '<p><strong>§ 32 Meldeversäumnis:</strong> ' +
                    escapeHtml(m.erstes_versaeumnis || '') + '</p>';
        }
        if (sk.aufschiebende_wirkung) {
            body += '<p><strong>Widerspruch:</strong> Keine aufschiebende Wirkung (§ 39 Nr. 1 SGB II)</p>';
        }
        body += '</div>';
        return '<div class="baseline-card"><h4>Sanktionen (neues Recht)</h4>' + body + '</div>';
    }

    function renderBaselineFristen(lb) {
        const fm = lb.fristen_model || {};
        let body = '';
        if (fm.bekanntgabefiktion) {
            body += '<p class="baseline-card-note"><strong>Bekanntgabefiktion:</strong> ' +
                    escapeHtml(fm.bekanntgabefiktion.slice(0, 100)) + '…</p>';
        }
        if (fm.widerspruchsfrist) {
            body += '<p class="baseline-card-note"><strong>Widerspruchsfrist:</strong> 1 Monat ab Bekanntgabe</p>';
        }
        // Render the full FristTimeline SVG as the showpiece
        body += renderFristTimelineSVG({
            aufgabe_zur_post: '2026-07-06',
            bekanntgabe_fiktion: '2026-07-10',
            frist_ende: '2026-08-10',
            frist_ende_rechnerisch: null,
            rollover_applied: false,
        }, true);
        return '<div class="baseline-card"><h4>Fristen-Modell</h4>' + body + '</div>';
    }

    /**
     * Render the case gallery as a grid of cards.
     */
    function renderCaseGallery(cases) {
        if (!cases || cases.length === 0) {
            elements.pruefstandGallery.innerHTML = '<p class="pruefstand-loading">Keine Fälle im Goldset.</p>';
            return;
        }
        let html = '';
        for (const c of cases) {
            const colorClass = 'verdict-' + (c.assessment_color || 'gray');
            const dotClass = c.assessment_color || 'gray';
            const icon = c.assessment_color === 'red' ? '✕' :
                         c.assessment_color === 'green' ? '✓' : '—';
            html += '<div class="pruefstand-card ' + colorClass + '" data-case-id="' + escapeHtml(c.id) + '">';
            html += '<div class="pruefstand-card-id">' + escapeHtml(c.id) + '</div>';
            html += '<div class="pruefstand-card-title">' + escapeHtml(c.title) + '</div>';
            html += '<div class="pruefstand-card-category">' + escapeHtml(c.category_label || c.category) + '</div>';
            html += '<div class="pruefstand-card-difficulty">Schwierigkeit: ' +
                    escapeHtml(c.difficulty_label || c.difficulty) + '</div>';
            html += '<div class="pruefstand-card-verdict ' + dotClass + '">' +
                    '<span class="verdict-dot ' + dotClass + '"></span>' +
                    '<span class="verdict-icon">' + icon + '</span>' +
                    escapeHtml(c.assessment_label || '') + '</div>';
            html += '<div class="pruefstand-card-cta">Details anzeigen →</div>';
            html += '</div>';
        }
        elements.pruefstandGallery.innerHTML = html;

        // Wire up card clicks
        elements.pruefstandGallery.querySelectorAll('.pruefstand-card').forEach(card => {
            card.addEventListener('click', () => {
                const caseId = card.dataset.caseId;
                if (caseId) fetchGoldsetCase(caseId);
            });
        });
    }

    /**
     * Render the two-column case detail: letter (left) + findings (right).
     */
    function renderCaseDetail(caseData) {
        let html = '<h2 class="pruefstand-detail-title">' + escapeHtml(caseData.title) + '</h2>';
        html += '<div class="pruefstand-detail-meta">';
        html += '<span><strong>' + escapeHtml(caseData.id) + '</strong></span>';
        html += '<span>' + escapeHtml(caseData.category_label || caseData.category) + '</span>';
        html += '<span>Schwierigkeit: ' + escapeHtml(caseData.difficulty_label || caseData.difficulty) + '</span>';
        html += '<span class="pruefstand-card-verdict ' + (caseData.assessment_color || 'gray') + '">' +
                '<span class="verdict-dot ' + (caseData.assessment_color || 'gray') + '"></span>' +
                escapeHtml(caseData.assessment_label || '') + '</span>';
        html += '</div>';

        // Demo CTA
        html += '<button class="demo-cta-btn" id="demo-start-btn" data-case-id="' + escapeHtml(caseData.id) + '">' +
                '▶ Diesen Fall live analysieren</button>';

        html += '<div class="pruefstand-detail">';

        // Left column: input document as Behördenbrief
        html += '<div class="detail-column detail-left">';
        html += '<h3>Eingangsdokument</h3>';
        html += '<div class="c-letter-render">' + escapeHtml(caseData.input_document.text) + '</div>';
        html += '</div>';

        // Right column: findings, calc, frist, traps, next steps
        html += '<div class="detail-column detail-right">';
        html += '<h3>Erwartete Befunde</h3>';

        // DeadlineBanner (static)
        html += renderDeadlineBanner(caseData.widerspruchsfrist);

        // FristTimeline (mini)
        if (caseData.widerspruchsfrist && caseData.widerspruchsfrist.aufgabe_zur_post) {
            html += '<div class="c-frist-timeline mini">' +
                    renderFristTimelineSVG(caseData.widerspruchsfrist, false) + '</div>';
        }

        // ClaimList (findings)
        if (caseData.findings && caseData.findings.length > 0) {
            html += '<div class="c-claim-list">';
            for (const f of caseData.findings) {
                html += renderClaimItem(f);
            }
            html += '</div>';
        }

        // CalcDiffTable
        if (caseData.calc_diff_rows && caseData.calc_diff_rows.length > 0) {
            html += renderCalcDiffTable(caseData.calc_diff_rows);
        }

        // Citations
        if (caseData.citations && caseData.citations.length > 0) {
            html += '<h3 class="pruefstand-section-heading" style="font-size:1rem;margin-top:1rem;">Normen</h3>';
            html += '<div class="citations-list">';
            for (const c of caseData.citations) {
                html += '<div class="citation-item">';
                html += '<span class="citation-norm">' + escapeHtml(c.norm) + '</span>';
                if (c.rolle) {
                    html += '<span class="citation-role">' + escapeHtml(c.rolle) + '</span>';
                }
                html += '</div>';
            }
            html += '</div>';
        }

        // TrapCallouts
        if (caseData.known_traps && caseData.known_traps.length > 0) {
            html += '<h3 class="pruefstand-section-heading" style="font-size:1rem;margin-top:1rem;">Bekannte Fallen</h3>';
            for (const trap of caseData.known_traps) {
                html += '<div class="c-trap-callout"><strong>Falle</strong>' + escapeHtml(trap) + '</div>';
            }
        }

        // NextSteps
        if (caseData.actionable_next_steps && caseData.actionable_next_steps.length > 0) {
            html += '<div class="c-next-steps"><h4>Nächste Schritte</h4><ol class="next-steps-list">';
            for (const step of caseData.actionable_next_steps) {
                html += '<li>' + escapeHtml(step) + '</li>';
            }
            html += '</ol></div>';
        }

        html += '</div>'; // detail-right
        html += '</div>'; // pruefstand-detail
        return html;
    }

    /**
     * Render a single claim item (finding) with verdict icon and § chips.
     * The context flag ('report' | 'pruefstand' | 'demo') changes only the
     * finding label per design doc §2.3 — never the optics.
     */
    function renderClaimItem(finding, context) {
        context = context || 'report';
        const assessment = finding.assessment || '';
        // Map assessment strings to verdict colors
        let color = 'gray';
        let icon = '—';
        let label = 'Hinweis';
        if (assessment.includes('rechtswidrig_zulasten') || assessment.includes('error_against_user')) {
            color = 'red'; icon = '✕'; label = 'Fehler zulasten gefunden';
        } else if (assessment.includes('rechtmaessig') || assessment.includes('bescheid_correct')) {
            color = 'green'; icon = '✓'; label = 'Bescheid hält stand';
        } else if (assessment.includes('hinweis') || assessment.includes('unclear')) {
            color = 'amber'; icon = '!'; label = 'Hinweis';
        }
        // Context flag: "Erwarteter Befund" in pruefstand, "Befund" in report/demo
        const labelText = context === 'pruefstand' ? 'Erwarteter Befund — ' + label : label;

        let html = '<div class="c-claim-item verdict-' + color + '">';
        html += '<div class="claim-item-icon ' + color + '">' + icon + '</div>';
        html += '<div class="claim-item-body">';
        html += '<div class="claim-item-title">' + escapeHtml(finding.issue) + '</div>';
        html += '<div class="claim-item-assessment">' + escapeHtml(labelText) + '</div>';
        // § chips from norm_chain
        if (finding.norm_chain && finding.norm_chain.length > 0) {
            html += '<div class="claim-item-chips">';
            for (const norm of finding.norm_chain) {
                html += '<span class="c-section-chip">' + escapeHtml(norm) + '</span>';
            }
            html += '</div>';
        }
        html += '</div></div>';
        return html;
    }

    /**
     * Render the CalcDiffTable: Jobcenter vs. Korrekt vs. Differenz.
     */
    function renderCalcDiffTable(rows) {
        let html = '<table class="c-calc-diff"><caption>Gegenüberstellung Jobcenter-Berechnung und korrekter Berechnung.</caption>';
        html += '<thead><tr><th>Position</th><th>Jobcenter</th><th>Korrekt</th><th>Differenz</th></tr></thead>';
        html += '<tbody>';
        for (const row of rows) {
            html += '<tr>';
            html += '<td>' + escapeHtml(row.label) + '</td>';
            html += '<td>' + (row.jobcenter !== null ? formatEuro(row.jobcenter) : '<span class="calc-row-na">—</span>') + '</td>';
            html += '<td class="correct-col">' + (row.correct !== null ? formatEuro(row.correct) : '<span class="calc-row-na">—</span>') + '</td>';
            // Delta cell
            if (row.delta !== null && row.delta !== undefined) {
                const deltaClass = row.delta > 0 ? 'delta-positive' :
                                   row.delta < 0 ? 'delta-negative' : 'delta-zero';
                const arrow = row.delta > 0 ? ' ▲' : row.delta < 0 ? ' ▼' : ' —';
                html += '<td class="' + deltaClass + '" aria-label="' +
                        (row.delta > 0 ? 'plus' : row.delta < 0 ? 'minus' : 'null') + ' ' +
                        Math.abs(row.delta).toFixed(2) + ' Euro">' +
                        (row.delta > 0 ? '+' : '') + formatEuro(row.delta) + arrow + '</td>';
            } else {
                html += '<td class="calc-row-na">—</td>';
            }
            html += '</tr>';
        }
        html += '</tbody></table>';
        return html;
    }

    /**
     * Render the DeadlineBanner — the hero showing frist status.
     */
    function renderDeadlineBanner(frist) {
        if (!frist) {
            return '<div class="c-deadline-banner state-no-va">' +
                   '<div><div class="deadline-banner-label">Widerspruchsfrist</div>' +
                   '<div class="deadline-banner-date">—</div></div>' +
                   '<div class="deadline-banner-days">Keine Fristdaten</div></div>';
        }

        // Handle kein_verwaltungsakt
        if (frist.status === 'kein_verwaltungsakt' || frist.frist_ende === null) {
            return '<div class="c-deadline-banner state-no-va">' +
                   '<div><div class="deadline-banner-label">Widerspruchsfrist</div>' +
                   '<div class="deadline-banner-date">Kein Verwaltungsakt</div>' +
                   '<div class="deadline-banner-subline">Keine Frist läuft</div></div>' +
                   '<div class="deadline-banner-days">—</div></div>';
        }

        const fristDate = frist.frist_ende;
        const today = new Date();
        const fristObj = new Date(fristDate);
        const daysRemaining = Math.ceil((fristObj - today) / (1000 * 60 * 60 * 24));

        let stateClass = 'state-normal';
        let daysLabel = '';
        let subline = '';
        if (daysRemaining < 0) {
            stateClass = 'state-lapsed';
            daysLabel = 'Frist abgelaufen';
            subline = '§ 44 SGB X Wiedereinsetzung prüfen';
        } else if (daysRemaining <= 3) {
            stateClass = 'state-urgent-red';
            daysLabel = 'NUR NOCH ' + daysRemaining + ' TAGE';
        } else if (daysRemaining <= 7) {
            stateClass = 'state-urgent-amber';
            daysLabel = 'noch ' + daysRemaining + ' Tage — jetzt handeln';
        } else {
            daysLabel = 'noch ' + daysRemaining + ' Tage';
        }

        if (frist.rollover_applied) {
            subline += (subline ? ' · ' : '') + 'Werktag-Rollover angewandt';
        }

        return '<div class="c-deadline-banner ' + stateClass + '">' +
               '<div><div class="deadline-banner-label">Widerspruchsfrist</div>' +
               '<div class="deadline-banner-date">' + formatDate(fristDate) + '</div>' +
               (subline ? '<div class="deadline-banner-subline">' + escapeHtml(subline) + '</div>' : '') + '</div>' +
               '<div class="deadline-banner-days">' + escapeHtml(daysLabel) + '</div></div>';
    }

    /**
     * Render the FristTimeline as an inline SVG — the showpiece visualization.
     * Four stations: Aufgabe zur Post → Bekanntgabefiktion → Fristende → Rollover (if applicable).
     */
    function renderFristTimelineSVG(frist, isFull) {
        if (!frist || !frist.aufgabe_zur_post) return '';

        const stations = [];
        stations.push({
            label: 'Aufgabe zur Post',
            date: frist.aufgabe_zur_post,
            delta: null,
        });
        if (frist.bekanntgabe_fiktion) {
            stations.push({
                label: 'Bekanntgabe (fingiert)',
                date: frist.bekanntgabe_fiktion,
                delta: '+4 Tage Fiktion',
            });
        }
        if (frist.frist_ende) {
            const isRollover = frist.rollover_applied;
            stations.push({
                label: isRollover ? 'Fristende (rollt auf Werktag)' : 'Fristende Widerspruch',
                date: frist.frist_ende,
                delta: '+1 Monat',
                isFinal: true,
            });
            if (isRollover && frist.frist_ende_rechnerisch) {
                stations.push({
                    label: 'Rollt auf Werktag',
                    date: frist.frist_ende,
                    delta: '↻ Werktag',
                    isRollover: true,
                });
            }
        }

        if (stations.length < 2) return '';

        // SVG layout — viewBox scales from 320px to 4K
        const width = 800;
        const height = isFull ? 120 : 60;
        const margin = 60;
        const stationY = isFull ? 55 : 30;
        const dateY = isFull ? 80 : 45;
        const labelY = isFull ? 100 : 55;
        const deltaY = isFull ? 20 : 15;
        const spacing = (width - 2 * margin) / (stations.length - 1);

        let svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" role="img">';
        svg += '<title>Fristen-Verlauf</title>';
        svg += '<desc>Horizontaler Zeitstrahl der Widerspruchsfrist-Berechnung</desc>';

        // Connectors
        for (let i = 0; i < stations.length - 1; i++) {
            const x1 = margin + i * spacing;
            const x2 = margin + (i + 1) * spacing;
            svg += '<line class="tl-connector" x1="' + x1 + '" y1="' + stationY + '" x2="' + x2 + '" y2="' + stationY + '"/>';

            // Delta label above connector
            if (isFull && stations[i + 1].delta) {
                const midX = (x1 + x2) / 2;
                const labelWidth = stations[i + 1].delta.length * 6 + 12;
                svg += '<rect class="tl-delta-bg" x="' + (midX - labelWidth / 2) + '" y="' + (deltaY - 10) +
                       '" width="' + labelWidth + '" height="16" rx="3"/>';
                svg += '<text class="tl-delta-label" x="' + midX + '" y="' + deltaY + '">' +
                       escapeHtml(stations[i + 1].delta) + '</text>';
            }
        }

        // Stations
        for (let i = 0; i < stations.length; i++) {
            const x = margin + i * spacing;
            const s = stations[i];
            const r = s.isFinal ? 10 : 7;

            if (s.isRollover) {
                // Rollover station — amber dashed arc
                svg += '<path class="tl-rollover-arc" d="M ' + (x - spacing) + ' ' + (stationY - 15) +
                       ' Q ' + x + ' ' + (stationY - 35) + ' ' + x + ' ' + stationY + '"/>';
                svg += '<circle class="tl-station-rollover" cx="' + x + '" cy="' + stationY + '" r="' + r + '"/>';
            } else if (s.isFinal) {
                svg += '<circle class="tl-station-final" cx="' + x + '" cy="' + stationY + '" r="' + r + '"/>';
            } else {
                svg += '<circle class="tl-station" cx="' + x + '" cy="' + stationY + '" r="' + r + '"/>';
            }

            if (isFull) {
                svg += '<text class="tl-date" x="' + x + '" y="' + dateY + '">' + formatDate(s.date) + '</text>';
                svg += '<text class="tl-station-label" x="' + x + '" y="' + labelY + '">' +
                       escapeHtml(s.label) + '</text>';
            }
        }

        svg += '</svg>';
        return svg;
    }

    /**
     * Render the demo progress UI while the pipeline is streaming.
     */
    function renderDemoProgress(caseId) {
        const stages = [
            ['normalization', 'Normalisierung'],
            ['classification', 'Klassifikation'],
            ['decomposition', 'Fragezerlegung'],
            ['retrieval', 'Retrieval'],
            ['construction', 'Anspruchsaufbau'],
            ['verification', 'Verifikation'],
            ['adversarial_review', 'Rechtsprüfung'],
            ['calculation_check', 'Berechnungsprüfung'],
            ['generation', 'Ausgabe'],
        ];
        let html = '<div class="demo-progress">';
        html += '<div class="demo-progress-title">Live-Analyse läuft — Fall ' + escapeHtml(caseId) + '</div>';
        html += '<div class="demo-progress-stages">';
        for (const [key, label] of stages) {
            html += '<div class="demo-progress-stage" data-stage="' + key + '">' +
                    '<span class="demo-progress-stage-icon">○</span>' +
                    '<span>' + label + '</span></div>';
        }
        html += '</div></div>';
        return html;
    }

    /**
     * Render the demo comparison: expected (left) vs actual pipeline output (right).
     */
    function renderDemoComparison(caseData, pipelineResult) {
        let html = '<h2 class="pruefstand-detail-title">Vergleich: Erwartet vs. Pipeline-Ergebnis</h2>';
        html += '<div class="pruefstand-detail-meta">';
        html += '<span><strong>' + escapeHtml(caseData.id) + '</strong></span>';
        html += '<span>' + escapeHtml(caseData.title) + '</span>';
        html += '</div>';

        html += '<div class="pruefstand-demo-comparison">';

        // Left: expected findings
        html += '<div class="demo-column expected">';
        html += '<h3>Erwartete Befunde <span class="demo-match-badge match">Goldset</span></h3>';

        // Expected deadline
        html += renderDeadlineBanner(caseData.widerspruchsfrist);

        // Expected findings
        if (caseData.findings && caseData.findings.length > 0) {
            html += '<div class="c-claim-list">';
            for (const f of caseData.findings) {
                html += renderClaimItem(f);
            }
            html += '</div>';
        }

        // Expected calc
        if (caseData.calc_diff_rows && caseData.calc_diff_rows.length > 0) {
            html += renderCalcDiffTable(caseData.calc_diff_rows);
        }
        html += '</div>';

        // Right: actual pipeline output
        html += '<div class="demo-column actual">';
        html += '<h3>Pipeline-Ergebnis <span class="demo-match-badge mismatch">Live</span></h3>';

        if (pipelineResult && typeof pipelineResult === 'object') {
            // Render each section of the pipeline output
            const sectionLabels = {
                sachverhalt: 'Sachverhalt',
                rechtliche_wuerdigung: 'Rechtliche Würdigung',
                ergebnis: 'Ergebnis',
                handlungsempfehlung: 'Handlungsempfehlung',
                entwurf: 'Entwurf',
                unsicherheiten: 'Unsicherheiten',
                adversarial_pruefung: 'Adversariale Rechtsprüfung',
                berechnungspruefung: 'Berechnungsprüfung',
            };
            for (const [key, label] of Object.entries(sectionLabels)) {
                if (pipelineResult[key]) {
                    let content = pipelineResult[key];
                    // Try to parse JSON-encoded sections (adversarial/berechnungspruefung)
                    if (typeof content === 'string' && content.startsWith('{')) {
                        try {
                            const parsed = JSON.parse(content);
                            content = JSON.stringify(parsed, null, 2);
                        } catch { /* keep original */ }
                    }
                    html += '<div class="demo-pipeline-section">';
                    html += '<div class="demo-pipeline-section-title">' + escapeHtml(label) + '</div>';
                    html += '<div class="demo-pipeline-output">' + escapeHtml(String(content)) + '</div>';
                    html += '</div>';
                }
            }
            // Show any other sections not in the label map
            for (const key of Object.keys(pipelineResult)) {
                if (!sectionLabels[key] && pipelineResult[key]) {
                    html += '<div class="demo-pipeline-section">';
                    html += '<div class="demo-pipeline-section-title">' + escapeHtml(key) + '</div>';
                    html += '<div class="demo-pipeline-output">' + escapeHtml(String(pipelineResult[key])) + '</div>';
                    html += '</div>';
                }
            }
        } else {
            html += '<div class="pruefstand-error">Keine Pipeline-Ausgabe erhalten.</div>';
        }

        html += '</div>'; // demo-column actual
        html += '</div>'; // demo-comparison
        return html;
    }

    /**
     * Wire up buttons inside the case detail view (demo CTA).
     */
    function wireDetailButtons(caseId) {
        const demoBtn = document.getElementById('demo-start-btn');
        if (demoBtn) {
            demoBtn.addEventListener('click', () => startDemoAnalysis(caseId));
        }
    }

    // -------------------------------------------------------------------------
    // Formatting helpers (Prüfstand-specific)
    // -------------------------------------------------------------------------

    /** Format an ISO date string as DD.MM.YYYY. */
    function formatDate(isoStr) {
        if (!isoStr) return '—';
        try {
            const d = new Date(isoStr);
            if (isNaN(d.getTime())) return isoStr;
            return String(d.getDate()).padStart(2, '0') + '.' +
                   String(d.getMonth() + 1).padStart(2, '0') + '.' +
                   d.getFullYear();
        } catch { return isoStr; }
    }

    /** Format an ISO datetime string as DD.MM.YYYY HH:MM. */
    function formatDateTime(isoStr) {
        if (!isoStr) return '—';
        try {
            const d = new Date(isoStr);
            if (isNaN(d.getTime())) return isoStr;
            return formatDate(isoStr) + ' ' +
                   String(d.getHours()).padStart(2, '0') + ':' +
                   String(d.getMinutes()).padStart(2, '0');
        } catch { return isoStr; }
    }

    /** Format a number as German euro amount (1.234,56 €). */
    function formatEuro(val) {
        if (val === null || val === undefined) return '—';
        const num = Number(val);
        if (isNaN(num)) return String(val);
        return num.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
    }

    // =========================================================================
    // Utilities
    // =========================================================================

    function truncateText(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.slice(0, maxLength) + '...';
    }

    function escapeHtml(str) {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function formatContent(content) {
        if (!content) return '—';
        return escapeHtml(content).replace(/\n/g, '<br>');
    }

    function showError(message) {
        if (!message) {
            elements.errorDisplay.classList.add('hidden');
            return;
        }
        elements.errorDisplay.textContent = message;
        elements.errorDisplay.classList.remove('hidden');
    }

    /**
     * Format a date as a relative time string in German
     */
    function relativeTime(dateString) {
        const now = new Date();
        const date = new Date(dateString);
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHr = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHr / 24);

        if (diffSec < 60) return 'gerade eben';
        if (diffMin < 2) return 'vor 1 Minute';
        if (diffMin < 60) return `vor ${diffMin} Minuten`;
        if (diffHr < 2) return 'vor 1 Stunde';
        if (diffHr < 24) return `vor ${diffHr} Stunden`;
        if (diffDay < 2) return 'gestern';
        if (diffDay < 7) return `vor ${diffDay} Tagen`;

        return date.toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
        });
    }

    /**
     * Format file size for display
     */
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    /**
     * Validate file for chat upload
     */
    function validateChatFile(file) {
        const maxSize = 25 * 1024 * 1024;
        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'text/plain', 'text/html', 'message/rfc822'];
        if (file.size > maxSize) {
            return `Datei "${file.name}" zu groß (max. 25 MB).`;
        }
        if (!allowedTypes.includes(file.type)) {
            return `Datei "${file.name}" hat ungültigen Typ. Erlaubt: PDF, JPG, PNG, TXT, HTML, EML.`;
        }
        return null;
    }

    // =========================================================================
    // Corpus Management
    // =========================================================================

    const substageLabels = {
        scraping: 'Rechtsquellen werden abgerufen und aufbereitet …',
        embedding: 'Vektordarstellungen (Embeddings) werden generiert …',
        upserting: 'Einträge werden in der Datenbank gespeichert …',
    };

    async function handleCorpusUpdate() {
        if (state.corpusJobId) return;

        elements.corpusResult.classList.add('hidden');
        elements.corpusResult.textContent = '';
        elements.corpusResult.className = 'corpus-result hidden';

        elements.corpusProgress.classList.remove('hidden');
        elements.corpusSubstage.textContent = 'Auftrag wird eingereiht …';
        elements.corpusChunksCount.textContent = '';
        elements.corpusProgressFill.classList.remove('indeterminate');
        elements.corpusProgressFill.style.width = '0%';

        elements.corpusUpdateBtn.disabled = true;
        elements.corpusUpdateBtn.textContent = 'Corpus-Aktualisierung läuft …';

        try {
            const response = await fetch(API_BASE + '/corpus/update', {
                method: 'POST',
                headers: buildHeaders(),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.corpusJobId = data.job_id;

            elements.corpusSubstage.textContent = 'Auftrag gestartet — warte auf erste Rückmeldung …';
            pollCorpusStatus(data.job_id);
        } catch (err) {
            showCorpusError(err.message);
        }
    }

    function pollCorpusStatus(jobId) {
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
        }

        state.corpusPollingTimer = setTimeout(async () => {
            try {
                const response = await fetch(API_BASE + '/corpus/status/' + jobId, {
                    method: 'GET',
                    headers: buildHeaders(),
                });

                if (!response.ok) {
                    if (response.status === 404) {
                        showCorpusError('Auftrag nicht mehr im Speicher — bitte erneut versuchen.');
                        return;
                    }
                    await handleApiError(response);
                    return;
                }

                const job = await response.json();
                updateCorpusProgress(job);

                if (job.status === 'completed' || job.status === 'failed') {
                    finishCorpusUpdate(job);
                } else {
                    pollCorpusStatus(jobId);
                }
            } catch (err) {
                showCorpusError(err.message);
            }
        }, 2000);
    }

    function updateCorpusProgress(job) {
        if (job.substage && substageLabels[job.substage]) {
            let label = substageLabels[job.substage];
            // Show which source is currently being ingested (WP-014)
            if (job.substage === 'scraping' && job.current_source_display) {
                const sourceInfo = job.source_total
                    ? ` (Quelle ${job.source_index}/${job.source_total})`
                    : '';
                label = `${job.current_source_display} wird abgerufen …${sourceInfo}`;
            }
            elements.corpusSubstage.textContent = label;
        }

        if (job.substage === 'scraping' && job.chunks_scraped > 0) {
            elements.corpusChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke bisher abgerufen`;
        } else if (job.substage === 'embedding' && job.chunks_scraped > 0) {
            elements.corpusChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke werden verarbeitet`;
        } else if (job.substage === 'upserting' && job.chunks_scraped > 0) {
            elements.corpusChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke in DB`;
        }

        if (job.status === 'running') {
            elements.corpusProgressFill.classList.add('indeterminate');
        }
    }

    function finishCorpusUpdate(job) {
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
            state.corpusPollingTimer = null;
        }
        state.corpusJobId = null;

        elements.corpusProgress.classList.add('hidden');

        elements.corpusUpdateBtn.disabled = false;
        elements.corpusUpdateBtn.textContent = 'Corpus aktualisieren';

        elements.corpusResult.classList.remove('hidden');

        if (job.status === 'completed') {
            const count = job.chunks_processed || 0;
            if (count > 0) {
                elements.corpusResult.className = 'corpus-result success';
                elements.corpusResult.textContent =
                    `Corpus-Aktualisierung abgeschlossen: ${count} Texteinträge wurden verarbeitet und gespeichert.`;
            } else {
                elements.corpusResult.className = 'corpus-result warning';
                elements.corpusResult.textContent =
                    'Corpus-Aktualisierung abgeschlossen, aber es wurden keine Einträge gefunden. ' +
                    'Bitte prüfen Sie die Netzwerkverbindung und die Verfügbarkeit von gesetze-im-internet.de.';
            }
        } else if (job.status === 'failed') {
            const errMsg = job.error || 'Unbekannter Fehler';
            elements.corpusResult.className = 'corpus-result error';
            elements.corpusResult.textContent =
                `Corpus-Aktualisierung fehlgeschlagen: ${errMsg}`;
        }
    }

    function showCorpusError(message) {
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
            state.corpusPollingTimer = null;
        }
        state.corpusJobId = null;

        elements.corpusProgress.classList.add('hidden');

        elements.corpusUpdateBtn.disabled = false;
        elements.corpusUpdateBtn.textContent = 'Corpus aktualisieren';

        elements.corpusResult.classList.remove('hidden');
        elements.corpusResult.className = 'corpus-result error';
        elements.corpusResult.textContent = `Fehler: ${message}`;
    }

    // =========================================================================
    // Mode Management
    // =========================================================================

    function switchMode(mode) {
        if (mode === state.currentMode) return;
        state.currentMode = mode;

        // Hide all modes first
        elements.analyzeMode.classList.add('hidden');
        elements.chatMode.classList.add('hidden');
        elements.settingsMode.classList.add('hidden');
        if (elements.pruefstandMode) elements.pruefstandMode.classList.add('hidden');

        // Deselect all mode buttons in all headers
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));

        // Deactivate all mode buttons in all headers
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));

        if (mode === 'analyze') {
            elements.analyzeMode.classList.remove('hidden');
            document.querySelectorAll('.mode-btn[data-mode="analyze"]').forEach(btn => btn.classList.add('active'));
            fetchRechtsstand();
        } else if (mode === 'chat') {
            elements.chatMode.classList.remove('hidden');
            document.querySelectorAll('.mode-btn[data-mode="chat"]').forEach(btn => btn.classList.add('active'));
            if (state.conversations.length === 0) {
                loadConversations();
            }
        } else if (mode === 'settings') {
            elements.settingsMode.classList.remove('hidden');
            document.querySelectorAll('.mode-btn[data-mode="settings"]').forEach(btn => btn.classList.add('active'));
            if (state.availableSources.length === 0) {
                loadSettingsSources();
            }
        } else if (mode === 'pruefstand') {
            elements.pruefstandMode.classList.remove('hidden');
            document.querySelectorAll('.mode-btn[data-mode="pruefstand"]').forEach(btn => btn.classList.add('active'));
            // Lazy-load goldset on first entry; refresh eval reports each time
            if (!state.goldsetData) {
                fetchGoldset();
            }
            fetchEvalReports();
            fetchActiveProfile();
        }
    }

    // =========================================================================
    // Settings
    // =========================================================================

    async function loadSettingsSources() {
        elements.settingsLoading.classList.remove('hidden');
        elements.settingsError.classList.add('hidden');
        elements.settingsSourceList.classList.add('hidden');
        elements.settingsSaveBtn.disabled = true;
        elements.settingsReloadBtn.disabled = true;

        try {
            const response = await fetch(API_BASE + '/corpus/available-sources', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            state.availableSources = await response.json();
            state.selectedSources = state.availableSources
                .filter(s => s.active)
                .map(s => s.key);
            state.settingsDirty = false;
            renderSettingsSources();
        } catch (err) {
            elements.settingsError.textContent = 'Fehler beim Laden der Quellen: ' + err.message;
            elements.settingsError.classList.remove('hidden');
        } finally {
            elements.settingsLoading.classList.add('hidden');
        }
    }

    function renderSettingsSources() {
        const sources = state.availableSources;
        const selected = new Set(state.selectedSources);

        elements.settingsSourceList.innerHTML = '';
        elements.settingsSourceList.classList.remove('hidden');

        let selectableCount = 0;

        sources.forEach(source => {
            if (source.has_scraper) selectableCount++;

            const item = document.createElement('div');
            item.className = 'settings-source-item' + (!source.has_scraper ? ' disabled' : '');

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = 'source-' + source.key;
            checkbox.value = source.key;
            checkbox.checked = selected.has(source.key);
            checkbox.disabled = !source.has_scraper;

            checkbox.addEventListener('change', () => {
                if (checkbox.checked) {
                    state.selectedSources.push(source.key);
                } else {
                    state.selectedSources = state.selectedSources.filter(k => k !== source.key);
                }
                state.settingsDirty = true;
                updateSettingsUI();
            });

            const label = document.createElement('label');
            label.htmlFor = 'source-' + source.key;
            label.className = 'settings-source-label';

            label.innerHTML = `
                <span class="settings-source-name">${escapeHtml(source.full_name)}</span>
                <span class="settings-source-source">${escapeHtml(source.source)}</span>
                ${!source.has_scraper
                    ? '<span class="settings-source-unavailable">(noch nicht verfügbar)</span>'
                    : ''}
            `;

            // Tooltip on the item
            item.title = source.tooltip;

            const desc = document.createElement('div');
            desc.className = 'settings-source-desc';
            desc.textContent = source.description;

            const tooltip = document.createElement('span');
            tooltip.className = 'settings-tooltip-icon';
            tooltip.innerHTML = '?';
            tooltip.title = source.tooltip;

            item.appendChild(checkbox);
            item.appendChild(label);
            item.appendChild(tooltip);
            item.appendChild(desc);

            elements.settingsSourceList.appendChild(item);
        });

        elements.settingsSelectAll.checked = selected.size === selectableCount && selectableCount > 0;
        elements.settingsSelectAll.indeterminate = selected.size > 0 && selected.size < selectableCount;

        updateSettingsUI();
    }

    function updateSettingsUI() {
        const selected = state.selectedSources;
        const total = state.availableSources.length;
        const selectable = state.availableSources.filter(s => s.has_scraper).length;

        elements.settingsSourceCount.textContent =
            `${selected.length} von ${selectable} Quellen ausgewählt`;

        elements.settingsSaveBtn.disabled = !state.settingsDirty || selected.length === 0;
        elements.settingsReloadBtn.disabled = selected.length === 0;

        // Update select-all checkbox
        const allSelectable = state.availableSources.filter(s => s.has_scraper);
        elements.settingsSelectAll.checked = allSelectable.every(s => selected.includes(s.key));
        elements.settingsSelectAll.indeterminate =
            allSelectable.some(s => selected.includes(s.key)) &&
            !allSelectable.every(s => selected.includes(s.key));
    }

    async function handleSettingsSave() {
        if (!state.settingsDirty || state.selectedSources.length === 0) return;

        elements.settingsSaveBtn.disabled = true;
        elements.settingsStatus.classList.add('hidden');

        try {
            const response = await fetch(API_BASE + '/corpus/sources', {
                method: 'PUT',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ sources: state.selectedSources }),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.settingsDirty = false;
            elements.settingsSaveBtn.disabled = true;

            elements.settingsStatus.className = 'settings-status success';
            elements.settingsStatus.textContent = 'Auswahl gespeichert.';
            elements.settingsStatus.classList.remove('hidden');

            // Refresh active state
            state.availableSources.forEach(s => {
                s.active = state.selectedSources.includes(s.key);
            });
        } catch (err) {
            elements.settingsStatus.className = 'settings-status error';
            elements.settingsStatus.textContent = 'Fehler: ' + err.message;
            elements.settingsStatus.classList.remove('hidden');
            elements.settingsSaveBtn.disabled = false;
        }
    }

    async function handleSettingsReload() {
        if (state.settingsJobId) return;  // Already running

        // Reset state
        elements.settingsStatus.classList.add('hidden');
        elements.settingsProgress.classList.remove('hidden');
        elements.settingsSubstage.textContent = 'Auftrag wird eingereiht …';
        elements.settingsChunksCount.textContent = '';
        elements.settingsProgressFill.classList.remove('indeterminate');
        elements.settingsProgressFill.style.width = '0%';

        elements.settingsSaveBtn.disabled = true;
        elements.settingsReloadBtn.disabled = true;

        try {
            const response = await fetch(API_BASE + '/corpus/update', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ sources: state.selectedSources }),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.settingsJobId = data.job_id;
            elements.settingsSubstage.textContent = 'Auftrag gestartet …';
            pollSettingsStatus(data.job_id);
        } catch (err) {
            settingsLoadError(err.message);
        }
    }

    function pollSettingsStatus(jobId) {
        if (state.settingsPollingTimer) {
            clearTimeout(state.settingsPollingTimer);
        }

        state.settingsPollingTimer = setTimeout(async () => {
            try {
                const response = await fetch(API_BASE + '/corpus/status/' + jobId, {
                    method: 'GET',
                    headers: buildHeaders(),
                });

                if (!response.ok) {
                    if (response.status === 404) {
                        settingsLoadError('Auftrag nicht mehr im Speicher.');
                        return;
                    }
                    await handleApiError(response);
                    return;
                }

                const job = await response.json();
                updateSettingsProgress(job);

                if (job.status === 'completed' || job.status === 'failed') {
                    finishSettingsReload(job);
                } else {
                    pollSettingsStatus(jobId);
                }
            } catch (err) {
                settingsLoadError(err.message);
            }
        }, 2000);
    }

    function updateSettingsProgress(job) {
        if (job.substage) {
            const labels = {
                scraping: 'Rechtsquellen werden abgerufen und aufbereitet …',
                embedding: 'Vektordarstellungen (Embeddings) werden generiert …',
                upserting: 'Einträge werden in der Datenbank gespeichert …',
            };
            let label = labels[job.substage] || job.substage;

            if (job.substage === 'scraping' && job.current_source_display) {
                const sourceInfo = job.source_total
                    ? ` (Quelle ${job.source_index}/${job.source_total})`
                    : '';
                label = `${job.current_source_display} wird abgerufen …${sourceInfo}`;
            }
            elements.settingsSubstage.textContent = label;
        }

        if (job.substage === 'scraping' && job.chunks_scraped > 0) {
            elements.settingsChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke bisher abgerufen`;
        } else if (job.substage === 'embedding' && job.chunks_scraped > 0) {
            elements.settingsChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke werden verarbeitet`;
        } else if (job.substage === 'upserting' && job.chunks_scraped > 0) {
            elements.settingsChunksCount.textContent =
                `${job.chunks_scraped} Textblöcke in DB`;
        }

        if (job.status === 'running') {
            elements.settingsProgressFill.classList.add('indeterminate');
        }
    }

    function finishSettingsReload(job) {
        if (state.settingsPollingTimer) {
            clearTimeout(state.settingsPollingTimer);
            state.settingsPollingTimer = null;
        }
        state.settingsJobId = null;

        elements.settingsProgress.classList.add('hidden');
        elements.settingsReloadBtn.disabled = false;
        elements.settingsSaveBtn.disabled = !state.settingsDirty;

        elements.settingsStatus.classList.remove('hidden');

        if (job.status === 'completed') {
            const count = job.chunks_processed || 0;
            if (count > 0) {
                elements.settingsStatus.className = 'settings-status success';
                elements.settingsStatus.textContent =
                    `Corpus-Aktualisierung abgeschlossen: ${count} Texteinträge verarbeitet.`;
            } else {
                elements.settingsStatus.className = 'settings-status warning';
                elements.settingsStatus.textContent =
                    'Corpus-Aktualisierung abgeschlossen, aber keine Einträge gefunden.';
            }
        } else if (job.status === 'failed') {
            elements.settingsStatus.className = 'settings-status error';
            elements.settingsStatus.textContent =
                `Fehler: ${job.error || 'Corpus-Aktualisierung fehlgeschlagen.'}`;
        }
    }

    function settingsLoadError(message) {
        if (state.settingsPollingTimer) {
            clearTimeout(state.settingsPollingTimer);
            state.settingsPollingTimer = null;
        }
        state.settingsJobId = null;

        elements.settingsProgress.classList.add('hidden');
        elements.settingsReloadBtn.disabled = false;
        elements.settingsSaveBtn.disabled = !state.settingsDirty;

        elements.settingsStatus.className = 'settings-status error';
        elements.settingsStatus.textContent = `Fehler: ${message}`;
        elements.settingsStatus.classList.remove('hidden');
    }

    // =========================================================================
    // Case Chat — Interactive Pipeline Results
    // =========================================================================

    async function loadCaseSessions() {
        try {
            const response = await fetch(API_BASE + '/cases', { headers: buildHeaders() });
            if (!response.ok) { await handleApiError(response); return; }
            state.caseSessions = await response.json();
            renderCaseSessionList();
        } catch (err) {
            console.error('Failed to load case sessions:', err);
        }
    }

    function renderCaseSessionList() {
        elements.caseSessionList.innerHTML = '';
        if (state.caseSessions.length === 0) {
            elements.caseSessionEmpty.style.display = 'block';
            return;
        }
        elements.caseSessionEmpty.style.display = 'none';
        state.caseSessions.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
        state.caseSessions.forEach(cs => {
            const item = document.createElement('div');
            item.className = 'case-session-item';
            if (cs.id === state.activeCaseId) item.classList.add('active');
            item.innerHTML = `
                <div class="case-session-title">${escapeHtml(cs.title || 'Unbenannter Fall')}</div>
                <div class="case-session-meta">${relativeTime(cs.updated_at || cs.created_at)}</div>
                <div class="case-session-preview">${escapeHtml((cs.input_text || '').substring(0, 80))}</div>
            `;
            item.addEventListener('click', () => loadCaseSession(cs.id));
            elements.caseSessionList.appendChild(item);
        });
    }

    async function loadCaseSession(caseId, preloadedOutput) {
        state.activeCaseId = caseId;
        elements.caseChatSection.classList.remove('hidden');
        if (elements.resultReportSection) elements.resultReportSection.classList.add('hidden');
        elements.caseChatInput.disabled = false;
        elements.caseChatSendBtn.disabled = false;
        elements.caseChatMessages.innerHTML = '';
        renderCaseSessionList();

        if (preloadedOutput) {
            state.activeCaseData = { id: caseId, final_output: preloadedOutput };
            renderCaseSections(preloadedOutput);
            return;
        }

        try {
            const response = await fetch(API_BASE + '/cases/' + caseId, { headers: buildHeaders() });
            if (!response.ok) { await handleApiError(response); return; }
            const data = await response.json();
            state.activeCaseData = data;
            elements.caseTitle.textContent = data.title || 'Ergebnis';
            renderCaseSections(data.final_output);
            if (data.chat_history && data.chat_history.messages) {
                data.chat_history.messages.forEach(m => renderCaseChatMessage(m.role, m.content, m.created_at));
            }
        } catch (err) {
            showError('Fehler beim Laden des Falls: ' + err.message);
        }
    }

    function renderCaseSections(output) {
        if (!output) return;
        elements.caseSections.innerHTML = '';
        Object.entries(pipelineSectionLabels).forEach(([key, label]) => {
            const content = output[key] || '—';
            const sectionEl = document.createElement('div');
            sectionEl.className = 'case-section';
            sectionEl.id = 'case-section-' + key;
            sectionEl.innerHTML = `
                <div class="case-section-header" data-section="${key}">
                    <h3>${escapeHtml(label)}</h3>
                    <div class="case-section-toolbar">
                        <button class="btn-icon-only section-btn-rerun" data-section="${key}" title="Neu analysieren">🔄</button>
                        <button class="btn-icon-only section-btn-edit" data-section="${key}" title="Bearbeiten">✏️</button>
                        <button class="btn-icon-only section-btn-flag" data-section="${key}" title="Beanstanden">⚑</button>
                        <button class="btn-icon-only section-btn-confirm" data-section="${key}" title="Bestätigen">✓</button>
                        <button class="btn-icon-only section-btn-copy" data-section="${key}" title="Kopieren">📋</button>
                        <button class="btn-icon-only section-btn-export" data-section="${key}" title="Exportieren">📥</button>
                    </div>
                </div>
                <div class="case-section-body">
                    <div class="case-section-content">${formatCaseContent(content)}</div>
                </div>
            `;
            // Toggle collapse on header click
            sectionEl.querySelector('.case-section-header').addEventListener('click', function(e) {
                if (e.target.closest('.case-section-toolbar')) return;
                sectionEl.classList.toggle('collapsed');
            });
            // Wire toolbar buttons
            sectionEl.querySelector('.section-btn-copy').addEventListener('click', () => {
                navigator.clipboard.writeText(content).then(() => { /* brief flash */ });
            });
            sectionEl.querySelector('.section-btn-export').addEventListener('click', () => {
                downloadText(label + '.txt', content);
            });
            sectionEl.querySelector('.section-btn-rerun').addEventListener('click', () => {
                const stage = sectionToStage(key);
                if (stage) startTargetedReevaluate(stage, key);
            });
            sectionEl.querySelector('.section-btn-edit').addEventListener('click', () => {
                toggleSectionEdit(key, content);
            });
            sectionEl.querySelector('.section-btn-flag').addEventListener('click', () => {
                adjudicateSection(key, 'disputed');
            });
            sectionEl.querySelector('.section-btn-confirm').addEventListener('click', () => {
                adjudicateSection(key, 'agreed');
            });
            elements.caseSections.appendChild(sectionEl);
        });
    }

    function sectionToStage(sectionKey) {
        const map = {
            sachverhalt: 'normalization',
            rechtliche_wuerdigung: 'construction',
            ergebnis: 'generation',
            handlungsempfehlung: 'generation',
            entwurf: 'generation',
            unsicherheiten: 'verification',
            adversarial_pruefung: 'adversarial_review',
            berechnungspruefung: 'calculation_check',
        };
        return map[sectionKey] || null;
    }

    function formatCaseContent(content) {
        if (!content) return '<em>—</em>';
        return escapeHtml(content).replace(/\n/g, '<br>');
    }

    async function handleCaseChatSend() {
        const input = elements.caseChatInput.value.trim();
        if (!input || !state.activeCaseId || state.caseIsStreaming) return;
        elements.caseChatInput.value = '';
        elements.caseChatInput.dispatchEvent(new Event('input'));
        elements.caseChatSendBtn.disabled = true;
        state.caseIsStreaming = true;
        state.caseChatAbortController = new AbortController();
        // Render user message
        renderCaseChatMessage('user', input);
        // Show typing indicator
        const typingEl = addCaseTypingIndicator();
        try {
            const response = await fetch(API_BASE + '/cases/' + state.activeCaseId + '/chat', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }),
                body: JSON.stringify({ content: input }),
                signal: state.caseChatAbortController.signal,
            });
            if (!response.ok) { await handleApiError(response); return; }
            // Remove typing indicator, process SSE
            if (typingEl) typingEl.remove();
            await processCaseChatSSE(response);
        } catch (err) {
            if (err.name === 'AbortError') return;
            if (typingEl) typingEl.remove();
            renderCaseChatMessage('system', 'Fehler: ' + err.message);
        } finally {
            state.caseIsStreaming = false;
            elements.caseChatSendBtn.disabled = !elements.caseChatInput.value.trim();
        }
    }

    function renderCaseChatMessage(role, content, timestamp) {
        if (!content) return;
        elements.caseChatEmpty.style.display = 'none';
        const msgEl = document.createElement('div');
        msgEl.className = 'case-chat-message ' + role;
        const time = timestamp ? new Date(timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : '';
        msgEl.innerHTML = `
            <div class="case-chat-bubble">${formatCaseContent(content)}</div>
            ${time ? '<div class="case-chat-time">' + time + '</div>' : ''}
        `;
        elements.caseChatMessages.appendChild(msgEl);
        elements.caseChatMessages.scrollTop = elements.caseChatMessages.scrollHeight;
    }

    function addCaseTypingIndicator() {
        const el = document.createElement('div');
        el.className = 'case-chat-message assistant typing';
        el.innerHTML = '<div class="case-chat-bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
        elements.caseChatMessages.appendChild(el);
        elements.caseChatMessages.scrollTop = elements.caseChatMessages.scrollHeight;
        return el;
    }

    async function processCaseChatSSE(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentBubble = null;
        let accumulatedText = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        if (event.type === 'case_token') {
                            if (!currentBubble) {
                                currentBubble = document.createElement('div');
                                currentBubble.className = 'case-chat-message assistant';
                                currentBubble.innerHTML = '<div class="case-chat-bubble"></div>';
                                elements.caseChatMessages.appendChild(currentBubble);
                            }
                            accumulatedText += event.content;
                            currentBubble.querySelector('.case-chat-bubble').innerHTML = formatCaseContent(accumulatedText);
                            elements.caseChatMessages.scrollTop = elements.caseChatMessages.scrollHeight;
                        } else if (event.type === 'case_done') {
                            if (event.updated_sections) {
                                event.updated_sections.forEach(key => updateSectionContent(key, event.section_contents));
                            }
                        } else if (event.type === 'stage_reevaluate') {
                            const stageName = stageNames[event.stage] || event.stage;
                            renderCaseChatMessage('system', 'Neu-Analyse: ' + stageName + ' — ' + (event.status === 'complete' ? '✓ abgeschlossen' : 'läuft...'));
                        } else if (event.type === 'section_updated') {
                            updateSectionContent(event.section, { [event.section]: event.content });
                        } else if (event.error) {
                            renderCaseChatMessage('system', 'Fehler: ' + (event.detail || event.error));
                        }
                    } catch (e) { /* skip malformed */ }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') throw err;
        }
    }

    function updateSectionContent(sectionKey, contents) {
        if (!contents || !contents[sectionKey]) return;
        const sectionEl = document.getElementById('case-section-' + sectionKey);
        if (!sectionEl) return;
        const contentEl = sectionEl.querySelector('.case-section-content');
        if (contentEl) {
            contentEl.innerHTML = formatCaseContent(contents[sectionKey]);
        }
    }

    function toggleSectionEdit(sectionKey, currentContent) {
        const sectionEl = document.getElementById('case-section-' + sectionKey);
        if (!sectionEl) return;
        const bodyEl = sectionEl.querySelector('.case-section-body');
        const contentEl = sectionEl.querySelector('.case-section-content');
        const existingEditor = bodyEl.querySelector('.case-section-editor');
        if (existingEditor) {
            // Save
            const newContent = existingEditor.value;
            existingEditor.remove();
            contentEl.style.display = '';
            contentEl.innerHTML = formatCaseContent(newContent);
            saveSectionEdit(sectionKey, newContent);
        } else {
            // Edit mode
            contentEl.style.display = 'none';
            const textarea = document.createElement('textarea');
            textarea.className = 'case-section-editor';
            textarea.value = currentContent;
            textarea.rows = 10;
            bodyEl.insertBefore(textarea, contentEl);
            textarea.focus();
            const saveBtn = document.createElement('button');
            saveBtn.className = 'btn btn-small';
            saveBtn.textContent = 'Speichern';
            saveBtn.style.marginTop = '8px';
            saveBtn.addEventListener('click', () => {
                const newContent = textarea.value;
                textarea.remove();
                saveBtn.remove();
                contentEl.style.display = '';
                contentEl.innerHTML = formatCaseContent(newContent);
                saveSectionEdit(sectionKey, newContent);
            });
            bodyEl.appendChild(saveBtn);
        }
    }

    async function saveSectionEdit(sectionKey, newContent) {
        if (!state.activeCaseId) return;
        try {
            await fetch(API_BASE + '/cases/' + state.activeCaseId + '/adjudicate', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ target_type: 'section', target_id: sectionKey, status: 'edited', note: newContent }),
            });
        } catch (err) {
            console.error('Failed to save section edit:', err);
        }
    }

    async function adjudicateSection(sectionKey, status) {
        if (!state.activeCaseId) return;
        const note = status === 'disputed' ? prompt('Grund für Beanstandung (optional):') : '';
        try {
            await fetch(API_BASE + '/cases/' + state.activeCaseId + '/adjudicate', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ target_type: 'section', target_id: sectionKey, status, note: note || '' }),
            });
            // Update UI indicator
            const sectionEl = document.getElementById('case-section-' + sectionKey);
            if (sectionEl) {
                const existingBadge = sectionEl.querySelector('.adjudication-badge');
                if (existingBadge) existingBadge.remove();
                const badge = document.createElement('span');
                badge.className = 'adjudication-badge ' + status;
                badge.textContent = status === 'agreed' ? '✓ Bestätigt' : '⚑ Beanstandet';
                sectionEl.querySelector('.case-section-header h3').appendChild(badge);
            }
        } catch (err) {
            console.error('Failed to adjudicate section:', err);
        }
    }

    async function startTargetedReevaluate(stage, sectionKey) {
        if (!state.activeCaseId || state.caseIsStreaming) return;
        const context = prompt('Kontext für Neu-Analyse (optional):', '');
        if (context === null) return; // cancelled
        state.caseIsStreaming = true;
        state.caseChatAbortController = new AbortController();
        renderCaseChatMessage('system', 'Starte gezielte Neu-Analyse von "' + (stageNames[stage] || stage) + '"...');
        try {
            const response = await fetch(API_BASE + '/cases/' + state.activeCaseId + '/reevaluate', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }),
                body: JSON.stringify({ stage, context: context || '' }),
                signal: state.caseChatAbortController.signal,
            });
            if (!response.ok) { await handleApiError(response); return; }
            await processCaseChatSSE(response);
        } catch (err) {
            if (err.name === 'AbortError') return;
            renderCaseChatMessage('system', 'Fehler bei Neu-Analyse: ' + err.message);
        } finally {
            state.caseIsStreaming = false;
        }
    }

    async function handleCaseDelete() {
        if (!state.activeCaseId) return;
        if (!confirm('Diesen Fall wirklich löschen?')) return;
        try {
            const response = await fetch(API_BASE + '/cases/' + state.activeCaseId, {
                method: 'DELETE',
                headers: buildHeaders(),
            });
            if (!response.ok) { await handleApiError(response); return; }
            state.activeCaseId = null;
            state.activeCaseData = null;
            elements.caseChatSection.classList.add('hidden');
            elements.resultsSection.classList.remove('hidden');
            loadCaseSessions();
        } catch (err) {
            showError('Fehler beim Löschen: ' + err.message);
        }
    }

    async function handleCaseExport() {
        if (!state.activeCaseId) return;
        try {
            const response = await fetch(API_BASE + '/cases/' + state.activeCaseId + '/export?format=markdown', {
                headers: buildHeaders(),
            });
            if (!response.ok) { await handleApiError(response); return; }
            const data = await response.json();
            downloadText('citizen-analyse-' + state.activeCaseId.substring(0, 8) + '.md', data.content || JSON.stringify(data, null, 2));
        } catch (err) {
            showError('Fehler beim Export: ' + err.message);
        }
    }

    async function handleCaseCompare() {
        await loadCaseSessions();
        const otherCases = state.caseSessions.filter(cs => cs.id !== state.activeCaseId);
        elements.caseCompareSelect.innerHTML = '<option value="">— Fall auswählen —</option>' +
            otherCases.map(cs => `<option value="${cs.id}">${escapeHtml(cs.title || cs.id.substring(0, 8))} (${relativeTime(cs.created_at)})</option>`).join('');
        elements.caseCompareOverlay.classList.remove('hidden');
    }

    async function handleCaseCompareLoad() {
        const compareId = elements.caseCompareSelect.value;
        if (!compareId) return;
        try {
            const response = await fetch(API_BASE + '/cases/' + compareId, { headers: buildHeaders() });
            if (!response.ok) { await handleApiError(response); return; }
            state.compareCaseData = await response.json();
            renderComparePanels();
        } catch (err) {
            alert('Fehler beim Laden des Vergleichsfalls: ' + err.message);
        }
    }

    function renderComparePanels() {
        if (!state.activeCaseData || !state.compareCaseData) return;
        const left = state.activeCaseData.final_output;
        const right = state.compareCaseData.final_output;
        elements.caseCompareLeft.innerHTML = '';
        elements.caseCompareRight.innerHTML = '';
        Object.entries(pipelineSectionLabels).forEach(([key, label]) => {
            const leftContent = left[key] || '—';
            const rightContent = right[key] || '—';
            const isDiff = leftContent !== rightContent;
            elements.caseCompareLeft.innerHTML += `
                <div class="compare-section${isDiff ? ' compare-diff' : ''}">
                    <h4>${escapeHtml(label)}</h4>
                    <div>${formatCaseContent(leftContent)}</div>
                </div>
            `;
            elements.caseCompareRight.innerHTML += `
                <div class="compare-section${isDiff ? ' compare-diff' : ''}">
                    <h4>${escapeHtml(label)}</h4>
                    <div>${formatCaseContent(rightContent)}</div>
                </div>
            `;
        });
    }

    function handleCaseCompareClose() {
        elements.caseCompareOverlay.classList.add('hidden');
        state.compareCaseData = null;
    }

    function downloadText(filename, text) {
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // Chat: Sidebar & Conversation List
    // =========================================================================

    async function loadConversations() {
        try {
            elements.conversationError.classList.add('hidden');

            const response = await fetch(API_BASE + '/conversations', {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.conversations = Array.isArray(data) ? data : [];
            renderConversationList();
        } catch (err) {
            elements.conversationError.textContent = 'Fehler beim Laden der Unterhaltungen.';
            elements.conversationError.classList.remove('hidden');
            console.error('Failed to load conversations:', err);
        }
    }

    function renderConversationList() {
        elements.conversationList.innerHTML = '';

        if (state.conversations.length === 0) {
            elements.conversationEmpty.style.display = 'flex';
            elements.conversationList.style.display = 'none';
            return;
        }

        elements.conversationEmpty.style.display = 'none';
        elements.conversationList.style.display = 'block';

        // Sort by most recent activity
        const sorted = [...state.conversations].sort((a, b) =>
            new Date(b.updated_at) - new Date(a.updated_at)
        );

        sorted.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (conv.id === state.activeConversationId) {
                item.classList.add('active');
            }

            const title = conv.title || 'Unterhaltung';
            const truncatedTitle = title.length > 30 ? title.slice(0, 30) + '…' : title;
            const date = conv.updated_at || conv.created_at;

            // Get preview from last message if available (loaded via detail)
            const preview = conv._lastMessagePreview || '';

            item.innerHTML = `
                <div class="conversation-item-title">${escapeHtml(truncatedTitle)}</div>
                <div class="conversation-item-date">${date ? relativeTime(date) : ''}</div>
                ${preview ? `<div class="conversation-item-preview">${escapeHtml(truncateText(preview, 55))}</div>` : ''}
            `;

            item.addEventListener('click', () => selectConversation(conv.id));
            elements.conversationList.appendChild(item);
        });
    }

    async function createConversation(title) {
        try {
            const formData = new FormData();
            if (title && title.trim()) {
                formData.append('title', title.trim());
            }

            const response = await fetch(API_BASE + '/conversations', {
                method: 'POST',
                headers: buildHeaders({ 'Accept': 'application/json' }),
                body: formData,
            });

            if (!response.ok) {
                await handleApiError(response);
                return null;
            }

            const data = await response.json();
            return data;
        } catch (err) {
            console.error('Failed to create conversation:', err);
            showChatError('Fehler beim Erstellen der Unterhaltung.');
            return null;
        }
    }

    async function selectConversation(conversationId) {
        if (state.activeConversationId === conversationId) return;

        state.activeConversationId = conversationId;
        state.conversationDocuments = [];
        state.isStreaming = false;

        // Update UI
        elements.chatEmptyState.classList.add('hidden');
        elements.chatMessages.innerHTML = '';
        elements.chatDeleteBtn.classList.remove('hidden');

        // Enable input
        elements.chatInput.disabled = false;
        elements.chatSendBtn.disabled = state.isStreaming;
        elements.chatAttachBtn.disabled = state.isStreaming;

        // Highlight active conversation
        renderConversationList();

        // Close sidebar on mobile
        closeSidebar();

        try {
            // Load full conversation detail
            const response = await fetch(API_BASE + '/conversations/' + conversationId, {
                method: 'GET',
                headers: buildHeaders({ 'Accept': 'application/json' }),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();

            // Update title
            elements.chatTitle.textContent = data.title || 'Unterhaltung';
            document.title = 'Citizen — ' + (data.title || 'Chat');

            // Load messages
            elements.chatMessages.innerHTML = '';
            if (data.messages && data.messages.length > 0) {
                elements.chatEmptyState.classList.add('hidden');
                data.messages.forEach(msg => {
                    renderMessage(msg.role, msg.content, msg.created_at);
                });
            } else {
                elements.chatEmptyState.classList.remove('hidden');
            }

            // Load documents
            state.conversationDocuments = data.documents || [];
            renderDocumentChips();

            // Scroll to bottom
            scrollToBottom();
        } catch (err) {
            showChatError('Fehler beim Laden der Unterhaltung.');
            console.error('Failed to load conversation:', err);
        }
    }

    async function handleNewConversation() {
        // Prompt for optional title
        const title = prompt('Titel der Unterhaltung (optional):', '');
        const finalTitle = title && title.trim() ? title.trim() : 'Unterhaltung';

        elements.newConversationBtn.disabled = true;

        try {
            const conv = await createConversation(finalTitle);
            if (conv) {
                // Add to local state
                state.conversations.unshift({
                    id: conv.id,
                    title: conv.title || finalTitle,
                    created_at: conv.created_at || new Date().toISOString(),
                    updated_at: conv.updated_at || conv.created_at || new Date().toISOString(),
                });

                renderConversationList();
                selectConversation(conv.id);
            }
        } finally {
            elements.newConversationBtn.disabled = false;
        }
    }

    async function handleDeleteConversation() {
        if (!state.activeConversationId) return;

        const confirmed = confirm(
            'Möchten Sie diese Unterhaltung wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.'
        );
        if (!confirmed) return;

        try {
            const response = await fetch(
                API_BASE + '/conversations/' + state.activeConversationId,
                {
                    method: 'DELETE',
                    headers: buildHeaders({ 'Accept': 'application/json' }),
                }
            );

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            // Remove from local state
            state.conversations = state.conversations.filter(
                c => c.id !== state.activeConversationId
            );

            // Reset active conversation
            state.activeConversationId = null;
            state.conversationDocuments = [];
            state.isStreaming = false;

            elements.chatMessages.innerHTML = '';
            elements.chatEmptyState.classList.remove('hidden');
            elements.chatTitle.textContent = 'Citizen Chat';
            elements.chatDeleteBtn.classList.add('hidden');
            elements.chatInput.disabled = true;
            elements.chatSendBtn.disabled = true;
            elements.chatAttachBtn.disabled = false;
            elements.chatDocChips.classList.add('hidden');
            document.title = 'Citizen — Legal Reasoning Engine';

            renderConversationList();
        } catch (err) {
            showChatError('Fehler beim Löschen der Unterhaltung.');
            console.error('Failed to delete conversation:', err);
        }
    }

    // =========================================================================
    // Chat: Messages
    // =========================================================================

    /**
     * Render a message bubble in the chat area
     */
    function renderMessage(role, content, createdAt, isPartial) {
        const wrapper = document.createElement('div');
        wrapper.className = `chat-message ${role}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';

        if (role === 'assistant') {
            // Parse markdown-like content (basic)
            bubble.innerHTML = formatMessageContent(content, isPartial);
            if (isPartial) {
                bubble.classList.add('streaming');
            }
        } else if (role === 'system') {
            bubble.textContent = content;
        } else {
            bubble.textContent = content;
        }

        wrapper.appendChild(bubble);

        if (createdAt) {
            const time = document.createElement('div');
            time.className = 'message-time';
            time.textContent = relativeTime(createdAt);
            wrapper.appendChild(time);
        }

        elements.chatMessages.appendChild(wrapper);
        elements.chatEmptyState.classList.add('hidden');

        return wrapper;
    }

    /**
     * Basic markdown-like formatting for assistant messages
     */
    function formatMessageContent(content, isPartial) {
        if (!content) return '';

        let html = escapeHtml(content);

        // Bold: **text**
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // Italic: *text* (but not if already processed by bold)
        html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');

        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
        });
    }

    // =========================================================================
    // Chat: Document Upload
    // =========================================================================

    async function uploadChatDocument(file) {
        if (!state.activeConversationId) return false;

        const validationError = validateChatFile(file);
        if (validationError) {
            showChatError(validationError);
            return false;
        }

        // Add uploading chip
        const chip = addDocumentChip(file.name, file.size, true);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(
                API_BASE + '/conversations/' + state.activeConversationId + '/documents',
                {
                    method: 'POST',
                    headers: buildHeaders({ 'Accept': 'application/json' }),
                    body: formData,
                }
            );

            if (!response.ok) {
                await handleApiError(response);
                return false;
            }

            const data = await response.json();

            // Add to state
            state.conversationDocuments.push(data);

            // Re-render chips (removes uploading state)
            renderDocumentChips();

            // Show system notification in chat
            addSystemMessage(
                `Dokument '${escapeHtml(data.original_filename)}' wurde hinzugefügt`
            );

            return true;
        } catch (err) {
            console.error('Failed to upload document:', err);
            showChatError('Fehler beim Hochladen des Dokuments: ' + err.message);

            // Remove uploading chip on error
            renderDocumentChips();
            return false;
        }
    }

    function addDocumentChip(name, size, isUploading) {
        const chip = document.createElement('div');
        chip.className = 'chat-doc-chip' + (isUploading ? ' uploading' : '');
        chip.innerHTML = `
            <svg class="doc-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span class="doc-chip-name">${escapeHtml(name)}</span>
            <span class="doc-chip-size">${size ? formatFileSize(size) : ''}</span>
        `;

        elements.chatDocChips.appendChild(chip);
        elements.chatDocChips.classList.remove('hidden');
        return chip;
    }

    function renderDocumentChips() {
        elements.chatDocChips.innerHTML = '';

        if (state.conversationDocuments.length === 0) {
            elements.chatDocChips.classList.add('hidden');
            return;
        }

        elements.chatDocChips.classList.remove('hidden');

        state.conversationDocuments.forEach(doc => {
            const chip = document.createElement('div');
            chip.className = 'chat-doc-chip';
            chip.innerHTML = `
                <svg class="doc-chip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <span class="doc-chip-name">${escapeHtml(doc.original_filename || doc.filename || 'Dokument')}</span>
                <button class="doc-chip-remove" title="Dokument entfernen">&times;</button>
            `;

            const removeBtn = chip.querySelector('.doc-chip-remove');
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                removeDocument(doc.id);
            });

            elements.chatDocChips.appendChild(chip);
        });
    }

    async function removeDocument(docId) {
        if (!state.activeConversationId) return;

        try {
            const response = await fetch(
                API_BASE + '/conversations/' + state.activeConversationId + '/documents/' + docId,
                {
                    method: 'DELETE',
                    headers: buildHeaders({ 'Accept': 'application/json' }),
                }
            );

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            state.conversationDocuments = state.conversationDocuments.filter(
                d => String(d.id) !== String(docId)
            );
            renderDocumentChips();
        } catch (err) {
            console.error('Failed to remove document:', err);
            showChatError('Fehler beim Entfernen des Dokuments.');
        }
    }

    function addSystemMessage(content) {
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message system';

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = content;

        wrapper.appendChild(bubble);

        const time = document.createElement('div');
        time.className = 'message-time';
        time.textContent = relativeTime(new Date().toISOString());
        wrapper.appendChild(time);

        elements.chatMessages.appendChild(wrapper);
        elements.chatEmptyState.classList.add('hidden');
        scrollToBottom();

        // Refresh conversation list to update preview
        // Debounce this slightly
        clearTimeout(state._refreshTimer);
        state._refreshTimer = setTimeout(() => loadConversations(), 1000);
    }

    // =========================================================================
    // Chat: Message Sending & SSE Streaming
    // =========================================================================

    async function sendMessage() {
        const content = elements.chatInput.value.trim();
        if (!content || state.isStreaming) return;

        // If no active conversation, create one first
        if (!state.activeConversationId) {
            const autoTitle = content.length > 40
                ? content.slice(0, 40) + '…'
                : content;

            elements.chatSendBtn.disabled = true;
            elements.chatInput.disabled = true;

            const conv = await createConversation(autoTitle);
            if (!conv) {
                elements.chatSendBtn.disabled = false;
                elements.chatInput.disabled = false;
                return;
            }

            state.conversations.unshift({
                id: conv.id,
                title: conv.title || autoTitle,
                created_at: conv.created_at || new Date().toISOString(),
                updated_at: conv.updated_at || new Date().toISOString(),
            });

            renderConversationList();
            state.activeConversationId = conv.id;

            elements.chatDeleteBtn.classList.remove('hidden');
            elements.chatTitle.textContent = conv.title || autoTitle;

            elements.chatEmptyState.classList.add('hidden');
            elements.chatMessages.innerHTML = '';
        }

        state.isStreaming = true;
        elements.chatSendBtn.disabled = true;
        elements.chatInput.disabled = true;
        elements.chatAttachBtn.disabled = true;

        const messageContent = content;
        elements.chatInput.value = '';
        elements.chatInput.style.height = 'auto';

        // Render user message immediately
        const userMsg = renderMessage('user', messageContent, new Date().toISOString());

        // Create assistant placeholder
        const assistantWrapper = document.createElement('div');
        assistantWrapper.className = 'chat-message assistant';
        const assistantBubble = document.createElement('div');
        assistantBubble.className = 'message-bubble';

        // Start with typing indicator
        assistantBubble.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        assistantWrapper.appendChild(assistantBubble);
        elements.chatMessages.appendChild(assistantWrapper);

        scrollToBottom();

        // Create AbortController for potential cancellation
        state.streamingAbortController = new AbortController();

        try {
            const headers = buildHeaders({
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
            });

            const response = await fetch(
                API_BASE + '/conversations/' + state.activeConversationId + '/messages',
                {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ content: messageContent }),
                    signal: state.streamingAbortController.signal,
                }
            );

            if (!response.ok) {
                await handleApiError(response);
                throw new Error('API request failed');
            }

            await processChatSSEStream(response, assistantBubble, assistantWrapper);
        } catch (err) {
            if (err.name === 'AbortError') {
                // Stream was cancelled
                return;
            }
            console.error('Message send failed:', err);

            // Remove placeholder on error
            if (assistantBubble.querySelector('.typing-indicator')) {
                assistantBubble.innerHTML = '';
                assistantBubble.classList.add('chat-error-inline');
                assistantBubble.textContent = 'Fehler: ' + (err.message || 'Unbekannter Fehler');
            }
        } finally {
            state.isStreaming = false;
            state.streamingAbortController = null;
            elements.chatSendBtn.disabled = false;
            elements.chatInput.disabled = false;
            elements.chatAttachBtn.disabled = false;
            elements.chatInput.focus();

            // Refresh conversation list to update timestamps
            loadConversations();
        }
    }

    /**
     * Process SSE stream from chat message endpoint.
     * Handles both pipeline mode (first message with documents) and
     * chat+RAG mode (subsequent messages).
     */
    async function processChatSSEStream(response, bubbleEl, wrapperEl) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentContent = '';
        let hasReceivedContent = false;

        // For pipeline mode
        let pipelineStagesCompleted = 0;
        let isPipelineMode = false;
        let pipelineProgressEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                const dataStr = line.slice(6).trim();
                if (!dataStr) continue;

                try {
                    const event = JSON.parse(dataStr);
                    handleChatSSEEvent(
                        event,
                        bubbleEl,
                        wrapperEl,
                        {
                            currentContent,
                            hasReceivedContent,
                            isPipelineMode,
                            pipelineStagesCompleted,
                            pipelineProgressEl,
                        },
                        (updates) => {
                            currentContent = updates.currentContent;
                            hasReceivedContent = updates.hasReceivedContent;
                            isPipelineMode = updates.isPipelineMode;
                            pipelineStagesCompleted = updates.pipelineStagesCompleted;
                            pipelineProgressEl = updates.pipelineProgressEl;
                        }
                    );
                } catch (err) {
                    console.error('Failed to parse chat SSE event:', err, dataStr);
                }
            }
        }
    }

    function handleChatSSEEvent(event, bubbleEl, wrapperEl, ctx, setCtx) {
        // Error event
        if (event.error) {
            bubbleEl.innerHTML = '';
            const errorDiv = document.createElement('div');
            errorDiv.className = 'chat-error-inline';
            errorDiv.textContent = 'Fehler: ' + (event.detail || event.error || 'Unbekannter Fehler');
            bubbleEl.appendChild(errorDiv);
            return;
        }

        // Pipeline stage event (first message with documents)
        if (event.stage) {
            handlePipelineStageEvent(event, bubbleEl, wrapperEl, ctx, setCtx);
            return;
        }

        // Final pipeline output
        if (event.final_output) {
            handlePipelineFinalOutput(event, bubbleEl, wrapperEl);
            return;
        }

        // Token event (chat+RAG mode)
        if (event.type === 'token') {
            handleTokenEvent(event, bubbleEl, ctx, setCtx);
            return;
        }

        // Done event
        if (event.type === 'done') {
            handleDoneEvent(event, bubbleEl, wrapperEl, ctx, setCtx);
            return;
        }
    }

    function handlePipelineStageEvent(event, bubbleEl, wrapperEl, ctx, setCtx) {
        if (!ctx.isPipelineMode) {
            ctx.isPipelineMode = true;
            setCtx(ctx);

            // Clear typing indicator and create pipeline progress UI
            bubbleEl.innerHTML = '';

            const progressDiv = document.createElement('div');
            progressDiv.className = 'pipeline-progress';

            const progressBar = document.createElement('div');
            progressBar.className = 'pipeline-progress-bar';
            const progressFill = document.createElement('div');
            progressFill.className = 'pipeline-progress-fill';
            progressBar.appendChild(progressFill);

            const stageLabel = document.createElement('div');
            stageLabel.className = 'pipeline-stage-label';
            stageLabel.textContent = 'Pipeline wird gestartet …';

            progressDiv.appendChild(progressBar);
            progressDiv.appendChild(stageLabel);
            bubbleEl.appendChild(progressDiv);

            ctx.pipelineProgressEl = { fill: progressFill, label: stageLabel };
            setCtx(ctx);
        }

        if (event.status === 'complete') {
            ctx.pipelineStagesCompleted++;
            setCtx(ctx);

            const totalStages = pipelineStages.length;
            const pct = (ctx.pipelineStagesCompleted / totalStages) * 100;
            ctx.pipelineProgressEl.fill.style.width = `${pct}%`;

            const stageLabel = stageNames[event.stage] || event.stage;
            ctx.pipelineProgressEl.label.textContent =
                `${stageLabel} abgeschlossen (${ctx.pipelineStagesCompleted}/${totalStages})`;
        } else if (event.status === 'running') {
            const stageLabel = stageNames[event.stage] || event.stage;
            ctx.pipelineProgressEl.label.textContent = `${stageLabel} wird ausgeführt …`;
        }
    }

    function handlePipelineFinalOutput(event, bubbleEl, wrapperEl) {
        // Replace pipeline progress with collapsible sections
        bubbleEl.innerHTML = '';

        const sections = event.sections || Object.keys(event.final_output);
        const output = event.final_output;

        sections.forEach(key => {
            const label = pipelineSectionLabels[key] || key;
            const content = output[key] || '—';

            const collapsible = document.createElement('div');
            collapsible.className = 'result-collapsible';
            collapsible.innerHTML = `
                <button class="result-collapsible-header">
                    <span>${escapeHtml(label)}</span>
                    <span class="collapse-arrow">▶</span>
                </button>
                <div class="result-collapsible-body">
                    <div class="result-collapsible-body-inner">${formatContent(content)}</div>
                </div>
            `;

            const header = collapsible.querySelector('.result-collapsible-header');
            header.addEventListener('click', () => {
                collapsible.classList.toggle('open');
            });

            // Open first section by default
            if (sections.indexOf(key) === 0) {
                collapsible.classList.add('open');
            }

            bubbleEl.appendChild(collapsible);
        });

        // Add timestamp
        ensureTimestamp(wrapperEl);
    }

    function handleTokenEvent(event, bubbleEl, ctx, setCtx) {
        // Clear typing indicator on first token
        if (!ctx.hasReceivedContent) {
            ctx.hasReceivedContent = true;
            setCtx(ctx);
            bubbleEl.querySelector('.typing-indicator')?.remove();
        }

        ctx.currentContent += (event.content || '');
        setCtx(ctx);

        // Update bubble content
        bubbleEl.innerHTML = formatMessageContent(ctx.currentContent, true);
        scrollToBottom();
    }

    function handleDoneEvent(event, bubbleEl, wrapperEl, ctx, setCtx) {
        // Finalize content if we were in streaming mode
        if (ctx.hasReceivedContent && event.full_response) {
            bubbleEl.innerHTML = formatMessageContent(event.full_response, false);
        }

        // Ensure timestamp
        ensureTimestamp(wrapperEl);

        // Scroll to bottom
        scrollToBottom();
    }

    function ensureTimestamp(wrapperEl) {
        if (!wrapperEl.querySelector('.message-time')) {
            const time = document.createElement('div');
            time.className = 'message-time';
            time.textContent = relativeTime(new Date().toISOString());
            wrapperEl.appendChild(time);
        }
    }

    // =========================================================================
    // Chat: Error Display
    // =========================================================================

    function showChatError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'chat-error-inline';
        errorDiv.textContent = message;
        elements.chatMessages.appendChild(errorDiv);

        // Auto-remove after 6 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 6000);

        scrollToBottom();
    }

    // =========================================================================
    // Chat: Sidebar Toggle (Mobile)
    // =========================================================================

    function toggleSidebar() {
        const sidebar = elements.chatSidebar;
        const isOpen = sidebar.classList.contains('open');

        if (isOpen) {
            closeSidebar();
        } else {
            openSidebar();
        }
    }

    function openSidebar() {
        elements.chatSidebar.classList.add('open');

        // Add overlay if it doesn't exist
        let overlay = document.querySelector('.sidebar-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay';
            elements.chatMode.appendChild(overlay);
            overlay.addEventListener('click', closeSidebar);
        }
        overlay.classList.add('visible');
    }

    function closeSidebar() {
        elements.chatSidebar.classList.remove('open');
        const overlay = document.querySelector('.sidebar-overlay');
        if (overlay) {
            overlay.classList.remove('visible');
        }
    }

    // =========================================================================
    // Chat: Drag & Drop
    // =========================================================================

    function handleChatDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        elements.chatMode.classList.add('drag-over');
    }

    function handleChatDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        // Only remove if we left the chat mode entirely
        if (!elements.chatMode.contains(e.relatedTarget)) {
            elements.chatMode.classList.remove('drag-over');
        }
    }

    function handleChatDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        elements.chatMode.classList.remove('drag-over');

        if (!state.activeConversationId) {
            showChatError('Bitte erst eine Unterhaltung auswählen oder erstellen.');
            return;
        }

        const files = e.dataTransfer.files;
        if (files.length === 0) return;

        Array.from(files).forEach(file => {
            uploadChatDocument(file);
        });
    }

    // =========================================================================
    // Chat: Auto-resize Textarea
    // =========================================================================

    function autoResizeTextarea() {
        const textarea = elements.chatInput;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }

    // =========================================================================
    // Chat: Event Handlers
    // =========================================================================

    function handleChatInputKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!state.isStreaming && elements.chatInput.value.trim()) {
                sendMessage();
            }
        }
    }

    function handleChatSend() {
        if (!state.isStreaming && elements.chatInput.value.trim()) {
            sendMessage();
        }
    }

    function handleChatAttach() {
        if (!state.activeConversationId) {
            showChatError('Bitte erst eine Unterhaltung auswählen oder erstellen.');
            return;
        }
        elements.chatFileInput.click();
    }

    async function handleChatFileSelect(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        if (!state.activeConversationId) {
            showChatError('Bitte erst eine Unterhaltung auswählen oder erstellen.');
            elements.chatFileInput.value = '';
            return;
        }

        for (const file of files) {
            await uploadChatDocument(file);
        }

        elements.chatFileInput.value = '';
    }

    // =========================================================================
    // Initialization
    // =========================================================================

    async function init() {
        // Always register disclaimer event listeners
        elements.disclaimerCheckbox.addEventListener('change', handleDisclaimerCheckbox);
        elements.acknowledgeBtn.addEventListener('click', handleAcknowledge);

        // Check disclaimer status
        const accepted = await checkDisclaimerStatus();
        if (!accepted) {
            showDisclaimerModal();
        }

    // =========================================================================
    // 3-step intake flow (Step 1 → 2 → 3 → Pipeline)
    // =========================================================================

    const LEGAL_AREA_LABELS = {
        sozialrecht: 'Sozialrecht',
        erbrecht: 'Erbrecht',
        schenkungsrecht: 'Schenkungsrecht',
        familienrecht: 'Familienrecht',
        mietrecht: 'Mietrecht',
        arbeitsrecht: 'Arbeitsrecht',
        vertragsrecht: 'Vertragsrecht',
        verwaltungsrecht: 'Verwaltungsrecht',
        strafrecht: 'Strafrecht',
        andere: 'Andere',
    };

    // WP-02: Support tier for legal areas (v1.0.0 scope cut)
    const LEGAL_AREA_TIER = {
        sozialrecht: 'supported',
        erbrecht: 'experimental',
        schenkungsrecht: 'experimental',
        familienrecht: 'experimental',
        mietrecht: 'experimental',
        arbeitsrecht: 'experimental',
        vertragsrecht: 'experimental',
        verwaltungsrecht: 'experimental',
        strafrecht: 'experimental',
        andere: 'experimental',
    };

    function gotoStep(step) {
        state.currentStep = step;
        elements.uploadSection.classList.toggle('hidden', step !== 1);
        elements.intakeSection.classList.toggle('hidden', step !== 2);
        elements.confirmationSection.classList.toggle('hidden', step !== 3);
        elements.progressSection.classList.add('hidden');
        // Update step indicator
        document.querySelectorAll('.step-indicator .step').forEach((el) => {
            const elStep = parseInt(el.dataset.step, 10);
            el.classList.toggle('active', elStep === step);
            el.classList.toggle('completed', elStep < step);
        });
        // Scroll to top
        elements.analyzeMode.scrollTo({ top: 0, behavior: 'smooth' });
    }

    async function startIntakeFlow() {
        if (!state.extractedText || !state.extractedText.trim()) {
            showError('Bitte zuerst einen Fall schildern.');
            return;
        }
        elements.useTextBtn.disabled = true;
        elements.useTextBtn.textContent = 'Interview wird gestartet …';

        try {
            const resp = await fetch(API_BASE + '/intake/start', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    session_id: state.sessionId,
                    initial_text: state.extractedText,
                    max_turns: 8,
                }),
            });
            if (!resp.ok) {
                await handleApiError(resp);
                elements.useTextBtn.disabled = false;
                elements.useTextBtn.textContent = 'Fall aufnehmen →';
                return;
            }
            const data = await resp.json();
            state.intakeSession = data;
            renderIntake(data);
            await loadAvailableSources();
            await runReadinessCheck();
            gotoStep(2);
        } catch (err) {
            showError('Intake konnte nicht gestartet werden: ' + err.message);
            elements.useTextBtn.disabled = false;
            elements.useTextBtn.textContent = 'Fall aufnehmen →';
        }
    }

    function renderIntake(data) {
        const messages = data.messages || [];
        const html = messages.map((m) => {
            const cls = m.role === 'user' ? 'intake-msg-user' : 'intake-msg-assistant';
            return `<div class="intake-msg ${cls}"><div class="intake-msg-bubble">${escapeHtml(m.content)}</div></div>`;
        }).join('');
        elements.intakeMessages.innerHTML = html;
        elements.intakeMessages.scrollTop = elements.intakeMessages.scrollHeight;

        const turn = data.turn_count || 0;
        const max = data.max_turns || 8;
        elements.intakeTurnCounter.textContent = `Frage ${turn} von max. ${max}`;
        elements.intakeInput.disabled = data.status !== 'active';
        elements.intakeSendBtn.disabled = data.status !== 'active';

        if (data.status === 'completed') {
            finalizeIntakeIntoConfirmation(data);
        }
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    async function sendIntakeMessage() {
        const text = elements.intakeInput.value.trim();
        if (!text || !state.intakeSession) return;
        elements.intakeSendBtn.disabled = true;
        try {
            const resp = await fetch(API_BASE + `/intake/${state.intakeSession.id}/message`, {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ message: text }),
            });
            if (resp.status === 409) {
                // turn cap reached
                await confirmIntake();
                return;
            }
            if (!resp.ok) {
                await handleApiError(resp);
                elements.intakeSendBtn.disabled = false;
                return;
            }
            const data = await resp.json();
            state.intakeSession = data;
            elements.intakeInput.value = '';
            renderIntake(data);
        } catch (err) {
            showError('Senden fehlgeschlagen: ' + err.message);
            elements.intakeSendBtn.disabled = false;
        }
    }

    async function confirmIntake() {
        if (!state.intakeSession) return;
        try {
            const resp = await fetch(API_BASE + `/intake/${state.intakeSession.id}/confirm`, {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({}),
            });
            if (!resp.ok) {
                await handleApiError(resp);
                return;
            }
            const data = await resp.json();
            state.intakeSession = data;
            finalizeIntakeIntoConfirmation(data);
        } catch (err) {
            showError('Bestätigen fehlgeschlagen: ' + err.message);
        }
    }

    function finalizeIntakeIntoConfirmation(data) {
        const result = data.intake_result || {};
        const primary = data.primary_area || result.primary_area || 'andere';
        const secondary = data.secondary_areas || result.secondary_areas || [];
        state.intakeSelectedAreas = [primary, ...secondary.filter((a) => a !== primary)];

        // Render the preset card
        renderPresetCard();
        gotoStep(3);
    }

    function renderPresetCard() {
        const body = elements.presetCardBody;
        const areas = state.intakeSelectedAreas.length
            ? state.intakeSelectedAreas
            : ['sozialrecht'];

        body.innerHTML = areas.map((area, i) => {
            const label = LEGAL_AREA_LABELS[area] || area;
            const tier = LEGAL_AREA_TIER[area] || 'experimental';
            const isPrimary = i === 0;
            const expBadge = tier !== 'supported'
                ? '<span class="experimental-badge" title="Noch kein evaluierter Goldstandard verfügbar. Ergebnisse können unzuverlässig sein.">experimentell</span>'
                : '';
            return `
                <label class="preset-area-item">
                    <input type="checkbox" data-area="${escapeHtml(area)}" ${i < areas.length ? 'checked' : ''}>
                    <span class="preset-area-label">${escapeHtml(label)}</span>
                    ${isPrimary ? '<span class="preset-primary-badge">Hauptgebiet</span>' : ''}
                    ${expBadge}
                </label>
            `;
        }).join('');

        // Allow adding 'andere' if nothing selected
        body.innerHTML += `
            <label class="preset-area-item preset-area-add">
                <select id="preset-area-add-select">
                    <option value="">+ Weiteres Rechtsgebiet hinzufügen</option>
                    ${Object.keys(LEGAL_AREA_LABELS).filter((a) => !areas.includes(a)).map((a) =>
                        `<option value="${a}">${escapeHtml(LEGAL_AREA_LABELS[a])}</option>`).join('')}
                </select>
            </label>
        `;

        // Wire change handlers
        body.querySelectorAll('input[type="checkbox"][data-area]').forEach((cb) => {
            cb.addEventListener('change', () => {
                const area = cb.dataset.area;
                if (cb.checked) {
                    if (!state.intakeSelectedAreas.includes(area)) {
                        state.intakeSelectedAreas.push(area);
                    }
                } else {
                    state.intakeSelectedAreas = state.intakeSelectedAreas.filter((a) => a !== area);
                }
                runReadinessCheck();
            });
        });
        const addSelect = body.querySelector('#preset-area-add-select');
        if (addSelect) {
            addSelect.addEventListener('change', () => {
                const a = addSelect.value;
                if (a && !state.intakeSelectedAreas.includes(a)) {
                    state.intakeSelectedAreas.push(a);
                    renderPresetCard();
                    runReadinessCheck();
                }
            });
        }

        // Summary
        const summary = (state.intakeSession && state.intakeSession.intake_result && state.intakeSession.intake_result.summary)
            || state.intakeSession && state.intakeSession.intake_result && state.intakeSession.intake_result.summary;
        const s = (state.intakeSession && state.intakeSession.intake_result && state.intakeSession.intake_result.summary) || '';
        elements.presetCardSummary.textContent = s
            ? `Zusammenfassung: ${s}`
            : '';

        runReadinessCheck();
    }

    async function loadAvailableSources() {
        try {
            const resp = await fetch(API_BASE + '/corpus/available-sources', {
                headers: buildHeaders({}),
            });
            if (resp.ok) {
                state.intakeAvailableSources = await resp.json();
            }
        } catch (err) {
            console.warn('available-sources load failed', err);
        }
    }

    async function runReadinessCheck() {
        if (!state.intakeSelectedAreas.length) {
            elements.presetCardMissing.classList.add('hidden');
            return;
        }
        // Client-side heuristic: an area is "ready" if at least one of its
        // mapped sources has a scraper (has_scraper). The full per-area
        // status is determined server-side at pipeline run time.
        const areaToSources = {
            sozialrecht: ['sgb2', 'sgbx', 'sgb1', 'weisung'],
            erbrecht: ['bgb', 'erbstg', 'hoefev'],
            schenkungsrecht: ['bgb', 'erbstg'],
            familienrecht: ['bgb'],
            mietrecht: ['bgb'],
            arbeitsrecht: ['bgb'],
            vertragsrecht: ['bgb'],
            verwaltungsrecht: ['vwvfg'],
            strafrecht: [],
            andere: [],
        };
        const available = new Set(
            (state.intakeAvailableSources || [])
                .filter((s) => s.has_scraper)
                .map((s) => s.key)
        );
        const missing = [];
        for (const area of state.intakeSelectedAreas) {
            const sources = areaToSources[area] || [];
            const has = sources.some((s) => available.has(s));
            if (!has && sources.length > 0) {
                missing.push(`${LEGAL_AREA_LABELS[area] || area} (${sources.filter((s) => !available.has(s)).join(', ')})`);
            }
        }
        state.intakeMissingSources = missing;
        if (missing.length) {
            elements.presetCardMissing.classList.remove('hidden');
            elements.presetCardMissingText.textContent =
                `Citizen kann die Analyse erst starten, wenn diese Quellen geladen sind: ${missing.join('; ')}.`;
        } else {
            elements.presetCardMissing.classList.add('hidden');
        }
    }

    async function loadMissingSources() {
        const sources = ['sgb2', 'sgbx', 'sgb1', 'weisung', 'bgb', 'erbstg', 'hoefev'];
        elements.presetLoadMissingBtn.disabled = true;
        elements.presetLoadMissingBtn.textContent = 'Quellen werden geladen …';
        try {
            const resp = await fetch(API_BASE + '/corpus/update', {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ sources }),
            });
            if (!resp.ok) {
                await handleApiError(resp);
                return;
            }
            const data = await resp.json();
            state.corpusJobId = data.job_id;
            // Show the corpus section progress UI (reuse existing handler)
            if (typeof pollCorpusStatus === 'function') {
                pollCorpusStatus();
            }
            await runReadinessCheck();
            await loadAvailableSources();
            await runReadinessCheck();
        } catch (err) {
            showError('Quellen-Update fehlgeschlagen: ' + err.message);
        } finally {
            elements.presetLoadMissingBtn.disabled = false;
            elements.presetLoadMissingBtn.textContent = 'Fehlende Quellen jetzt laden';
        }
    }

    function showMissingSourcesModal(detail) {
        elements.missingSourcesMessage.textContent = detail.message || 'Quellen fehlen.';
        const list = elements.missingSourcesList;
        list.innerHTML = '';
        const areas = detail.areas || {};
        Object.keys(areas).forEach((area) => {
            const info = areas[area];
            const li = document.createElement('li');
            const missing = (info.missing_source_types || []).join(', ') || '(keine)';
            li.innerHTML = `<strong>${escapeHtml(LEGAL_AREA_LABELS[area] || area)}:</strong> fehlen ${escapeHtml(missing)}`;
            list.appendChild(li);
        });
        if (!list.innerHTML) {
            (detail.missing_source_types || []).forEach((s) => {
                const li = document.createElement('li');
                li.textContent = s;
                list.appendChild(li);
            });
        }
        elements.missingSourcesModal.classList.remove('hidden');
    }

    function hideMissingSourcesModal() {
        elements.missingSourcesModal.classList.add('hidden');
    }

    // =========================================================================
    // Original analyze handler — now uses intake state
    // =========================================================================


        elements.fileInput.addEventListener('change', handleFileSelect);
        elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
        elements.uploadArea.addEventListener('drop', handleFileDrop);
        elements.uploadArea.addEventListener('dragover', handleDragOver);
        elements.removeFile.addEventListener('click', handleRemoveFile);
        elements.uploadBtn.addEventListener('click', handleUpload);
        elements.analyzeBtn.addEventListener('click', handleAnalyze);
        elements.corpusUpdateBtn.addEventListener('click', handleCorpusUpdate);
        elements.textEditor.addEventListener('input', handleTextEditorInput);
        elements.useTextBtn.addEventListener('click', startIntakeFlow);

        // 3-step intake wiring
        if (elements.intakeSendBtn) {
            elements.intakeSendBtn.addEventListener('click', sendIntakeMessage);
        }
        if (elements.intakeInput) {
            elements.intakeInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendIntakeMessage();
                }
            });
        }
        if (elements.intakeConfirmBtn) {
            elements.intakeConfirmBtn.addEventListener('click', confirmIntake);
        }
        if (elements.intakeBackBtn) {
            elements.intakeBackBtn.addEventListener('click', () => gotoStep(1));
        }
        if (elements.confirmationBackBtn) {
            elements.confirmationBackBtn.addEventListener('click', () => gotoStep(2));
        }
        if (elements.presetLoadMissingBtn) {
            elements.presetLoadMissingBtn.addEventListener('click', loadMissingSources);
        }
        if (elements.missingSourcesCancelBtn) {
            elements.missingSourcesCancelBtn.addEventListener('click', hideMissingSourcesModal);
        }
        if (elements.missingSourcesLoadBtn) {
            elements.missingSourcesLoadBtn.addEventListener('click', () => {
                hideMissingSourcesModal();
                loadMissingSources();
            });
        }

        // =========================================================================
        // Mode Toggle
        // =========================================================================

        elements.modeAnalyzeBtn.addEventListener('click', () => switchMode('analyze'));
        elements.modeChatBtn.addEventListener('click', () => switchMode('chat'));
        elements.modeSettingsBtn.addEventListener('click', () => switchMode('settings'));
        if (elements.modePruefstandBtn) {
            elements.modePruefstandBtn.addEventListener('click', () => switchMode('pruefstand'));
        }

        // Also wire up mode buttons within settings-mode and pruefstand-mode headers
        document.querySelectorAll('#settings-mode .mode-btn, #pruefstand-mode .mode-btn').forEach(btn => {
            btn.addEventListener('click', () => switchMode(btn.dataset.mode));
        });

        // =========================================================================
        // Settings Mode Event Listeners
        // =========================================================================

        elements.settingsSelectAll.addEventListener('change', () => {
            const checked = elements.settingsSelectAll.checked;
            state.availableSources.forEach(s => {
                if (s.has_scraper) {
                    if (checked) {
                        if (!state.selectedSources.includes(s.key)) {
                            state.selectedSources.push(s.key);
                        }
                    } else {
                        state.selectedSources = state.selectedSources.filter(k => k !== s.key);
                    }
                }
            });
            state.settingsDirty = true;
            renderSettingsSources();
        });

        elements.settingsSaveBtn.addEventListener('click', handleSettingsSave);
        elements.settingsReloadBtn.addEventListener('click', handleSettingsReload);

        // =========================================================================
        // Prüfstand Mode Event Listeners (WP-14)
        // =========================================================================

        if (elements.pruefstandBackBtn) {
            elements.pruefstandBackBtn.addEventListener('click', () => {
                elements.pruefstandDetailSection.classList.add('hidden');
                elements.pruefstandDemoSection.classList.add('hidden');
                elements.pruefstandGallerySection.classList.remove('hidden');
                state.goldsetCaseDetail = null;
                state.pruefstandDemoResult = null;
            });
        }
        if (elements.pruefstandDemoBackBtn) {
            elements.pruefstandDemoBackBtn.addEventListener('click', () => {
                elements.pruefstandDemoSection.classList.add('hidden');
                elements.pruefstandDetailSection.classList.remove('hidden');
                state.pruefstandDemoResult = null;
            });
        }

        // =========================================================================
        // Case Chat Event Listeners
        // =========================================================================

        elements.caseChatSendBtn.addEventListener('click', handleCaseChatSend);
        elements.caseChatInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleCaseChatSend();
            }
        });
        elements.caseChatInput.addEventListener('input', function() {
            elements.caseChatSendBtn.disabled = !this.value.trim() || state.caseIsStreaming;
        });
        elements.caseDeleteBtn.addEventListener('click', handleCaseDelete);
        elements.caseExportBtn.addEventListener('click', handleCaseExport);
        elements.caseCompareBtn.addEventListener('click', handleCaseCompare);
        elements.caseCompareLoad.addEventListener('click', handleCaseCompareLoad);
        elements.caseCompareClose.addEventListener('click', handleCaseCompareClose);

        // =========================================================================
        // Chat Mode Event Listeners
        // =========================================================================

        // Sidebar
        elements.newConversationBtn.addEventListener('click', handleNewConversation);
        elements.sidebarToggle.addEventListener('click', toggleSidebar);

        // Delete conversation
        elements.chatDeleteBtn.addEventListener('click', handleDeleteConversation);

        // Messages
        elements.chatSendBtn.addEventListener('click', handleChatSend);
        elements.chatAttachBtn.addEventListener('click', handleChatAttach);
        elements.chatFileInput.addEventListener('change', handleChatFileSelect);
        elements.chatInput.addEventListener('keydown', handleChatInputKeydown);
        elements.chatInput.addEventListener('input', autoResizeTextarea);

        // Drag and drop on chat area
        elements.chatMessages.addEventListener('dragover', handleChatDragOver);
        elements.chatMessages.addEventListener('dragleave', handleChatDragLeave);
        elements.chatMessages.addEventListener('drop', handleChatDrop);

        // Close sidebar when pressing Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && state.currentMode === 'chat') {
                closeSidebar();
            }
        });

        // =========================================================================
        // Show app
        // =========================================================================

        if (accepted) {
            elements.disclaimerModal.classList.add('hidden');
            elements.app.classList.remove('hidden');
            // Fetch the Rechtsstand indicator and active profile immediately and on each mode switch
            fetchRechtsstand();
            fetchActiveProfile();
        }

        // Default mode
        switchMode('analyze');
    }

    // Start app when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
