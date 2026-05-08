/**
 * Citizen — Legal Reasoning Engine Frontend
 * @version 0.2.0
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
 * - Mode toggle between Analyze and Chat views
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
        claims: 'Anspruchsaufbau',
        verification: 'Verifikation',
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
        analysisSection: document.getElementById('analysis-section'),
        textPreview: document.getElementById('text-preview'),
        analyzeBtn: document.getElementById('analyze-btn'),
        progressSection: document.getElementById('progress-section'),
        progressBar: document.getElementById('progress-bar'),
        stageList: document.getElementById('stage-list'),
        resultsSection: document.getElementById('results-section'),
        resultsContainer: document.getElementById('results-container'),
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
        // Chat mode state
        currentMode: 'analyze',
        conversations: [],
        activeConversationId: null,
        conversationDocuments: [],
        isStreaming: false,
        streamingAbortController: null,
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

        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
        if (!allowedTypes.includes(file.type)) {
            showError('Ungültiger Dateityp. Erlaubt: PDF, JPG, PNG.');
            return;
        }

        state.file = file;
        elements.filename.textContent = file.name;
        elements.fileInfo.classList.remove('hidden');
        elements.uploadBtn.disabled = false;
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

        try {
            const response = await fetch(API_BASE + '/analyze', {
                method: 'POST',
                headers: buildHeaders({
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                }),
                body: JSON.stringify({ text: state.extractedText }),
            });

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

        if (event.stage) {
            updateStage(event.stage, event.status, event.payload);
        }

        if (event.final_output) {
            renderResults(event.final_output);
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
        elements.resultsContainer.innerHTML = '';

        Object.entries(pipelineSectionLabels).forEach(([key, label]) => {
            const content = output[key] || '—';
            const sectionEl = document.createElement('div');
            sectionEl.className = 'result-section';
            sectionEl.innerHTML = `
                <h3>${escapeHtml(label)}</h3>
                <div class="result-content">${formatContent(content)}</div>
            `;
            elements.resultsContainer.appendChild(sectionEl);
        });

        elements.progressSection.classList.add('hidden');
        elements.resultsSection.classList.remove('hidden');
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
        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
        if (file.size > maxSize) {
            return `Datei "${file.name}" zu groß (max. 25 MB).`;
        }
        if (!allowedTypes.includes(file.type)) {
            return `Datei "${file.name}" hat ungültigen Typ. Erlaubt: PDF, JPG, PNG.`;
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
            elements.corpusSubstage.textContent = substageLabels[job.substage];
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

        if (mode === 'analyze') {
            elements.analyzeMode.classList.remove('hidden');
            elements.chatMode.classList.add('hidden');
            elements.modeAnalyzeBtn.classList.add('active');
            elements.modeChatBtn.classList.remove('active');
        } else {
            elements.analyzeMode.classList.add('hidden');
            elements.chatMode.classList.remove('hidden');
            elements.modeAnalyzeBtn.classList.remove('active');
            elements.modeChatBtn.classList.add('active');

            // Load conversations when switching to chat mode
            if (state.conversations.length === 0) {
                loadConversations();
            }
        }
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
        // Analyze Mode Event Listeners
        // =========================================================================

        elements.fileInput.addEventListener('change', handleFileSelect);
        elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
        elements.uploadArea.addEventListener('drop', handleFileDrop);
        elements.uploadArea.addEventListener('dragover', handleDragOver);
        elements.removeFile.addEventListener('click', handleRemoveFile);
        elements.uploadBtn.addEventListener('click', handleUpload);
        elements.analyzeBtn.addEventListener('click', handleAnalyze);
        elements.corpusUpdateBtn.addEventListener('click', handleCorpusUpdate);

        // =========================================================================
        // Mode Toggle
        // =========================================================================

        elements.modeAnalyzeBtn.addEventListener('click', () => switchMode('analyze'));
        elements.modeChatBtn.addEventListener('click', () => switchMode('chat'));

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
