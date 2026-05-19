// State — declared with `var` so they hoist onto window. This lets
// feature modules (loaded after this file) read/write the same variables
// without an explicit RH namespace. See static/features/beautify.js.
var currentResumeText = null;
var currentResumePdfUrl = null;
var currentJdText = null;
var currentResumeId = null;
var currentBeautifications = [];
var currentResumeVersions = [];
var currentBaselineText = null;
var pollTimer = null;
var profileLoaded = false;
var loadedProfiles = [];
const UI = window.ResumeHelper;

// ---- Init ----
window.addEventListener('DOMContentLoaded', () => {
  loadSystemStatus();
  checkProfile();
  applyInitialHash();
});

// ---- Tab switching ----
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'history') loadHistory();
  if (name === 'submittable') loadSubmittable();
  if (name === 'profile') loadProfile();
}

function applyInitialHash() {
  const target = window.location.hash.replace('#', '');
  const allowed = ['evaluate', 'history', 'submittable', 'profile'];
  if (allowed.includes(target)) {
    switchTab(target);
  }
}

// Feature scripts loaded after app.js provide loadSystemStatus, checkProfile,
// loadHistory, loadSubmittable, runEvaluate, and resume modal handlers.

// ---- Helpers ----
function resumeActionsHtml(item) {
  if (item.resume_id) {
    return `<div class="flex">
      <button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal('${item.id}')">View</button>
      <button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal('${item.id}', true)">PDF</button>
    </div>`;
  }
  if (item.pdf_url && item.pdf_kind === 'baseline') {
    return `<div class="flex">
      <a class="btn btn-sm btn-muted" href="${item.pdf_url}" target="_blank" rel="noopener" title="Score ≥85: ready to submit using your baseline profile">Baseline PDF</a>
    </div>`;
  }
  return '<span style="color:var(--muted);font-size:0.8rem">—</span>';
}

function renderTags(id, items) {
  const ul = document.getElementById(id);
  ul.innerHTML = (items || []).map(function(t) { return '<li>' + escHtml(t) + '</li>'; }).join('');
}

function setEvalStatus(msg) { document.getElementById('eval-status').textContent = msg; }
function setEvalError(msg) { document.getElementById('eval-error').textContent = msg; }
function setEvalApiError(response, payload) { document.getElementById('eval-error').innerHTML = UI.apiErrorBanner(response, payload); }
function setEvalBtnDisabled(v) { document.getElementById('eval-btn').disabled = v; }
function hideResult() { document.getElementById('eval-result').style.display = 'none'; }

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtStatus(s) {
  if (s === 'ready_to_submit') return 'Ready';
  if (s === 'needs_tailoring') return 'Tailoring';
  if (s === 'skip') return 'Skipped';
  return s || '—';
}

function profileLabel(profile) {
  if (!profile) return 'Default profile';
  return escHtml(profile.name || 'Untitled #' + profile.id);
}

function escHtml(s) {
  return UI.escHtml(s);
}

async function apiFetch(url, options) {
  return UI.apiFetch(url, options);
}

function formatApiError(response, payload, options) {
  return UI.formatApiError(response, payload, options);
}
