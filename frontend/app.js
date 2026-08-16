// ── SUSHRUTA AI CLINICAL PORTAL APPLICATION LOGIC ──

// Backend URL configuration - automatically resolves to the host address
const API_BASE = `${window.location.origin}/api/v1`;

// Application State Store
const state = {
    token: localStorage.getItem('token') || null,
    doctor: JSON.parse(localStorage.getItem('doctor')) || null,
    patients: [],
    selectedPatient: null,
    activeTab: 'summary',
    patientPage: 1,
    patientLimit: 12,
    patientTotal: 0,
    patientSearch: '',
    activeDrugList: [],
    activeNotes: [],
    activeDocuments: [],
    activeEncounters: [],
    statusPollingIntervals: {},
    recognitionInstance: null,
    isListening: false,
    micPreExistingText: ""
};

// ── UTILITY: HEADERS & AUTH ──
function getHeaders(isMultipart = false) {
    const headers = {};
    if (!isMultipart) {
        headers['Content-Type'] = 'application/json';
    }
    if (state.token) {
        headers['Authorization'] = `Bearer ${state.token}`;
    }
    return headers;
}

// Global API Fetch wrapper with auto-logout on 401 Unauthorized
async function apiRequest(endpoint, options = {}) {
    options.headers = { ...options.headers, ...getHeaders(options.body instanceof FormData) };
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        
        if (response.status === 401) {
            handleLogout();
            throw new Error("Session expired. Please log in again.");
        }
        
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || `Request failed with status ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error(`API Error on ${endpoint}:`, error);
        throw error;
    }
}

// Custom Markdown renderer for rendering AI summaries and notes without dependencies
function renderMarkdown(md) {
    if (!md) return '';
    let html = md;
    
    // Replace markdown rules with HTML elements
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    html = html.replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*)\*/gim, '<em>$1</em>');
    html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
    
    // Group adjacent lists
    html = html.replace(/(<li>.*<\/li>)/sim, '<ul>$1</ul>');
    // Line breaks
    html = html.replace(/\n/gim, '<br>');
    
    return html;
}

// Format ISO date strings to human-readable strings
function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Debounce timer for live search
let searchDebounceTimer;

// ── CORE APP FLOW & PAGES ──
document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setupDragAndDrop();
});

async function initApp() {
    if (state.token) {
        try {
            // Validate session token with server
            const profile = await apiRequest('/auth/me');
            state.doctor = profile;
            localStorage.setItem('doctor', JSON.stringify(profile));
            showAppView();
        } catch (error) {
            console.error("Token verification failed, clearing session.");
            handleLogout();
        }
    } else {
        showAuthView();
    }
}

function showAuthView() {
    document.getElementById('auth-overlay').classList.remove('hidden');
    document.getElementById('app-container').classList.add('hidden');
}

function showAppView() {
    document.getElementById('auth-overlay').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');
    
    // Update Doctor details widget
    document.getElementById('doc-name').textContent = state.doctor.name;
    document.getElementById('doc-spec').textContent = state.doctor.specialisation || 'General Medicine';
    document.getElementById('doc-license').textContent = `Lic: ${state.doctor.license_number}`;
    
    // Pull patient list
    fetchPatients(1);
}

// ── AUTH HANDLERS ──
function toggleAuthTab(tab) {
    const loginBtn = document.getElementById('tab-login-btn');
    const registerBtn = document.getElementById('tab-register-btn');
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    
    if (tab === 'login') {
        loginBtn.classList.add('active');
        registerBtn.classList.remove('active');
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
    } else {
        loginBtn.classList.remove('active');
        registerBtn.classList.add('active');
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
    }
}

async function handleLogin(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const errorDiv = document.getElementById('login-error');
    
    errorDiv.classList.add('hidden');
    
    try {
        const data = await apiRequest('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
        
        state.token = data.access_token;
        state.doctor = data.doctor;
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('doctor', JSON.stringify(data.doctor));
        
        showAppView();
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const name = document.getElementById('reg-name').value;
    const email = document.getElementById('reg-email').value;
    const license_number = document.getElementById('reg-license').value;
    const specialisation = document.getElementById('reg-specialisation').value;
    const password = document.getElementById('reg-password').value;
    
    const errorDiv = document.getElementById('register-error');
    const successDiv = document.getElementById('register-success');
    
    errorDiv.classList.add('hidden');
    successDiv.classList.add('hidden');
    
    if (password.length < 8) {
        errorDiv.textContent = "Password must be at least 8 characters long.";
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        await apiRequest('/auth/register', {
            method: 'POST',
            body: JSON.stringify({
                name,
                email,
                password,
                license_number,
                specialisation: specialisation || null
            })
        });
        
        successDiv.classList.remove('hidden');
        document.getElementById('register-form').reset();
        
        setTimeout(() => {
            toggleAuthTab('login');
        }, 1500);
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    }
}

function handleLogout() {
    state.token = null;
    state.doctor = null;
    state.selectedPatient = null;
    localStorage.removeItem('token');
    localStorage.removeItem('doctor');
    
    if (state.recognitionInstance && state.isListening) {
        state.recognitionInstance.stop();
    }
    
    // Clear status intervals
    Object.values(state.statusPollingIntervals).forEach(clearInterval);
    state.statusPollingIntervals = {};
    
    showAuthView();
}

// ── PATIENT CRUD OPERATORS ──
async function fetchPatients(page = 1) {
    state.patientPage = page;
    const searchParam = state.patientSearch ? `&search=${encodeURIComponent(state.patientSearch)}` : '';
    
    try {
        const data = await apiRequest(`/patients?page=${page}&limit=${state.patientLimit}${searchParam}`);
        state.patients = data.patients;
        state.patientTotal = data.total;
        
        renderPatientsList();
        updatePaginationUI();
    } catch (error) {
        console.error("Failed to load patients list", error);
    }
}

function renderPatientsList() {
    const container = document.getElementById('patient-list');
    document.getElementById('patient-count').textContent = `(${state.patientTotal})`;
    
    if (state.patients.length === 0) {
        container.innerHTML = `<div class="list-empty">No patients found.</div>`;
        return;
    }
    
    container.innerHTML = state.patients.map(p => `
        <div class="patient-item ${state.selectedPatient && state.selectedPatient.id === p.id ? 'active' : ''}" onclick="selectPatient(${p.id})">
            <h4>${p.name}</h4>
            <div class="patient-meta">
                <span>Age: ${p.age} | ${p.gender}</span>
                <span>${p.blood_group || 'Unknown'}</span>
            </div>
        </div>
    `).join('');
}

function updatePaginationUI() {
    const totalPages = Math.ceil(state.patientTotal / state.patientLimit);
    document.getElementById('page-indicator').textContent = `Page ${state.patientPage} of ${totalPages || 1}`;
    document.getElementById('prev-page-btn').disabled = state.patientPage <= 1;
    document.getElementById('next-page-btn').disabled = state.patientPage >= totalPages;
}

function changePatientPage(direction) {
    const nextPage = state.patientPage + direction;
    fetchPatients(nextPage);
}

function handlePatientSearch() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        state.patientSearch = document.getElementById('patient-search-input').value.trim();
        fetchPatients(1);
    }, 400000 / 1000); // 400ms debounce
}

async function selectPatient(patientId) {
    try {
        const patient = await apiRequest(`/patients/${patientId}`);
        state.selectedPatient = patient;
        
        // Render selected class on active list
        renderPatientsList();
        
        // Populate patient banner
        document.getElementById('banner-patient-name').textContent = patient.name;
        document.getElementById('banner-patient-age').textContent = `Age: ${patient.age}`;
        document.getElementById('banner-patient-gender').textContent = patient.gender.replace(/_/g, ' ');
        document.getElementById('banner-patient-blood').textContent = patient.blood_group || 'Blood Type: Unknown';
        
        const allergiesText = document.getElementById('banner-patient-allergies');
        if (patient.allergies) {
            allergiesText.textContent = patient.allergies;
            allergiesText.classList.add('allergies-text');
        } else {
            allergiesText.textContent = 'None';
            allergiesText.classList.remove('allergies-text');
        }
        
        document.getElementById('banner-patient-history').textContent = patient.medical_history || 'No history recorded.';
        
        // Hide empty view, show workspace
        document.getElementById('empty-state').classList.add('hidden');
        document.getElementById('active-workspace').classList.remove('hidden');
        
        // Load data for active tab
        switchTab(state.activeTab);
    } catch (error) {
        alert("Failed to load patient: " + error.message);
    }
}

// ── PATIENT FORMS & MODALS ──
function openAddPatientModal() {
    document.getElementById('patient-modal-title').textContent = "Add New Patient";
    document.getElementById('patient-form-id').value = "";
    document.getElementById('patient-form').reset();
    document.getElementById('patient-form-error').classList.add('hidden');
    document.getElementById('add-patient-modal').classList.remove('hidden');
}

function openEditPatientModal() {
    if (!state.selectedPatient) return;
    const p = state.selectedPatient;
    
    document.getElementById('patient-modal-title').textContent = "Edit Patient Details";
    document.getElementById('patient-form-id').value = p.id;
    document.getElementById('patient-name').value = p.name;
    document.getElementById('patient-age').value = p.age;
    document.getElementById('patient-gender').value = p.gender;
    document.getElementById('patient-blood').value = p.blood_group || "";
    document.getElementById('patient-allergies').value = p.allergies || "";
    document.getElementById('patient-history').value = p.medical_history || "";
    
    document.getElementById('patient-form-error').classList.add('hidden');
    document.getElementById('add-patient-modal').classList.remove('hidden');
}

function closeAddPatientModal() {
    document.getElementById('add-patient-modal').classList.add('hidden');
}

async function handlePatientFormSubmit(event) {
    event.preventDefault();
    const id = document.getElementById('patient-form-id').value;
    const name = document.getElementById('patient-name').value.trim();
    const age = parseInt(document.getElementById('patient-age').value);
    const gender = document.getElementById('patient-gender').value;
    const blood_group = document.getElementById('patient-blood').value || null;
    const allergies = document.getElementById('patient-allergies').value.trim() || null;
    const medical_history = document.getElementById('patient-history').value.trim() || null;
    
    const errorDiv = document.getElementById('patient-form-error');
    errorDiv.classList.add('hidden');
    
    const payload = { name, age, gender, blood_group, allergies, medical_history };
    
    try {
        if (id) {
            // Update
            const updated = await apiRequest(`/patients/${id}`, {
                method: 'PATCH',
                body: JSON.stringify(payload)
            });
            state.selectedPatient = updated;
            selectPatient(updated.id); // Reload banner
        } else {
            // Create
            const created = await apiRequest('/patients', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            selectPatient(created.id);
        }
        
        closeAddPatientModal();
        fetchPatients(state.patientPage); // Refresh sidebar
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    }
}

async function confirmDeletePatient() {
    if (!state.selectedPatient) return;
    const check = confirm(`Are you sure you want to deactivate patient "${state.selectedPatient.name}"? All records will be hidden but kept for compliance.`);
    if (check) {
        try {
            await apiRequest(`/patients/${state.selectedPatient.id}`, { method: 'DELETE' });
            state.selectedPatient = null;
            document.getElementById('active-workspace').classList.add('hidden');
            document.getElementById('empty-state').classList.remove('hidden');
            fetchPatients(1);
        } catch (error) {
            alert(error.message);
        }
    }
}

// ── TAB ROUTER ──
function switchTab(tabName) {
    if (state.recognitionInstance && state.isListening) {
        state.recognitionInstance.stop();
    }
    
    state.activeTab = tabName;
    
    // Update navigation buttons styling
    const tabs = ['summary', 'scribe', 'documents', 'interactions'];
    tabs.forEach(t => {
        const el = document.getElementById(`tab-${t}`);
        if (t === tabName) el.classList.add('active');
        else el.classList.remove('active');
        
        const panel = document.getElementById(`panel-${t}`);
        if (t === tabName) panel.classList.add('active');
        else panel.classList.remove('active');
    });
    
    // Clear dynamic loaders/results from past patients
    if (tabName === 'summary') {
        renderPatientSummary();
    } else if (tabName === 'scribe') {
        loadSOAPNotes();
    } else if (tabName === 'documents') {
        loadDocuments();
    } else if (tabName === 'interactions') {
        loadInteractionsTab();
    }
}

// ── TAB 1: SUMMARY & REFERRAL LOGIC ──
async function generatePatientSummary(force = false) {
    if (!state.selectedPatient) return;
    
    const loader = document.getElementById('summary-loader');
    const content = document.getElementById('summary-content');
    const empty = document.getElementById('summary-empty');
    
    loader.classList.remove('hidden');
    content.classList.add('hidden');
    empty.classList.add('hidden');
    
    try {
        const data = await apiRequest(`/patients/${state.selectedPatient.id}/summary`);
        content.innerHTML = renderMarkdown(data.summary);
        
        loader.classList.add('hidden');
        content.classList.remove('hidden');
    } catch (error) {
        loader.classList.add('hidden');
        empty.innerHTML = `<p class="text-error">Failed to generate summary: ${error.message}</p>`;
        empty.classList.remove('hidden');
    }
}

function renderPatientSummary() {
    // Standard initialization: Clear summaries from previous patient selections
    document.getElementById('summary-content').innerHTML = '';
    document.getElementById('summary-empty').classList.remove('hidden');
    document.getElementById('referral-letter-result').classList.add('hidden');
    document.getElementById('referral-form').reset();
    
    // Auto trigger generation
    generatePatientSummary(false);
}

async function handleGenerateReferral(event) {
    event.preventDefault();
    if (!state.selectedPatient) return;
    
    const specialist = document.getElementById('referral-specialist').value;
    const reason = document.getElementById('referral-reason').value;
    const loader = document.getElementById('referral-loader');
    const resultBox = document.getElementById('referral-letter-result');
    const bodyBox = document.getElementById('referral-letter-body');
    
    loader.classList.remove('hidden');
    resultBox.classList.add('hidden');
    
    try {
        const data = await apiRequest(`/patients/${state.selectedPatient.id}/referral`, {
            method: 'POST',
            body: JSON.stringify({
                target_specialist: specialist,
                referral_reason: reason
            })
        });
        
        bodyBox.textContent = data.letter_text;
        loader.classList.add('hidden');
        resultBox.classList.remove('hidden');
    } catch (error) {
        loader.classList.add('hidden');
        alert("Failed to draft referral letter: " + error.message);
    }
}

function copyReferralLetter() {
    const text = document.getElementById('referral-letter-body').textContent;
    navigator.clipboard.writeText(text)
        .then(() => alert("Referral letter copied to clipboard!"))
        .catch(err => console.error("Could not copy letter", err));
}

// ── TAB 2: SOAP NOTES SCRIBE LOGIC ──
async function loadSOAPNotes() {
    if (!state.selectedPatient) return;
    
    const container = document.getElementById('recorded-notes-list');
    container.innerHTML = `<div class="loader-container"><div class="spinner"></div><p>Fetching patient medical notes...</p></div>`;
    
    try {
        const notes = await apiRequest(`/notes/patient/${state.selectedPatient.id}`);
        state.activeNotes = notes;
        
        if (notes.length === 0) {
            container.innerHTML = `<div class="list-empty">No clinical notes recorded yet.</div>`;
            return;
        }
        
        container.innerHTML = notes.map(n => `
            <div class="note-item-card">
                <div class="note-item-header">
                    <span class="note-date"><i class="fa-solid fa-calendar-day"></i> ${formatDate(n.consultation_date)}</span>
                    <span class="status-badge ${n.is_draft ? 'badge-draft' : 'badge-final'}">
                        ${n.is_draft ? 'Draft' : 'Finalized'}
                    </span>
                </div>
                <div class="note-item-preview">${renderMarkdown(n.generated_note)}</div>
                <div class="note-item-actions">
                    <button class="btn btn-sm btn-outline" onclick="editNoteDraft(${n.id})">
                        <i class="fa-solid fa-pen-to-square"></i> Review
                    </button>
                    <button class="btn btn-sm btn-outline btn-danger" onclick="deleteNote(${n.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="list-empty text-error">Failed to fetch notes: ${error.message}</div>`;
    }
}

async function handleGenerateSOAP(event) {
    event.preventDefault();
    if (!state.selectedPatient) return;
    
    const rawInput = document.getElementById('scribe-raw-input').value;
    const loader = document.getElementById('scribe-loader');
    
    loader.classList.remove('hidden');
    
    try {
        const note = await apiRequest('/notes/generate', {
            method: 'POST',
            body: JSON.stringify({
                patient_id: state.selectedPatient.id,
                raw_input: rawInput,
                consultation_date: new Date().toISOString()
            })
        });
        
        document.getElementById('scribe-raw-input').value = "";
        loader.classList.add('hidden');
        
        // Open edit note modal for immediate review
        editNoteDraft(note.id);
        loadSOAPNotes();
    } catch (error) {
        loader.classList.add('hidden');
        alert("Failed to run AI scribe: " + error.message);
    }
}

function editNoteDraft(noteId) {
    const note = state.activeNotes.find(n => n.id === noteId);
    if (!note) return;
    
    document.getElementById('edit-note-id').value = note.id;
    document.getElementById('edit-note-content').value = note.generated_note;
    document.getElementById('edit-note-draft').checked = note.is_draft;
    document.getElementById('note-edit-error').classList.add('hidden');
    document.getElementById('note-edit-modal').classList.remove('hidden');
}

function closeNoteEditModal() {
    document.getElementById('note-edit-modal').classList.add('hidden');
}

async function handleNoteEditSubmit(event) {
    event.preventDefault();
    const id = document.getElementById('edit-note-id').value;
    const content = document.getElementById('edit-note-content').value;
    const isDraft = document.getElementById('edit-note-draft').checked;
    const errorDiv = document.getElementById('note-edit-error');
    
    errorDiv.classList.add('hidden');
    
    try {
        await apiRequest(`/notes/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({
                generated_note: content,
                is_draft: isDraft
            })
        });
        
        closeNoteEditModal();
        loadSOAPNotes();
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    }
}

async function deleteNote(noteId) {
    if (!confirm("Are you sure you want to delete this clinical note? This action is permanent.")) return;
    try {
        await apiRequest(`/notes/${noteId}`, { method: 'DELETE' });
        loadSOAPNotes();
    } catch (error) {
        alert(error.message);
    }
}

// ── TAB 3: DOCUMENT UPLOAD & RAG CHAT LOGIC ──
function setupDragAndDrop() {
    const area = document.getElementById('drag-drop-area');
    const input = document.getElementById('doc-file-input');
    
    area.addEventListener('click', () => input.click());
    
    area.addEventListener('dragover', (e) => {
        e.preventDefault();
        area.classList.add('highlight');
    });
    
    area.addEventListener('dragleave', () => {
        area.classList.remove('highlight');
    });
    
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('highlight');
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            handleFileSelect();
        }
    });
    
    input.addEventListener('change', handleFileSelect);
}

function handleFileSelect() {
    const input = document.getElementById('doc-file-input');
    const info = document.getElementById('file-info');
    const nameSpan = document.getElementById('selected-filename');
    const uploadBtn = document.getElementById('upload-btn');
    const errorDiv = document.getElementById('upload-error');
    
    errorDiv.classList.add('hidden');
    
    if (input.files.length === 0) {
        info.classList.add('hidden');
        uploadBtn.disabled = true;
        return;
    }
    
    const file = input.files[0];
    // Client-side validation: Max 5MB
    if (file.size > 5 * 1024 * 1024) {
        errorDiv.textContent = "File exceeds the 5MB size limit.";
        errorDiv.classList.remove('hidden');
        clearSelectedFile();
        return;
    }
    
    nameSpan.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    info.classList.remove('hidden');
    uploadBtn.disabled = false;
}

function clearSelectedFile() {
    document.getElementById('doc-file-input').value = "";
    document.getElementById('file-info').classList.add('hidden');
    document.getElementById('upload-btn').disabled = true;
}

async function handleDocumentUpload(event) {
    event.preventDefault();
    if (!state.selectedPatient) return;
    
    const fileInput = document.getElementById('doc-file-input');
    if (fileInput.files.length === 0) return;
    
    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('file', file);
    
    const errorDiv = document.getElementById('upload-error');
    const uploadBtn = document.getElementById('upload-btn');
    
    errorDiv.classList.add('hidden');
    uploadBtn.disabled = true;
    
    try {
        const doc = await apiRequest(`/patients/${state.selectedPatient.id}/documents`, {
            method: 'POST',
            body: formData
        });
        
        clearSelectedFile();
        loadDocuments();
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
        uploadBtn.disabled = false;
    }
}

async function loadDocuments() {
    if (!state.selectedPatient) return;
    
    const container = document.getElementById('document-vault-list');
    container.innerHTML = `<div class="loader-container"><div class="spinner"></div><p>Fetching files from patient vault...</p></div>`;
    
    try {
        const data = await apiRequest(`/patients/${state.selectedPatient.id}/documents`);
        state.activeDocuments = data.documents;
        
        if (data.documents.length === 0) {
            container.innerHTML = `<div class="list-empty">No documents uploaded yet.</div>`;
            return;
        }
        
        container.innerHTML = data.documents.map(d => {
            let statusBtnHtml = '';
            if (d.processing_status === 'uploaded') {
                statusBtnHtml = `<button class="btn btn-sm btn-primary" onclick="processDoc(${d.id})"><i class="fa-solid fa-play"></i> Process RAG</button>`;
            } else if (d.processing_status === 'processing') {
                statusBtnHtml = `<span class="status-badge status-processing"><i class="fa-solid fa-spinner fa-spin"></i> Processing</span>`;
                startStatusPolling(d.id); // Poll status dynamically
            } else if (d.processing_status === 'ready') {
                statusBtnHtml = `
                    <span class="status-badge status-ready"><i class="fa-solid fa-check-double"></i> Ready</span>
                    <button class="btn btn-sm btn-outline" onclick="inspectChunks(${d.id})"><i class="fa-solid fa-magnifying-glass"></i> Chunks</button>
                `;
            } else {
                statusBtnHtml = `<span class="status-badge status-failed">Failed</span>`;
            }
            
            return `
                <div class="doc-vault-item">
                    <div class="doc-meta-box">
                        <h5 title="${d.original_filename}"><i class="fa-solid fa-file-pdf text-accent"></i> ${d.original_filename}</h5>
                        <span>Size: ${(d.file_size_bytes / 1024).toFixed(1)} KB | Uploaded: ${formatDate(d.created_at)}</span>
                    </div>
                    <div class="doc-actions-box">
                        ${statusBtnHtml}
                        <button class="btn btn-sm btn-danger" onclick="deleteDocument(${d.id})"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        container.innerHTML = `<div class="list-empty text-error">Failed to load documents: ${error.message}</div>`;
    }
}

async function deleteDocument(docId) {
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
        await apiRequest(`/patients/${state.selectedPatient.id}/documents/${docId}`, { method: 'DELETE' });
        
        // Clear interval if active
        if (state.statusPollingIntervals[docId]) {
            clearInterval(state.statusPollingIntervals[docId]);
            delete state.statusPollingIntervals[docId];
        }
        
        loadDocuments();
    } catch (error) {
        alert(error.message);
    }
}

async function processDoc(docId) {
    try {
        await apiRequest(`/patients/${state.selectedPatient.id}/documents/${docId}/process`, {
            method: 'POST'
        });
        loadDocuments();
    } catch (error) {
        alert("Failed to start processing: " + error.message);
    }
}

function startStatusPolling(docId) {
    if (state.statusPollingIntervals[docId]) return;
    
    state.statusPollingIntervals[docId] = setInterval(async () => {
        if (!state.selectedPatient) {
            clearInterval(state.statusPollingIntervals[docId]);
            delete state.statusPollingIntervals[docId];
            return;
        }
        
        try {
            const statusData = await apiRequest(`/patients/${state.selectedPatient.id}/documents/${docId}/status`);
            if (statusData.processing_status !== 'processing') {
                clearInterval(state.statusPollingIntervals[docId]);
                delete state.statusPollingIntervals[docId];
                loadDocuments();
            }
        } catch (error) {
            clearInterval(state.statusPollingIntervals[docId]);
            delete state.statusPollingIntervals[docId];
        }
    }, 3000); // Poll every 3s
}

async function inspectChunks(docId) {
    if (!state.selectedPatient) return;
    
    const loader = document.getElementById('chunks-loader');
    const list = document.getElementById('chunks-list');
    
    loader.classList.remove('hidden');
    list.classList.add('hidden');
    document.getElementById('chunks-modal').classList.remove('hidden');
    
    try {
        const data = await apiRequest(`/patients/${state.selectedPatient.id}/documents/${docId}/chunks`);
        loader.classList.add('hidden');
        list.classList.remove('hidden');
        
        if (data.chunks.length === 0) {
            list.innerHTML = `<div class="list-empty">No splits found. Check if processing failed.</div>`;
            return;
        }
        
        list.innerHTML = data.chunks.map(c => `
            <div class="chunk-item-card">
                <h6><span>Chunk #${c.chunk_index + 1}</span> <span>Tokens: ${c.token_count}</span></h6>
                <p>${c.chunk_text}</p>
            </div>
        `).join('');
    } catch (error) {
        loader.classList.add('hidden');
        list.innerHTML = `<div class="list-empty text-error">Failed to retrieve chunks: ${error.message}</div>`;
        list.classList.remove('hidden');
    }
}

function closeChunksModal() {
    document.getElementById('chunks-modal').classList.add('hidden');
}

// ── RAG CHAT Q&A INTERFACE ──
async function handleRAGQuery(event) {
    event.preventDefault();
    if (!state.selectedPatient) return;
    
    const input = document.getElementById('rag-question-input');
    const question = input.value.trim();
    if (!question) return;
    
    input.value = "";
    appendChatBubble('doctor', question);
    
    const assistantBubbleId = appendChatBubble('assistant', '<i class="fa-solid fa-spinner fa-spin"></i> Medical model searching RAG repository...');
    
    try {
        const data = await apiRequest(`/patients/${state.selectedPatient.id}/ask`, {
            method: 'POST',
            body: JSON.stringify({ question })
        });
        
        updateAssistantBubble(assistantBubbleId, data);
    } catch (error) {
        updateAssistantBubbleError(assistantBubbleId, error.message);
    }
}

function appendChatBubble(role, contentText) {
    const history = document.getElementById('rag-chat-history');
    
    // Clear placeholder on first chat
    const placeholder = history.querySelector('.chat-placeholder');
    if (placeholder) placeholder.remove();
    
    const bubbleId = `bubble-${Date.now()}`;
    const div = document.createElement('div');
    div.id = bubbleId;
    div.className = `chat-bubble ${role}`;
    div.innerHTML = `<p>${contentText}</p>`;
    
    history.appendChild(div);
    history.scrollTop = history.scrollHeight;
    
    return bubbleId;
}

function updateAssistantBubble(bubbleId, data) {
    const bubble = document.getElementById(bubbleId);
    if (!bubble) return;
    
    let citationsHtml = '';
    if (data.sources && data.sources.length > 0) {
        citationsHtml = `
            <div class="chat-citations">
                <h5>Source Documents Used</h5>
                ${data.sources.map((src, i) => `
                    <div class="citation-link" onclick="toggleCitationText(this)">
                        <i class="fa-solid fa-bookmark text-accent"></i> ${src.filename} (Chunk #${src.chunk_index + 1})
                        <span>Match: ${(src.similarity * 100).toFixed(0)}%</span>
                        <div class="citation-expanded-text hidden" style="margin-top:0.4rem; padding: 0.5rem; background:#0b0f19; border-radius:4px; font-size:0.8rem; line-height:1.4;">
                            ${src.chunk_text}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    bubble.innerHTML = `
        <p>${data.answer}</p>
        ${citationsHtml}
    `;
    
    const history = document.getElementById('rag-chat-history');
    history.scrollTop = history.scrollHeight;
}

function updateAssistantBubbleError(bubbleId, errorMsg) {
    const bubble = document.getElementById(bubbleId);
    if (bubble) {
        bubble.innerHTML = `<p class="text-error"><i class="fa-solid fa-triangle-exclamation"></i> Error: ${errorMsg}</p>`;
    }
}

function toggleCitationText(el) {
    const subtext = el.querySelector('.citation-expanded-text');
    if (subtext) {
        subtext.classList.toggle('hidden');
    }
}

// ── TAB 4: PRESCRIPTIONS & INTERACTIONS LOGIC ──
function loadInteractionsTab() {
    state.activeDrugList = [];
    renderDrugPills();
    
    document.getElementById('interaction-results').classList.add('hidden');
    document.getElementById('check-interactions-btn').disabled = true;
    document.getElementById('drug-input').value = "";
    
    loadEncounterLogs();
}

function addDrugItem() {
    const input = document.getElementById('drug-input');
    const drugName = input.value.trim();
    if (!drugName) return;
    
    // De-duplicate
    if (!state.activeDrugList.some(d => d.toLowerCase() === drugName.toLowerCase())) {
        state.activeDrugList.push(drugName);
        renderDrugPills();
    }
    
    input.value = "";
    input.focus();
}

function removeDrugItem(index) {
    state.activeDrugList.splice(index, 1);
    renderDrugPills();
}

function renderDrugPills() {
    const container = document.getElementById('drug-pills-container');
    container.innerHTML = state.activeDrugList.map((d, i) => `
        <div class="drug-pill">
            <span>${d}</span>
            <button class="remove-pill-btn" onclick="removeDrugItem(${i})">&times;</button>
        </div>
    `).join('');
    
    // We need at least 2 medications to check interactions
    document.getElementById('check-interactions-btn').disabled = state.activeDrugList.length < 2;
}

async function checkDrugInteractions() {
    if (state.activeDrugList.length < 2) return;
    
    const loader = document.getElementById('interaction-loader');
    const resultsBox = document.getElementById('interaction-results');
    
    loader.classList.remove('hidden');
    resultsBox.classList.add('hidden');
    
    const patientParam = state.selectedPatient ? `?patient_id=${state.selectedPatient.id}` : '';
    
    try {
        const data = await apiRequest(`/interactions/check${patientParam}`, {
            method: 'POST',
            body: JSON.stringify({
                medications: state.activeDrugList
            })
        });
        
        loader.classList.add('hidden');
        resultsBox.classList.remove('hidden');
        
        if (!data.has_interactions || data.interactions.length === 0) {
            resultsBox.innerHTML = `
                <div class="success-msg" style="padding:1.5rem; text-align:center;">
                    <i class="fa-solid fa-circle-check" style="font-size:1.5rem; margin-bottom:0.5rem; display:block;"></i>
                    <strong>No interactions detected!</strong> The analyzed drug combination appears safe.
                </div>
            `;
            return;
        }
        
        resultsBox.innerHTML = `
            <h4 class="interaction-report-title text-warning"><i class="fa-solid fa-triangle-exclamation"></i> Interaction Report — ${data.interactions.length} Warning(s)</h4>
            <div class="interactions-list">
                ${data.interactions.map(item => {
                    let severityClass = 'minor-severity';
                    let badgeClass = 'badge-minor';
                    if (item.severity.toUpperCase() === 'HIGH') {
                        severityClass = 'high-severity';
                        badgeClass = 'badge-high';
                    } else if (item.severity.toUpperCase() === 'MODERATE') {
                        severityClass = 'moderate-severity';
                        badgeClass = 'badge-moderate';
                    }
                    
                    return `
                        <div class="interaction-item-card ${severityClass}">
                            <div class="interaction-meta">
                                <span class="interaction-drugs">${item.drugs.join(' & ')}</span>
                                <span class="severity-badge ${badgeClass}">${item.severity}</span>
                            </div>
                            <p class="interaction-desc">${item.description}</p>
                            <div class="interaction-advice">
                                <strong>Clinical Action:</strong> ${item.clinical_advice}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    } catch (error) {
        loader.classList.add('hidden');
        alert("Failed to evaluate drug interactions: " + error.message);
    }
}

// ── ENCOUNTER LOGS LOGIC ──
async function loadEncounterLogs() {
    if (!state.selectedPatient) return;
    
    const container = document.getElementById('encounter-logs-list');
    container.innerHTML = `<div class="loader-container"><div class="spinner"></div><p>Fetching encounter history...</p></div>`;
    
    try {
        const list = await apiRequest(`/interactions/patient/${state.selectedPatient.id}`);
        state.activeEncounters = list;
        
        if (list.length === 0) {
            container.innerHTML = `<div class="list-empty">No clinical encounters recorded.</div>`;
            return;
        }
        
        container.innerHTML = list.map(enc => `
            <div class="encounter-item-card">
                <div class="encounter-header">
                    <span class="encounter-type"><i class="fa-solid fa-handshake-angle"></i> ${enc.type}</span>
                    <span class="encounter-date">${formatDate(enc.interaction_date)}</span>
                </div>
                <p class="encounter-notes">${enc.notes || 'No notes logged.'}</p>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="list-empty text-error">Failed to load encounter logs: ${error.message}</div>`;
    }
}

function openAddEncounterModal() {
    document.getElementById('encounter-form').reset();
    document.getElementById('encounter-date').value = new Date().toISOString().slice(0, 16); // Local datetime ISO
    document.getElementById('encounter-error').classList.add('hidden');
    document.getElementById('encounter-modal').classList.remove('hidden');
}

function closeAddEncounterModal() {
    document.getElementById('encounter-modal').classList.add('hidden');
}

async function handleEncounterSubmit(event) {
    event.preventDefault();
    if (!state.selectedPatient) return;
    
    const date = new Date(document.getElementById('encounter-date').value).toISOString();
    const type = document.getElementById('encounter-type').value.trim();
    const notes = document.getElementById('encounter-notes').value.trim() || null;
    const errorDiv = document.getElementById('encounter-error');
    
    errorDiv.classList.add('hidden');
    
    try {
        await apiRequest('/interactions', {
            method: 'POST',
            body: JSON.stringify({
                patient_id: state.selectedPatient.id,
                interaction_date: date,
                type,
                notes
            })
        });
        
        closeAddEncounterModal();
        loadEncounterLogs();
    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    }
}

// ── SPEECH RECOGNITION (VOICE DICTATION) ──
function toggleDictationMic() {
    const micBtn = document.getElementById('scribe-mic-btn');
    const textarea = document.getElementById('scribe-raw-input');
    
    // Check compatibility
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Speech Recognition API is not supported by your current browser. Please try Chrome, Edge, or Safari.");
        return;
    }
    
    if (state.isListening) {
        // Stop listening
        if (state.recognitionInstance) {
            state.recognitionInstance.stop();
        }
        return;
    }
    
    // Start listening
    if (!state.recognitionInstance) {
        state.recognitionInstance = new SpeechRecognition();
        state.recognitionInstance.continuous = true;
        state.recognitionInstance.interimResults = true;
        state.recognitionInstance.lang = 'en-US';
        
        state.recognitionInstance.onstart = () => {
            state.isListening = true;
            state.micPreExistingText = textarea.value;
            if (state.micPreExistingText && !state.micPreExistingText.endsWith(" ")) {
                state.micPreExistingText += " ";
            }
            micBtn.classList.add('listening');
            micBtn.title = "Stop voice dictation";
            micBtn.innerHTML = '<i class="fa-solid fa-microphone-slash"></i>';
        };
        
        state.recognitionInstance.onresult = (event) => {
            let interimTranscript = '';
            let finalTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }
            
            // Append transcribed text
            textarea.value = state.micPreExistingText + finalTranscript + interimTranscript;
            
            // Auto resize or trigger input event in case of listener dependencies
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        };
        
        state.recognitionInstance.onerror = (event) => {
            console.error("Speech Recognition Error:", event.error);
            // Don't show alert for 'no-speech', just let it log or handle gracefully
            if (event.error !== 'no-speech') {
                alert("Speech recognition error: " + event.error);
            }
            stopListeningState();
        };
        
        state.recognitionInstance.onend = () => {
            stopListeningState();
        };
    }
    
    try {
        state.recognitionInstance.start();
    } catch (err) {
        console.error("Failed to start Speech Recognition:", err);
    }
}

function stopListeningState() {
    state.isListening = false;
    const micBtn = document.getElementById('scribe-mic-btn');
    if (micBtn) {
        micBtn.classList.remove('listening');
        micBtn.title = "Start voice dictation";
        micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
    }
}

