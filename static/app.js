// State
let currentResumeText = null;
let currentResumePdfUrl = null;
let pollTimer = null;
let profileLoaded = false;
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

// ---- System status ----
async function loadSystemStatus() {
  const bodyEl = document.getElementById('system-status-body');
  const summaryEl = document.getElementById('system-status-summary');
  if (!bodyEl || !summaryEl) return;

  summaryEl.textContent = 'Checking readiness...';
  bodyEl.innerHTML = UI.loadingState('Loading...');

  try {
    const { response: res, payload: body } = await apiFetch('/api/health');
    if (!res.ok) {
      summaryEl.textContent = 'Health check failed';
      bodyEl.innerHTML = '<div class="health-message health-error">' + escHtml(formatApiError(res, body, { includeStatus: true })) + '</div>';
      return;
    }
    renderSystemStatus(body.data || {}, body.meta || {});
  } catch (e) {
    summaryEl.textContent = 'Health check failed';
    bodyEl.innerHTML = '<div class="health-message health-error">Network error: ' + escHtml(e.message) + '</div>';
  }
}

function renderSystemStatus(data, meta) {
  const container = document.getElementById('system-status');
  const bodyEl = document.getElementById('system-status-body');
  const summaryEl = document.getElementById('system-status-summary');
  if (!container || !bodyEl || !summaryEl) return;

  const ready = data.can_evaluate === true;
  const degraded = data.status === 'degraded';
  container.className = 'system-status ' + (ready ? 'system-status-ready' : degraded ? 'system-status-error' : 'system-status-warn');
  summaryEl.textContent = ready ? 'Ready to evaluate jobs' : degraded ? 'Needs attention before scoring' : 'Finish setup before scoring';

  const checks = data.checks || {};
  const counts = data.counts || {};
  const requestId = meta.request_id || '';
  const checksHtml = Object.keys(checks).map(function(key) {
    const check = checks[key] || {};
    const status = check.status || 'warning';
    const message = check.message || '';
    const statusClass = ['ok', 'warning', 'error'].includes(status) ? status : 'warning';
    const backend = check.backend ? ' (' + escHtml(check.backend) + ')' : '';
    return '<div class="health-item health-' + statusClass + '">'
      + '<span class="health-dot"></span>'
      + '<div><strong>' + healthLabel(key) + backend + '</strong><span>' + escHtml(message) + '</span></div>'
      + '</div>';
  }).join('');

  const actions = data.next_actions || [];
  const actionsHtml = actions.length > 0
    ? '<div class="health-actions">' + actions.map(healthActionHtml).join('') + '</div>'
    : '<div class="health-message health-ok">All required setup is ready.</div>';

  bodyEl.innerHTML =
    '<div class="health-counts">'
      + '<span><strong>' + countText(counts.profiles) + '</strong> profiles</span>'
      + '<span><strong>' + countText(counts.job_listings) + '</strong> job listings</span>'
      + (requestId ? '<span class="request-id">Request ID: ' + escHtml(requestId) + '</span>' : '')
    + '</div>'
    + '<div class="health-grid">' + checksHtml + '</div>'
    + actionsHtml;
}

function healthActionHtml(action) {
  const kind = action.kind || '';
  const message = escHtml(action.message || '');
  if (kind === 'profile') {
    return '<div class="health-action"><span>' + message + '</span><button class="btn btn-sm btn-primary" onclick="switchTab(\'profile\'); toggleAddForm(true)">Add Profile</button></div>';
  }
  if (kind === 'job_listings') {
    return '<div class="health-action"><span>' + message + '</span><a class="btn btn-sm btn-muted" href="/jobs.html">JD Database</a></div>';
  }
  return '<div class="health-action"><span>' + message + '</span></div>';
}

function healthLabel(key) {
  if (key === 'api') return 'API';
  if (key === 'db') return 'DB';
  if (key === 'llm') return 'LLM';
  return escHtml(key);
}

function countText(value) {
  return value == null ? '-' : String(value);
}

// ---- Profile ----
async function checkProfile() {
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles');
    const profiles = body.data || [];
    if (res.ok && profiles.length > 0) {
      profileLoaded = true;
      setHeaderBadge(true);
      document.getElementById('no-profile-notice').style.display = 'none';
    } else {
      profileLoaded = false;
      setHeaderBadge(false);
      document.getElementById('no-profile-notice').style.display = 'block';
    }
    populateProfileSelector(profiles);
  } catch (_) {}
}

function populateProfileSelector(profiles) {
  const sel = document.getElementById('profile-select');
  if (!sel) return;
  sel.innerHTML = profiles.length === 0
    ? '<option value="">No profiles yet — add one in Profile tab</option>'
    : profiles.map(p =>
        `<option value="${p.id}">${escHtml(p.name || 'Untitled #' + p.id)} — ${fmtDate(p.updated_at)}</option>`
      ).join('');
}

function setHeaderBadge(hasProfile) {
  const el = document.getElementById('header-profile-badge');
  if (hasProfile) {
    el.innerHTML = '<span class="profile-badge profile-set">&#10003; Profile set</span>';
  } else {
    el.innerHTML = '<span class="profile-badge profile-unset">! No profile</span>';
  }
}

async function loadProfile() {
  const el = document.getElementById('profiles-list');
  if (!el) return;
  el.innerHTML = UI.loadingState('Loading...');
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles');
    if (!res.ok) { el.innerHTML = UI.emptyState('Error loading profiles.'); return; }
    const profiles = body.data || [];
    populateProfileSelector(profiles);
    if (profiles.length === 0) {
      el.innerHTML = UI.emptyState('No profiles yet. Click "+ Add Profile" to get started.');
      return;
    }
    el.innerHTML = '<div class="card" style="padding:0;overflow:hidden"><table>'
      + '<thead><tr><th>Name</th><th>Preview</th><th>Updated</th><th></th></tr></thead><tbody>'
      + profiles.map(p => `
        <tr>
          <td style="font-weight:600">${escHtml(p.name || 'Untitled #' + p.id)}</td>
          <td><div class="jd-preview">${escHtml((p.skills_text || '').substring(0, 80))}</div></td>
          <td style="font-size:0.8rem;color:var(--muted)">${fmtDate(p.updated_at)}</td>
          <td><button class="btn btn-sm btn-muted" style="color:var(--red)" onclick="deleteProfile(${p.id})">Delete</button></td>
        </tr>`).join('')
      + '</tbody></table></div>';
  } catch (e) {
    el.innerHTML = UI.emptyState('Network error.');
  }
}

function toggleAddForm(show) {
  document.getElementById('add-profile-card').style.display = show ? 'block' : 'none';
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  if (!show) {
    document.getElementById('new-profile-name').value = '';
    document.getElementById('new-profile-pdf').value = '';
    document.getElementById('new-profile-filename').textContent = 'No file chosen';
  }
}

function updateFilename(input) {
  document.getElementById('new-profile-filename').textContent = input.files[0]?.name || 'No file chosen';
}

async function submitNewProfile() {
  const file = document.getElementById('new-profile-pdf').files[0];
  const name = document.getElementById('new-profile-name').value.trim() || null;
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  if (!file) { document.getElementById('add-profile-error').textContent = 'Please choose a PDF file.'; return; }
  document.getElementById('add-profile-progress').style.display = 'flex';
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/upload', { method: 'POST', body: form });
    if (!res.ok) { document.getElementById('add-profile-error').textContent = body?.error?.message || 'Upload failed.'; return; }
    document.getElementById('add-profile-success').textContent = 'Profile saved!';
    profileLoaded = true;
    setHeaderBadge(true);
    document.getElementById('no-profile-notice').style.display = 'none';
    loadSystemStatus();
    setTimeout(() => { toggleAddForm(false); loadProfile(); }, 800);
  } catch (e) {
    document.getElementById('add-profile-error').textContent = 'Network error: ' + e.message;
  } finally {
    document.getElementById('add-profile-progress').style.display = 'none';
  }
}

async function deleteProfile(id) {
  if (!confirm('Delete this profile?')) return;
  try {
    const { response: res } = await apiFetch('/api/profiles/' + id, { method: 'DELETE' });
    if (!res.ok) { alert('Delete failed.'); return; }
    loadProfile();
    checkProfile();
    loadSystemStatus();
  } catch (e) { alert('Network error: ' + e.message); }
}

// ---- Evaluate ----
async function runEvaluate() {
  const jd = document.getElementById('jd-input').value.trim();
  if (!jd) { setEvalError('Please paste a job description.'); return; }

  setEvalError('');
  setEvalStatus('Evaluating…');
  setEvalBtnDisabled(true);
  hideResult();
  stopPoll();

  let data, cached;
  try {
    const profileId = document.getElementById('profile-select')?.value;
    const { response: res, payload: body } = await apiFetch('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd_text: jd, profile_id: profileId ? parseInt(profileId) : null }),
    });
    if (!res.ok) { setEvalError(formatApiError(res, body)); return; }
    data = body.data;
    cached = body.meta?.cached === true;
  } catch (e) {
    setEvalError('Network error: ' + e.message);
    return;
  } finally {
    setEvalBtnDisabled(false);
    setEvalStatus('');
  }

  renderEvalResult(data, cached);

  if (data.status === 'needs_tailoring') {
    showTailoringSpinner();
    startPoll(data.job_analysis_id);
  }
}

function renderEvalResult(data, cached) {
  const badge = document.getElementById('result-badge');
  badge.textContent = data.score + '/100';
  badge.className = 'score-badge ' + statusBadgeClass(data.status);

  document.getElementById('result-message').textContent = data.message || '';
  document.getElementById('result-cached').textContent = cached ? '(cached)' : '';
  document.getElementById('result-explanation').textContent = data.explanation || '';
  renderTags('result-strengths', data.strengths);
  renderTags('result-gaps', data.gaps);

  document.getElementById('tailoring-spinner').style.display = 'none';
  document.getElementById('tailoring-done').style.display = 'none';
  document.getElementById('eval-result').style.display = 'block';
}

function statusBadgeClass(status) {
  return UI.statusBadgeClass(status);
}

function statusPillClass(status) {
  return UI.statusPillClass(status);
}

// ---- Polling for tailoring ----
function startPoll(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const { response: res, payload: body } = await apiFetch('/api/history/' + jobId);
      if (!res.ok) return;
      const job = body.data;
      if (job.can_submit && job.generated_resumes && job.generated_resumes.length > 0) {
        stopPoll();
        const resume = job.generated_resumes[0];
        currentResumeText = resume.resume_text;
        currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
        document.getElementById('tailoring-spinner').style.display = 'none';
        document.getElementById('tailoring-done').style.display = 'flex';
      }
    } catch (_) {}
  }, 2000);
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function showTailoringSpinner() {
  document.getElementById('tailoring-spinner').style.display = 'flex';
  document.getElementById('tailoring-done').style.display = 'none';
}

// ---- History ----
async function loadHistory() {
  const el = document.getElementById('history-content');
  el.innerHTML = UI.loadingState('Loading...');
  try {
    const { response: res, payload: body } = await apiFetch('/api/history');
    if (!res.ok) { el.innerHTML = UI.emptyState('Error loading history.'); return; }
    const grouped = body.meta?.grouped || {};
    const sections = [
      { key: 'ready_to_submit', label: 'Ready to Submit' },
      { key: 'needs_tailoring', label: 'Needs Tailoring' },
      { key: 'skip', label: 'Skipped' },
    ];
    let html = '';
    for (const { key, label } of sections) {
      const items = grouped[key] || [];
      html += '<div class="history-section"><div class="history-section-hdr">' + label + ' (' + items.length + ')</div>';
      if (items.length === 0) {
        html += '<div class="empty" style="padding:0.75rem 0">None</div>';
      } else {
        html += '<div class="card" style="padding:0;overflow:hidden"><table><thead><tr><th>Score</th><th>JD Preview</th><th>Created</th><th>Submittable</th></tr></thead><tbody>';
        for (const item of items) {
          html += '<tr>'
            + '<td><span class="' + statusPillClass(item.status) + '">' + (item.score != null ? item.score : '—') + '</span></td>'
            + '<td><div class="jd-preview">' + escHtml(item.jd_snippet || '') + '</div></td>'
            + '<td style="font-size:0.8rem;color:var(--muted)">' + fmtDate(item.created_at) + '</td>'
            + '<td>' + (item.can_submit ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--muted)">—</span>') + '</td>'
            + '</tr>';
        }
        html += '</tbody></table></div>';
      }
      html += '</div>';
    }
    const total = body.meta?.total ?? 0;
    const subCount = body.meta?.submittable_count ?? 0;
    el.innerHTML = '<div style="font-size:0.82rem;color:var(--muted);margin-bottom:0.75rem">Total: ' + total + ' &nbsp;|&nbsp; Submittable: ' + subCount + '</div>' + html;
  } catch (e) {
    el.innerHTML = UI.emptyState('Network error.');
  }
}

// ---- Submittable ----
async function loadSubmittable() {
  const tbody = document.getElementById('submittable-body');
  tbody.innerHTML = '<tr><td colspan="5" class="empty">Loading...</td></tr>';
  try {
    const { response: res, payload: body } = await apiFetch('/api/submittable');
    if (!res.ok) { tbody.innerHTML = '<tr><td colspan="5" class="empty">Error.</td></tr>'; return; }
    const items = body.data || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">No submittable resumes yet.</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(function(item) {
      return '<tr>'
        + '<td><strong>' + (item.score != null ? item.score : '—') + '</strong></td>'
        + '<td><span class="' + statusPillClass(item.status) + '">' + fmtStatus(item.status) + '</span></td>'
        + '<td><div class="jd-preview">' + escHtml(item.jd_snippet || '') + '</div></td>'
        + '<td style="font-size:0.8rem;color:var(--muted)">' + fmtDate(item.created_at) + '</td>'
        + '<td>' + resumeActionsHtml(item) + '</td>'
        + '</tr>';
    }).join('');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">Network error.</td></tr>';
  }
}

async function fetchAndOpenModal(jobId) {
  try {
    const { response: res, payload: body } = await apiFetch('/api/history/' + jobId);
    const resumes = body.data?.generated_resumes;
    if (resumes && resumes.length > 0) {
      const resume = resumes[0];
      currentResumeText = resume.resume_text;
      currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
      openModal();
    }
  } catch (_) {}
}

// ---- Modal ----
function openModal() {
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('download-resume-pdf').hidden = !currentResumePdfUrl;
  document.getElementById('resume-modal').classList.add('open');
}

function closeModal() {
  document.getElementById('resume-modal').classList.remove('open');
}

async function copyResume() {
  if (!currentResumeText) return;
  try { await navigator.clipboard.writeText(currentResumeText); } catch (_) {}
}

function downloadCurrentResumePdf() {
  if (!currentResumePdfUrl) return;
  window.open(currentResumePdfUrl, '_blank', 'noopener');
}

// ---- Helpers ----
function resumeActionsHtml(item) {
  if (!item.resume_id) {
    return '<span style="color:var(--muted);font-size:0.8rem">—</span>';
  }
  const pdfUrl = item.pdf_url || '/api/generated-resumes/' + item.resume_id + '/pdf';
  return `<div class="flex">
    <button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal('${item.id}')">View</button>
    <a class="btn btn-sm btn-muted" href="${escHtml(pdfUrl)}" target="_blank" rel="noreferrer">PDF</a>
  </div>`;
}

function renderTags(id, items) {
  const ul = document.getElementById(id);
  ul.innerHTML = (items || []).map(function(t) { return '<li>' + escHtml(t) + '</li>'; }).join('');
}

function setEvalStatus(msg) { document.getElementById('eval-status').textContent = msg; }
function setEvalError(msg) { document.getElementById('eval-error').textContent = msg; }
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

function escHtml(s) {
  return UI.escHtml(s);
}

async function apiFetch(url, options) {
  return UI.apiFetch(url, options);
}

function formatApiError(response, payload, options) {
  return UI.formatApiError(response, payload, options);
}

document.getElementById('resume-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
