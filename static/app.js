/**
 * Citizen — Legal Reasoning Engine Frontend
 * @version 0.1.0
 *
 * Handles:
 * - Disclaimer acceptance modal with localStorage persistence
 * - Document upload and OCR via /api/v1/ingest
 * - Corpus update via /api/v1/corpus/update with status polling
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
        // Corpus management
        corpusUpdateBtn: document.getElementById('corpus-update-btn'),
        corpusProgress: document.getElementById('corpus-progress'),
        corpusProgressFill: document.getElementById('corpus-progress-fill'),
        corpusSubstage: document.getElementById('corpus-substage'),
        corpusChunksCount: document.getElementById('corpus-chunks-count'),
        corpusResult: document.getElementById('corpus-result'),
    };

    // State
    let state = {
        file: null,
        extractedText: null,
        disclaimerVersion: null,
        sessionId: null,
        hasExtracted: false,
        // Corpus update tracking
        corpusJobId: null,
        corpusPollingTimer: null,
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
            const data = await response.json();
            elements.disclaimerText.innerHTML = data.text;
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
        state.hasExtracted = false;
        elements.fileInput.value = '';
        elements.fileInfo.classList.add('hidden');
        elements.uploadBtn.disabled = true;
        elements.uploadBtn.textContent = 'Text extrahieren';
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
        elements.uploadBtn.textContent = state.hasExtracted ? 'Wird erneut extrahiert...' : 'Wird extrahiert...';

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
            state.hasExtracted = true;

            // Show analysis section with character count
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
    // Corpus Management
    // =========================================================================

    /**
     * Mapping of substage values to user-visible German labels
     */
    const substageLabels = {
        scraping: 'Rechtsquellen werden abgerufen und aufbereitet …',
        embedding: 'Vektordarstellungen (Embeddings) werden generiert …',
        upserting: 'Einträge werden in der Datenbank gespeichert …',
    };

    /**
     * Handle corpus update button click
     */
    async function handleCorpusUpdate() {
        // Prevent double-trigger
        if (state.corpusJobId) return;

        // Clear any previous result
        elements.corpusResult.classList.add('hidden');
        elements.corpusResult.textContent = '';
        elements.corpusResult.className = 'corpus-result hidden';

        // Show progress area
        elements.corpusProgress.classList.remove('hidden');
        elements.corpusSubstage.textContent = 'Auftrag wird eingereiht …';
        elements.corpusChunksCount.textContent = '';
        elements.corpusProgressFill.classList.remove('indeterminate');
        elements.corpusProgressFill.style.width = '0%';

        // Disable button
        elements.corpusUpdateBtn.disabled = true;
        elements.corpusUpdateBtn.textContent = 'Corpus-Aktualisierung läuft …';

        try {
            const response = await fetch('/api/v1/corpus/update', {
                method: 'POST',
                headers: buildHeaders(),
            });

            if (!response.ok) {
                await handleApiError(response);
                return;
            }

            const data = await response.json();
            state.corpusJobId = data.job_id;

            // Start polling
            elements.corpusSubstage.textContent = 'Auftrag gestartet — warte auf erste Rückmeldung …';
            pollCorpusStatus(data.job_id);
        } catch (err) {
            showCorpusError(err.message);
        }
    }

    /**
     * Poll GET /api/v1/corpus/status/{job_id} until the job completes or fails
     */
    function pollCorpusStatus(jobId) {
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
        }

        state.corpusPollingTimer = setTimeout(async () => {
            try {
                const response = await fetch(`/api/v1/corpus/status/${jobId}`, {
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
                    // Continue polling
                    pollCorpusStatus(jobId);
                }
            } catch (err) {
                showCorpusError(err.message);
            }
        }, 2000);
    }

    /**
     * Update the UI based on current job status
     */
    function updateCorpusProgress(job) {
        // Update substage label
        if (job.substage && substageLabels[job.substage]) {
            elements.corpusSubstage.textContent = substageLabels[job.substage];
        }

        // Build chunks status line
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

        // Update progress bar style
        if (job.status === 'running') {
            // Indeterminate shimmer — we don't know exact progress within the 3 stages
            elements.corpusProgressFill.classList.add('indeterminate');
        }
    }

    /**
     * Handle job completion or failure
     */
    function finishCorpusUpdate(job) {
        // Stop polling
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
            state.corpusPollingTimer = null;
        }
        state.corpusJobId = null;

        // Hide progress
        elements.corpusProgress.classList.add('hidden');

        // Re-enable button
        elements.corpusUpdateBtn.disabled = false;
        elements.corpusUpdateBtn.textContent = 'Corpus aktualisieren';

        // Show result
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

    /**
     * Show a corpus update error and reset UI
     */
    function showCorpusError(message) {
        // Stop polling
        if (state.corpusPollingTimer) {
            clearTimeout(state.corpusPollingTimer);
            state.corpusPollingTimer = null;
        }
        state.corpusJobId = null;

        // Hide progress
        elements.corpusProgress.classList.add('hidden');

        // Re-enable button
        elements.corpusUpdateBtn.disabled = false;
        elements.corpusUpdateBtn.textContent = 'Corpus aktualisieren';

        // Show error
        elements.corpusResult.classList.remove('hidden');
        elements.corpusResult.className = 'corpus-result error';
        elements.corpusResult.textContent = `Fehler: ${message}`;
    }

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * Initialize the application
     */
    async function init() {
        // Always register disclaimer event listeners — needed even on first visit
        elements.disclaimerCheckbox.addEventListener('change', handleDisclaimerCheckbox);
        elements.acknowledgeBtn.addEventListener('click', handleAcknowledge);

        // Check disclaimer status
        const accepted = await checkDisclaimerStatus();
        if (!accepted) {
            showDisclaimerModal();
            // Fall through — register remaining listeners even when modal is shown,
            // so they're ready once the user accepts and the app becomes visible.
        }

        // Setup all other event listeners (always registered, UI stays hidden until accepted)
        elements.fileInput.addEventListener('change', handleFileSelect);
        elements.uploadArea.addEventListener('click', () => elements.fileInput.click());
        elements.uploadArea.addEventListener('drop', handleFileDrop);
        elements.uploadArea.addEventListener('dragover', handleDragOver);
        elements.removeFile.addEventListener('click', handleRemoveFile);
        elements.uploadBtn.addEventListener('click', handleUpload);
        elements.analyzeBtn.addEventListener('click', handleAnalyze);
        elements.corpusUpdateBtn.addEventListener('click', handleCorpusUpdate);

        // Show app if disclaimer was already accepted
        if (accepted) {
            elements.disclaimerModal.classList.add('hidden');
            elements.app.classList.remove('hidden');
        }
    }

    // Start app when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();