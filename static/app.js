// State
let currentResumeText = null;
let currentResumePdfUrl = null;
let currentJdText = null;
let pollTimer = null;
let profileLoaded = false;
let loadedProfiles = [];
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
      bodyEl.innerHTML = UI.apiErrorBanner(res, body, { includeStatus: true });
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
    return '<div class="health-action"><span>' + message + '</span><button class="btn btn-sm btn-primary" onclick="switchTab(\'profile\'); toggleAddForm(true)">Set Up Profile</button></div>';
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
    loadedProfiles = profiles;
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
  if (profiles.length === 0) {
    sel.innerHTML = '<option value="">No profiles yet - add one in Profile tab</option>';
    return;
  }
  const defaultProfile = profiles.find(p => p.is_default) || profiles[0];
  sel.innerHTML = '<option value="" selected>Default: ' + profileLabel(defaultProfile) + '</option>'
    + profiles.map(p => {
        const suffix = p.is_default ? ' (default)' : '';
        return '<option value="' + p.id + '">'
          + profileLabel(p) + suffix + ' - ' + fmtDate(p.updated_at)
          + '</option>';
      }).join('');
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
    loadedProfiles = profiles;
    populateProfileSelector(profiles);
    if (profiles.length === 0) {
      el.innerHTML = UI.emptyState('No profiles yet. Click "+ Add Profile" to get started.');
      return;
    }
    el.innerHTML = '<div class="profile-table-wrap"><table>'
      + '<thead><tr><th>Name</th><th>Default</th><th>Preview</th><th>Created</th><th>Updated</th><th>PDF</th><th></th></tr></thead><tbody>'
      + profiles.map(p => `
        <tr>
          <td style="font-weight:600">${escHtml(p.name || 'Untitled #' + p.id)}</td>
          <td>${p.is_default ? '<span class="pill pill-ready">Default</span>' : ''}</td>
          <td><div class="jd-preview">${escHtml((p.skills_text || '').substring(0, 80))}</div></td>
          <td class="date-cell">${fmtDate(p.created_at)}</td>
          <td class="date-cell">${fmtDate(p.updated_at)}</td>
          <td>${p.pdf_path ? '<span class="status-msg">Saved</span>' : '<span class="status-msg">None</span>'}</td>
          <td>
            <div class="flex">
              <button class="btn btn-sm btn-muted" onclick="startEditProfile(${p.id})">Edit</button>
              <button class="btn btn-sm btn-muted danger-btn" onclick="deleteProfile(${p.id})">Delete</button>
            </div>
          </td>
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
    document.getElementById('new-profile-skills').value = '';
    document.getElementById('new-profile-default').checked = false;
    document.getElementById('new-profile-filename').textContent = 'No file chosen';
  }
}

function updateFilename(input) {
  document.getElementById('new-profile-filename').textContent = input.files[0]?.name || 'No file chosen';
}

async function previewNewProfilePdf() {
  const file = document.getElementById('new-profile-pdf').files[0];
  const errorEl = document.getElementById('add-profile-error');
  const successEl = document.getElementById('add-profile-success');
  errorEl.textContent = '';
  successEl.textContent = '';
  if (!file) { errorEl.textContent = 'Please choose a PDF file to preview.'; return; }

  setAddProfileProgress(true, 'Extracting text...');
  const form = new FormData();
  form.append('file', file);
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/upload/preview', { method: 'POST', body: form });
    if (!res.ok) { errorEl.innerHTML = UI.apiErrorBanner(res, body); return; }
    document.getElementById('new-profile-skills').value = body.data?.skills_text || '';
    successEl.textContent = 'Preview ready. Review the text before saving.';
  } catch (e) {
    errorEl.textContent = 'Network error: ' + e.message;
  } finally {
    setAddProfileProgress(false);
  }
}

async function submitNewProfile() {
  const file = document.getElementById('new-profile-pdf').files[0];
  const name = document.getElementById('new-profile-name').value.trim() || null;
  const skillsText = document.getElementById('new-profile-skills').value.trim();
  const isDefault = document.getElementById('new-profile-default').checked;
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  if (!file && !skillsText) {
    document.getElementById('add-profile-error').textContent = 'Preview a PDF or paste profile skills text.';
    return;
  }
  setAddProfileProgress(true, file ? 'Saving profile and PDF...' : 'Saving profile...');
  try {
    const request = file ? buildProfileUploadRequest(file, name, skillsText, isDefault) : {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, skills_text: skillsText, is_default: isDefault }),
    };
    const url = file ? '/api/profiles/upload' : '/api/profiles';
    const { response: res, payload: body } = await apiFetch(url, request);
    if (!res.ok) { document.getElementById('add-profile-error').innerHTML = UI.apiErrorBanner(res, body); return; }
    document.getElementById('add-profile-success').textContent = 'Profile saved!';
    profileLoaded = true;
    setHeaderBadge(true);
    document.getElementById('no-profile-notice').style.display = 'none';
    loadSystemStatus();
    setTimeout(() => { toggleAddForm(false); loadProfile(); }, 800);
  } catch (e) {
    document.getElementById('add-profile-error').textContent = 'Network error: ' + e.message;
  } finally {
    setAddProfileProgress(false);
  }
}

async function deleteProfile(id) {
  const profile = loadedProfiles.find(p => p.id === id);
  try {
    const { response: impactRes, payload: impactBody } = await apiFetch('/api/profiles/' + id + '/delete-impact');
    if (!impactRes.ok) { alert('Could not load delete impact.'); return; }
    const impact = impactBody.data || {};
    const message = 'Delete ' + profileLabel(profile || { id }) + '?\n\n'
      + 'Linked evaluations: ' + (impact.job_analyses_count || 0) + '\n'
      + 'Generated resumes: ' + (impact.generated_resumes_count || 0) + '\n\n'
      + 'Deleting the profile keeps existing history rows, but they will no longer have an active profile.';
    if (!confirm(message)) return;
    const { response: res } = await apiFetch('/api/profiles/' + id, { method: 'DELETE' });
    if (!res.ok) { alert('Delete failed.'); return; }
    loadProfile();
    checkProfile();
    loadSystemStatus();
  } catch (e) { alert('Network error: ' + e.message); }
}

function startEditProfile(id) {
  const profile = loadedProfiles.find(p => p.id === id);
  if (!profile) return;
  document.getElementById('edit-profile-id').value = String(profile.id);
  document.getElementById('edit-profile-name').value = profile.name || '';
  document.getElementById('edit-profile-skills').value = profile.skills_text || '';
  document.getElementById('edit-profile-default').checked = profile.is_default === true;
  document.getElementById('edit-profile-error').textContent = '';
  document.getElementById('edit-profile-success').textContent = '';
  document.getElementById('edit-profile-card').style.display = 'block';
}

function cancelEditProfile() {
  document.getElementById('edit-profile-card').style.display = 'none';
  document.getElementById('edit-profile-error').textContent = '';
  document.getElementById('edit-profile-success').textContent = '';
}

async function saveProfileEdit() {
  const id = document.getElementById('edit-profile-id').value;
  const name = document.getElementById('edit-profile-name').value.trim() || null;
  const skillsText = document.getElementById('edit-profile-skills').value.trim();
  const isDefault = document.getElementById('edit-profile-default').checked;
  const errorEl = document.getElementById('edit-profile-error');
  const successEl = document.getElementById('edit-profile-success');
  errorEl.textContent = '';
  successEl.textContent = '';
  if (!skillsText) { errorEl.textContent = 'Skills text is required.'; return; }
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, skills_text: skillsText, is_default: isDefault }),
    });
    if (!res.ok) { errorEl.innerHTML = UI.apiErrorBanner(res, body); return; }
    successEl.textContent = 'Profile updated.';
    await loadProfile();
    await checkProfile();
    loadSystemStatus();
  } catch (e) {
    errorEl.textContent = 'Network error: ' + e.message;
  }
}

function setAddProfileProgress(show, label) {
  document.getElementById('add-profile-progress').style.display = show ? 'flex' : 'none';
  if (label) document.getElementById('add-profile-progress-label').textContent = label;
}

function buildProfileUploadRequest(file, name, skillsText, isDefault) {
  const form = new FormData();
  form.append('file', file);
  if (name) form.append('name', name);
  if (skillsText) form.append('skills_text', skillsText);
  form.append('is_default', isDefault ? 'true' : 'false');
  return { method: 'POST', body: form };
}

// ---- Evaluate ----
async function runEvaluate() {
  const jd = document.getElementById('jd-input').value.trim();
  if (!jd) { setEvalError('Please paste a job description.'); return; }

  currentJdText = jd;
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
    if (!res.ok) { setEvalApiError(res, body); return; }
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
        currentJdText = job.jd_full_text || currentJdText;
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

async function fetchAndOpenModal(jobId, showChecklist) {
  try {
    const { response: res, payload: body } = await apiFetch('/api/history/' + jobId);
    const resumes = body.data?.generated_resumes;
    if (resumes && resumes.length > 0) {
      const resume = resumes[0];
      currentResumeText = resume.resume_text;
      currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
      currentJdText = body.data?.jd_full_text || body.data?.jd_snippet || currentJdText;
      openModal();
      if (showChecklist) showReadinessChecklist();
    }
  } catch (_) {}
}

// ---- Modal ----
function openModal() {
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('download-resume-pdf').hidden = !currentResumePdfUrl;
  hideReadinessChecklist();
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
  showReadinessChecklist();
}

function confirmResumePdfDownload() {
  if (!currentResumePdfUrl) return;
  window.open(currentResumePdfUrl, '_blank', 'noopener');
}

function showReadinessChecklist() {
  const panel = document.getElementById('readiness-panel');
  const summary = document.getElementById('readiness-summary');
  const list = document.getElementById('readiness-list');
  if (!panel || !summary || !list) return;

  const checks = buildReadinessChecks(currentResumeText || '', currentJdText || '');
  const failCount = checks.filter(c => c.status === 'fail').length;
  const warnCount = checks.filter(c => c.status === 'warn').length;
  summary.textContent = failCount > 0
    ? `${failCount} fail, ${warnCount} warn before download`
    : warnCount > 0
      ? `${warnCount} warnings before download`
      : 'Ready for PDF download';
  summary.className = 'readiness-summary ' + (
    failCount > 0 ? 'readiness-fail' : warnCount > 0 ? 'readiness-warn' : 'readiness-pass'
  );
  list.innerHTML = checks.map(function(check) {
    return '<li class="readiness-item readiness-' + check.status + '">'
      + '<span class="readiness-status">' + check.status.toUpperCase() + '</span>'
      + '<div><strong>' + escHtml(check.label) + '</strong><span>' + escHtml(check.message) + '</span></div>'
      + '</li>';
  }).join('');
  panel.hidden = false;
}

function hideReadinessChecklist() {
  const panel = document.getElementById('readiness-panel');
  if (panel) panel.hidden = true;
}

function buildReadinessChecks(resumeText, jdText) {
  const resume = normalizeText(resumeText);
  const jd = normalizeText(jdText);
  const resumeWords = wordList(resume);
  const jdWords = wordList(jd);
  const jdKeywords = topKeywords(jdWords, 12);
  const matchedKeywords = jdKeywords.filter(word => resume.includes(word));
  const jdKeywordRatio = jdKeywords.length === 0 ? 0 : matchedKeywords.length / jdKeywords.length;
  const jdKeywordCheck = jdKeywords.length === 0
    ? readiness('warn', 'JD keywords', 'No full JD text is available, so keyword alignment cannot be verified.')
    : jdKeywordRatio >= 0.5
      ? readiness('pass', 'JD keywords', `Matches ${matchedKeywords.length}/${jdKeywords.length} important JD terms.`)
      : jdKeywordRatio >= 0.25
        ? readiness('warn', 'JD keywords', `Matches ${matchedKeywords.length}/${jdKeywords.length} important JD terms; add missing role keywords if they are truthful.`)
        : readiness('fail', 'JD keywords', `Only ${matchedKeywords.length}/${jdKeywords.length} important JD terms appear in the resume.`);

  const jdSkills = skillKeywords(jd);
  const matchedSkills = jdSkills.filter(skill => resume.includes(skill));
  const skillCheck = jdSkills.length === 0
    ? readiness('warn', 'Required skills', 'No recognizable must-have skills were found in the JD text.')
    : matchedSkills.length === jdSkills.length
      ? readiness('pass', 'Required skills', `Covers ${matchedSkills.length}/${jdSkills.length} detected JD skills.`)
      : matchedSkills.length > 0
        ? readiness('warn', 'Required skills', `Covers ${matchedSkills.length}/${jdSkills.length} detected JD skills; review the missing ones.`)
        : readiness('fail', 'Required skills', 'Detected JD skills are not visible in the tailored resume.');

  const wordCount = resumeWords.length;
  const lengthCheck = wordCount >= 250 && wordCount <= 900
    ? readiness('pass', 'Resume length', `${wordCount} words is within a recruiter-friendly range.`)
    : wordCount >= 150 && wordCount <= 1200
      ? readiness('warn', 'Resume length', `${wordCount} words may be acceptable, but review density before sending.`)
      : readiness('fail', 'Resume length', `${wordCount} words is outside the expected range for a focused resume.`);

  const hasPlaceholders = /\b(todo|tbd|lorem|placeholder|xxx)\b/i.test(resumeText);
  const hasSections = /\b(experience|skills|projects|education|summary)\b/i.test(resumeText);
  const formatCheck = !hasPlaceholders && hasSections && resumeText.split('\n').length >= 6
    ? readiness('pass', 'Format', 'Contains resume sections and no obvious placeholders.')
    : hasPlaceholders
      ? readiness('fail', 'Format', 'Remove placeholder text before exporting.')
      : readiness('warn', 'Format', 'Section structure is not obvious; review formatting before exporting.');

  const metricMatches = resumeText.match(/\b(\d+[%+]|\$[\d,.]+|\d+x|\d+\s*(users|customers|requests|hours|days|weeks|months|years|people|teams))\b/gi) || [];
  const metricsCheck = metricMatches.length >= 2
    ? readiness('pass', 'Quantified impact', `Includes ${metricMatches.length} quantified proof points.`)
    : metricMatches.length === 1
      ? readiness('warn', 'Quantified impact', 'Only one quantified result is visible; add more evidence if accurate.')
      : readiness('fail', 'Quantified impact', 'No quantified achievements detected.');

  const riskyClaims = resumeText.match(/\b(expert in everything|guaranteed|world-class|best-in-class|master of all|flawless)\b/gi) || [];
  const riskCheck = riskyClaims.length === 0
    ? readiness('pass', 'Risk statement', 'No obvious overclaiming markers detected.')
    : readiness('warn', 'Risk statement', `Review potentially risky wording: ${riskyClaims.slice(0, 3).join(', ')}.`);

  return [jdKeywordCheck, skillCheck, lengthCheck, formatCheck, metricsCheck, riskCheck];
}

function readiness(status, label, message) {
  return { status, label, message };
}

function normalizeText(text) {
  return String(text || '').toLowerCase();
}

function wordList(text) {
  return normalizeText(text).match(/[a-z][a-z0-9+#.-]{2,}/g) || [];
}

function topKeywords(words, limit) {
  const stop = new Set([
    'and', 'the', 'for', 'with', 'this', 'that', 'you', 'your', 'our', 'are',
    'will', 'from', 'have', 'has', 'job', 'role', 'team', 'work', 'years',
    'experience', 'skills', 'ability', 'using', 'including', 'about',
  ]);
  const counts = new Map();
  for (const word of words) {
    if (stop.has(word) || word.length < 4) continue;
    counts.set(word, (counts.get(word) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(entry => entry[0]);
}

function skillKeywords(text) {
  const catalog = [
    'python', 'fastapi', 'django', 'flask', 'sql', 'postgres', 'postgresql',
    'mysql', 'redis', 'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'react',
    'typescript', 'javascript', 'node', 'etl', 'airflow', 'spark', 'api',
    'graphql', 'terraform', 'ci/cd', 'linux', 'machine learning',
  ];
  return catalog.filter(skill => text.includes(skill));
}

// ---- Helpers ----
function resumeActionsHtml(item) {
  if (!item.resume_id) {
    return '<span style="color:var(--muted);font-size:0.8rem">—</span>';
  }
  return `<div class="flex">
    <button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal('${item.id}')">View</button>
    <button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal('${item.id}', true)">PDF</button>
  </div>`;
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

document.getElementById('resume-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
