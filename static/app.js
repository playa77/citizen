/**
 * Citizen — Legal Reasoning Engine Frontend
 *
 * Handles:
 * - Disclaimer acceptance modal with localStorage persistence
 * - Document upload and OCR via /api/v1/ingest
 * - SSE streaming analysis via /api/v1/analyze
 * - 6-section output rendering
 */

(function() {
    'use strict';

    // Configuration
    const STORAGE_KEY = 'legal_disclaimer_accepted_v1';
    const STORAGE_VERSION_KEY = 'legal_disclaimer_version_v1';

    // DOM Elements
    const elements = {
        disclaimerModal: document.getElementById('disclaimer-modal'),
        disclaimerText: document.getElementById('disclaimer-text'),
        disclaimerCheckbox: document.getElementById('disclaimer-checkbox'),
        acknowledgeBtn: document.getElementById('acknowledge-btn'),
        app: document.getElementById('app'),
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
    };

    // State
    let state = {
        file: null,
        extractedText: null,
        disclaimerVersion: null,
        sessionId: null,
    };

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

    // =========================================================================
    // Disclaimer Management
    // =========================================================================

    /**
     * Check if disclaimer has been accepted and matches current version
     */
    async function checkDisclaimerStatus() {
        try {
            const response = await fetch('/api/v1/meta/disclaimer/version');
            if (!response.ok) {
                // If the endpoint doesn't exist yet, allow access
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
                // Version mismatch - clear and show modal
                localStorage.removeItem(STORAGE_KEY);
                localStorage.removeItem(STORAGE_VERSION_KEY);
                return false;
            }

            return true;
        } catch (err) {
            console.error('Error checking disclaimer status:', err);
            return false; // Show modal on error
        }
    }

    /**
     * Load and display disclaimer text
     */
    async function loadDisclaimerText() {
        try {
            const response = await fetch('/api/v1/meta/disclaimer/text');
            if (!response.ok) {
                elements.disclaimerText.textContent = 'Fehler beim Laden des Disclaimer-Textes.';
                return;
            }
            const data = await response.text();
            elements.disclaimerText.textContent = data.text || data;
        } catch (err) {
            elements.disclaimerText.textContent = 'Fehler beim Laden des Disclaimer-Textes.';
        }
    }

    /**
     * Show the disclaimer modal
     */
    function showDisclaimerModal() {
        elements.disclaimerModal.classList.remove('hidden');
        elements.app.classList.add('hidden');
        loadDisclaimerText();
    }

    /**
     * Hide the disclaimer modal and show the app
     */
    function hideDisclaimerModal() {
        elements.disclaimerModal.classList.add('hidden');
        elements.app.classList.remove('hidden');

        // Store acceptance in localStorage
        const acceptanceData = {
            version: state.disclaimerVersion,
            timestamp: new Date().toISOString(),
            ip_hash: '', // Will be populated by backend on first API call
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(acceptanceData));
        localStorage.setItem(STORAGE_VERSION_KEY, state.disclaimerVersion);
    }

    /**
     * Handle disclaimer checkbox change
     */
    function handleDisclaimerCheckbox() {
        elements.acknowledgeBtn.disabled = !elements.disclaimerCheckbox.checked;
    }

    /**
     * Handle acknowledge button click
     */
    function handleAcknowledge() {
        if (elements.disclaimerCheckbox.checked) {
            hideDisclaimerModal();
        }
    }

    // =========================================================================
    // API Helpers
    // =========================================================================

    /**
     * Get disclaimer acknowledgment header value
     */
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

    /**
     * Build headers with disclaimer acknowledgment
     */
    function buildHeaders() {
        const headers = {
            'Accept': 'application/json',
        };
        const ack = getDisclaimerAckHeader();
        if (ack) {
            headers['X-Disclaimer-Ack'] = ack;
        }
        return headers;
    }

    /**
     * Handle API error and check for disclaimer requirements
     */
    async function handleApiError(response) {
        if (response.status === 403) {
            const data = await response.json();
            if (data.error === 'disclaimer_required' || data.error === 'disclaimer_version_mismatch') {
                // Need to re-acknowledge
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
    // File Upload
    // =========================================================================

    /**
     * Handle file selection
     */
    function handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        const maxSize = 25 * 1024 * 1024; // 25 MB
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

    /**
     * Handle file drop
     */
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

    /**
     * Handle drag over
     */
    function handleDragOver(event) {
        event.preventDefault();
    }

    /**
     * Handle remove file
     */
    function handleRemoveFile() {
        state.file = null;
        state.extractedText = null;
        elements.fileInput.value = '';
        elements.fileInfo.classList.add('hidden');
        elements.uploadBtn.disabled = true;
        elements.analysisSection.classList.add('hidden');
        elements.resultsSection.classList.add('hidden');
    }

    /**
     * Handle upload button click
     */
    async function handleUpload() {
        if (!state.file) return;

        showError(null);
        elements.uploadBtn.disabled = true;
        elements.uploadBtn.textContent = 'Wird extrahiert...';

        try {
            const formData = new FormData();
            formData.append('file', state.file);

            const response = await fetch('/api/v1/ingest', {
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

            // Show analysis section
            elements.textPreview.textContent = truncateText(state.extractedText, 500);
            elements.analysisSection.classList.remove('hidden');
            elements.resultsSection.classList.add('hidden');
        } catch (err) {
            showError(err.message);
        } finally {
            elements.uploadBtn.disabled = false;
            elements.uploadBtn.textContent = 'Text extrahieren';
        }
    }

    // =========================================================================
    // Analysis
    // =========================================================================

    /**
     * Handle analyze button click
     */
    async function handleAnalyze() {
        if (!state.extractedText) return;

        showError(null);
        elements.analysisSection.classList.add('hidden');
        elements.progressSection.classList.add('hidden');
        elements.resultsSection.classList.add('hidden');
        elements.errorDisplay.classList.add('hidden');

        // Reset stages
        document.querySelectorAll('.stage').forEach(stage => {
            stage.classList.remove('complete', 'active');
            stage.querySelector('.stage-icon').textContent = '○';
        });

        elements.progressBar.style.width = '0%';
        elements.progressSection.classList.remove('hidden');

        try {
            const response = await fetch('/api/v1/analyze', {
                method: 'POST',
                headers: {
                    ...buildHeaders(),
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
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

    /**
     * Process SSE stream from analyze endpoint
     */
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

    /**
     * Handle single SSE event
     */
    function handleSSEEvent(event) {
        // Check for error events
        if (event.error) {
            showError(event.detail || 'Analyse fehlgeschlagen');
            return;
        }

        // Update progress bar
        if (event.stage) {
            updateStage(event.stage, event.status, event.payload);
        }

        // Check for final output
        if (event.final_output) {
            renderResults(event.final_output);
        }
    }

    /**
     * Update stage display
     */
    function updateStage(stageName, status, payload) {
        const stage = document.querySelector(`.stage[data-stage="${stageName}"]`);
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

        // Update progress bar
        const stages = Object.keys(stageNames);
        const currentIndex = stages.indexOf(stageName);
        const progress = ((currentIndex + 1) / stages.length) * 100;
        elements.progressBar.style.width = `${progress}%`;
    }

    /**
     * Render the 6-section output
     */
    function renderResults(output) {
        const sections = [
            { key: 'sachverhalt', label: 'Sachverhalt' },
            { key: 'rechtliche_wuerdigung', label: 'Rechtliche Würdigung' },
            { key: 'ergebnis', label: 'Ergebnis' },
            { key: 'handlungsempfehlung', label: 'Handlungsempfehlung' },
            { key: 'entwurf', label: 'Entwurf' },
            { key: 'unsicherheiten', label: 'Unsicherheiten' },
        ];

        elements.resultsContainer.innerHTML = '';

        sections.forEach(section => {
            const content = output[section.key] || '—';
            const sectionEl = document.createElement('div');
            sectionEl.className = 'result-section';
            sectionEl.innerHTML = `
                <h3>${section.label}</h3>
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

    /**
     * Truncate text with ellipsis
     */
    function truncateText(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.slice(0, maxLength) + '...';
    }

    /**
     * Format content for display (preserve line breaks)
     */
    function formatContent(content) {
        if (!content) return '—';
        return content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
    }

    /**
     * Show error message
     */
    function showError(message) {
        if (!message) {
            elements.errorDisplay.classList.add('hidden');
            return;
        }
        elements.errorDisplay.textContent = message;
        elements.errorDisplay.classList.remove('hidden');
    }

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * Initialize the application
     */
    async function init() {
        // Check disclaimer status
        const accepted = await checkDisclaimerStatus();
        if (!accepted) {
            showDisclaimerModal();
            return;
        }

        // Setup event listeners
        elements.disclaimerCheckbox.addEventListener('change', handleDisclaimerCheckbox);
        elements.acknowledgeBtn.addEventListener('click', handleAcknowledge);

        elements.fileInput.addEventListener('change', handleFileSelect);
        elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
        elements.uploadArea.addEventListener('drop', handleFileDrop);
        elements.uploadArea.addEventListener('dragover', handleDragOver);
        elements.removeFile.addEventListener('click', handleRemoveFile);
        elements.uploadBtn.addEventListener('click', handleUpload);
        elements.analyzeBtn.addEventListener('click', handleAnalyze);

        // Show app (disclaimer already accepted)
        elements.app.classList.remove('hidden');
    }

    // Start app when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();