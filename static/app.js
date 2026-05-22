// State
let currentResumeText = null;
let currentResumePdfUrl = null;
let currentJdText = null;
let pollTimer = null;
let profileLoaded = false;
let loadedProfiles = [];
const UI = window.ResumeHelper;

window.addEventListener('DOMContentLoaded', () => {
  loadSystemStatus();
  checkProfile();
  applyInitialHash();
});

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'history') loadHistory();
  if (name === 'submittable') loadSubmittable();
  if (name === 'profile') loadProfile();
}

function applyInitialHash() {
  const target = window.location.hash.replace('#', '');
  if (['evaluate', 'history', 'submittable', 'profile'].includes(target)) switchTab(target);
}

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
  const checksHtml = Object.keys(checks).map((key) => {
    const check = checks[key] || {};
    const status = ['ok', 'warning', 'error'].includes(check.status) ? check.status : 'warning';
    const backend = check.backend ? ' (' + escHtml(check.backend) + ')' : '';
    return '<div class="health-item health-' + status + '"><span class="health-dot"></span><div><strong>'
      + healthLabel(key) + backend + '</strong><span>' + escHtml(check.message || '') + '</span></div></div>';
  }).join('');
  const actions = data.next_actions || [];
  const actionsHtml = actions.length
    ? '<div class="health-actions">' + actions.map(healthActionHtml).join('') + '</div>'
    : '<div class="health-message health-ok">All required setup is ready.</div>';
  bodyEl.innerHTML = '<div class="health-counts">'
    + '<span><strong>' + countText(counts.profiles) + '</strong> profiles</span>'
    + '<span><strong>' + countText(counts.job_listings) + '</strong> job listings</span>'
    + (meta.request_id ? '<span class="request-id">Request ID: ' + escHtml(meta.request_id) + '</span>' : '')
    + '</div><div class="health-grid">' + checksHtml + '</div>' + actionsHtml;
}

function healthActionHtml(action) {
  const message = escHtml(action.message || '');
  if (action.kind === 'profile') return '<div class="health-action"><span>' + message + '</span><button class="btn btn-sm btn-primary" onclick="switchTab(\'profile\'); toggleAddForm(true)">Set Up Profile</button></div>';
  if (action.kind === 'job_listings') return '<div class="health-action"><span>' + message + '</span><a class="btn btn-sm btn-muted" href="/jobs.html">JD Database</a></div>';
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

async function checkProfile() {
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles');
    const profiles = res.ok ? (body.data || []) : [];
    loadedProfiles = profiles;
    profileLoaded = profiles.length > 0;
    setHeaderBadge(profileLoaded, profiles.find((p) => p.is_default) || profiles[0]);
    document.getElementById('no-profile-notice').style.display = profileLoaded ? 'none' : 'block';
    populateProfileSelector(profiles);
  } catch (_) {
    profileLoaded = false;
  }
}

function populateProfileSelector(profiles) {
  const sel = document.getElementById('profile-select');
  if (!sel) return;
  if (profiles.length === 0) {
    sel.innerHTML = '<option value="">No profiles yet - add one in Profile tab</option>';
    return;
  }
  sel.innerHTML = profiles.map((p) => {
    const label = (p.is_default ? 'Default: ' : '') + (p.name || 'Untitled #' + p.id) + ' - ' + fmtDate(p.updated_at);
    return '<option value="' + p.id + '"' + (p.is_default ? ' selected' : '') + '>' + escHtml(label) + '</option>';
  }).join('');
}

function setHeaderBadge(hasProfile, profile) {
  const el = document.getElementById('header-profile-badge');
  if (!el) return;
  el.innerHTML = hasProfile
    ? '<span class="profile-badge profile-set">&#10003; Default: ' + escHtml(profile?.name || 'Untitled #' + profile?.id) + '</span>'
    : '<span class="profile-badge profile-unset">! No profile</span>';
}

async function loadProfile() {
  const el = document.getElementById('profiles-list');
  if (!el) return;
  el.innerHTML = UI.loadingState('Loading...');
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles');
    if (!res.ok) {
      el.innerHTML = UI.emptyState('Error loading profiles.');
      return;
    }
    const profiles = body.data || [];
    loadedProfiles = profiles;
    populateProfileSelector(profiles);
    if (profiles.length === 0) {
      el.innerHTML = UI.emptyState('No profiles yet. Click "+ Add Profile" to get started.');
      return;
    }
    el.innerHTML = '<div class="profile-table-wrap"><table><thead><tr>'
      + '<th>Name</th><th>Preview</th><th>Created</th><th>Updated</th><th>Default</th><th>PDF</th><th></th>'
      + '</tr></thead><tbody>'
      + profiles.map(profileRowHtml).join('')
      + '</tbody></table></div>';
  } catch (_) {
    el.innerHTML = UI.emptyState('Network error.');
  }
}

function profileRowHtml(p) {
  const pdf = p.pdf_path ? '<span class="pill pill-ready">PDF</span>' : '<span class="status-msg">No PDF</span>';
  const defaultCell = p.is_default
    ? '<span class="pill pill-ready">Default</span>'
    : '<button class="btn btn-sm btn-muted" onclick="setDefaultProfile(' + p.id + ')">Make Default</button>';
  return '<tr>'
    + '<td style="font-weight:600">' + escHtml(p.name || 'Untitled #' + p.id) + '</td>'
    + '<td><div class="jd-preview">' + escHtml((p.skills_text || '').substring(0, 100)) + '</div></td>'
    + '<td class="date-cell">' + fmtDate(p.created_at) + '</td>'
    + '<td class="date-cell">' + fmtDate(p.updated_at) + '</td>'
    + '<td>' + defaultCell + '</td>'
    + '<td>' + pdf + '</td>'
    + '<td><div class="flex"><button class="btn btn-sm btn-muted" onclick="startEditProfile(' + p.id + ')">Edit</button>'
    + '<button class="btn btn-sm btn-muted danger-btn" onclick="deleteProfile(' + p.id + ')">Delete</button></div></td>'
    + '</tr>';
}

function toggleAddForm(show) {
  document.getElementById('add-profile-card').style.display = show ? 'block' : 'none';
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  if (!show) {
    document.getElementById('new-profile-name').value = '';
    document.getElementById('new-profile-pdf').value = '';
    document.getElementById('new-profile-filename').textContent = 'No file chosen';
    document.getElementById('new-profile-skills').value = '';
    document.getElementById('new-profile-default').checked = false;
  }
}

function updateFilename(input) {
  document.getElementById('new-profile-filename').textContent = input.files[0]?.name || 'No file chosen';
  document.getElementById('add-profile-success').textContent = '';
}

async function previewNewProfilePdf() {
  const file = document.getElementById('new-profile-pdf').files[0];
  if (!file) {
    document.getElementById('add-profile-error').textContent = 'Please choose a PDF file.';
    return;
  }
  setProfileProgress(true, 'Extracting text...');
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  const form = new FormData();
  form.append('file', file);
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/upload/preview', { method: 'POST', body: form });
    if (!res.ok) {
      document.getElementById('add-profile-error').textContent = formatApiError(res, body);
      return;
    }
    document.getElementById('new-profile-skills').value = body.data.skills_text || '';
    document.getElementById('add-profile-success').textContent = 'Preview ready. Review the text before saving.';
  } catch (e) {
    document.getElementById('add-profile-error').textContent = 'Network error: ' + e.message;
  } finally {
    setProfileProgress(false);
  }
}

async function submitNewProfile() {
  const file = document.getElementById('new-profile-pdf').files[0];
  const name = document.getElementById('new-profile-name').value.trim() || null;
  const skillsText = document.getElementById('new-profile-skills').value.trim();
  const isDefault = document.getElementById('new-profile-default').checked;
  document.getElementById('add-profile-error').textContent = '';
  document.getElementById('add-profile-success').textContent = '';
  if (!skillsText) {
    document.getElementById('add-profile-error').textContent = 'Preview a PDF or enter skills text before saving.';
    return;
  }
  setProfileProgress(true, 'Saving...');
  try {
    const options = file
      ? uploadProfileOptions(file, name, skillsText, isDefault)
      : jsonOptions('POST', { name, skills_text: skillsText, is_default: isDefault });
    const { response: res, payload: body } = await apiFetch(file ? '/api/profiles/upload' : '/api/profiles', options);
    if (!res.ok) {
      document.getElementById('add-profile-error').textContent = formatApiError(res, body);
      return;
    }
    document.getElementById('add-profile-success').textContent = 'Profile saved.';
    profileLoaded = true;
    loadSystemStatus();
    setTimeout(() => { toggleAddForm(false); loadProfile(); checkProfile(); }, 500);
  } catch (e) {
    document.getElementById('add-profile-error').textContent = 'Network error: ' + e.message;
  } finally {
    setProfileProgress(false);
  }
}

function uploadProfileOptions(file, name, skillsText, isDefault) {
  const form = new FormData();
  form.append('file', file);
  form.append('skills_text', skillsText);
  form.append('is_default', isDefault ? 'true' : 'false');
  if (name) form.append('name', name);
  return { method: 'POST', body: form };
}

function setProfileProgress(show, label) {
  document.getElementById('add-profile-progress').style.display = show ? 'flex' : 'none';
  if (label) document.getElementById('add-profile-progress-label').textContent = label;
}

function startEditProfile(id) {
  const profile = loadedProfiles.find((p) => p.id === id);
  if (!profile) return;
  document.getElementById('edit-profile-card').style.display = 'block';
  document.getElementById('edit-profile-id').value = String(profile.id);
  document.getElementById('edit-profile-name').value = profile.name || '';
  document.getElementById('edit-profile-skills').value = profile.skills_text || '';
  document.getElementById('edit-profile-default').checked = profile.is_default === true;
  document.getElementById('edit-profile-error').textContent = '';
  document.getElementById('edit-profile-success').textContent = '';
  document.getElementById('edit-profile-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cancelEditProfile() {
  document.getElementById('edit-profile-card').style.display = 'none';
}

async function saveProfileEdit() {
  const id = document.getElementById('edit-profile-id').value;
  const payload = {
    name: document.getElementById('edit-profile-name').value.trim() || null,
    skills_text: document.getElementById('edit-profile-skills').value.trim(),
    is_default: document.getElementById('edit-profile-default').checked,
  };
  if (!payload.skills_text) {
    document.getElementById('edit-profile-error').textContent = 'Skills text is required.';
    return;
  }
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id, jsonOptions('PUT', payload));
    if (!res.ok) {
      document.getElementById('edit-profile-error').textContent = formatApiError(res, body);
      return;
    }
    document.getElementById('edit-profile-success').textContent = 'Profile updated.';
    loadProfile();
    checkProfile();
    loadSystemStatus();
  } catch (e) {
    document.getElementById('edit-profile-error').textContent = 'Network error: ' + e.message;
  }
}

async function setDefaultProfile(id) {
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id, jsonOptions('PUT', { is_default: true }));
    if (!res.ok) {
      alert(formatApiError(res, body));
      return;
    }
    loadProfile();
    checkProfile();
  } catch (e) {
    alert('Network error: ' + e.message);
  }
}

async function deleteProfile(id) {
  let message = 'Delete this profile? Related evaluation history will no longer be tied to this profile, and generated resume records may be harder to trace.';
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id + '/delete-impact');
    if (res.ok) {
      const impact = body.data || {};
      message = 'Delete this profile? This affects ' + (impact.job_analyses_count || 0)
        + ' related job analyses and ' + (impact.generated_resumes_count || 0)
        + ' generated resume records. History rows remain, but their profile link will be cleared.';
    }
  } catch (_) {}
  if (!confirm(message)) return;
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id, { method: 'DELETE' });
    if (!res.ok) {
      alert(formatApiError(res, body));
      return;
    }
    cancelEditProfile();
    loadProfile();
    checkProfile();
    loadSystemStatus();
  } catch (e) {
    alert('Network error: ' + e.message);
  }
}

async function runEvaluate() {
  const jd = document.getElementById('jd-input').value.trim();
  if (!jd) {
    setEvalError('Please paste a job description.');
    return;
  }
  currentJdText = jd;
  setEvalError('');
  setEvalStatus('Evaluating...');
  setEvalBtnDisabled(true);
  hideResult();
  stopPoll();
  let data;
  let cached;
  try {
    const profileId = document.getElementById('profile-select')?.value;
    const { response: res, payload: body } = await apiFetch('/api/evaluate', jsonOptions('POST', {
      jd_text: jd,
      profile_id: profileId ? parseInt(profileId, 10) : null,
    }));
    if (!res.ok) {
      setEvalError(formatApiError(res, body));
      return;
    }
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

function statusBadgeClass(status) { return UI.statusBadgeClass(status); }
function statusPillClass(status) { return UI.statusPillClass(status); }

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
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function showTailoringSpinner() {
  document.getElementById('tailoring-spinner').style.display = 'flex';
  document.getElementById('tailoring-done').style.display = 'none';
}

async function loadHistory() {
  const el = document.getElementById('history-content');
  el.innerHTML = UI.loadingState('Loading...');
  try {
    const { response: res, payload: body } = await apiFetch('/api/history');
    if (!res.ok) {
      el.innerHTML = UI.emptyState('Error loading history.');
      return;
    }
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
          html += '<tr><td><span class="' + statusPillClass(item.status) + '">' + (item.score != null ? item.score : '-') + '</span></td>'
            + '<td><div class="jd-preview">' + escHtml(item.jd_snippet || '') + '</div></td>'
            + '<td class="date-cell">' + fmtDate(item.created_at) + '</td>'
            + '<td>' + (item.can_submit ? '<span style="color:var(--green)">Yes</span>' : '<span style="color:var(--muted)">No</span>') + '</td></tr>';
        }
        html += '</tbody></table></div>';
      }
      html += '</div>';
    }
    const total = body.meta?.total ?? 0;
    const subCount = body.meta?.submittable_count ?? 0;
    el.innerHTML = '<div style="font-size:0.82rem;color:var(--muted);margin-bottom:0.75rem">Total: ' + total + ' | Submittable: ' + subCount + '</div>' + html;
  } catch (_) {
    el.innerHTML = UI.emptyState('Network error.');
  }
}

async function loadSubmittable() {
  const tbody = document.getElementById('submittable-body');
  tbody.innerHTML = '<tr><td colspan="5" class="empty">Loading...</td></tr>';
  try {
    const { response: res, payload: body } = await apiFetch('/api/submittable');
    if (!res.ok) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Error.</td></tr>';
      return;
    }
    const items = body.data || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">No submittable resumes yet.</td></tr>';
      return;
    }
    tbody.innerHTML = items.map((item) => '<tr>'
      + '<td><strong>' + (item.score != null ? item.score : '-') + '</strong></td>'
      + '<td><span class="' + statusPillClass(item.status) + '">' + fmtStatus(item.status) + '</span></td>'
      + '<td><div class="jd-preview">' + escHtml(item.jd_snippet || '') + '</div></td>'
      + '<td class="date-cell">' + fmtDate(item.created_at) + '</td>'
      + '<td>' + resumeActionsHtml(item) + '</td></tr>').join('');
  } catch (_) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">Network error.</td></tr>';
  }
}

async function fetchAndOpenModal(jobId, showChecklist) {
  try {
    const { payload: body } = await apiFetch('/api/history/' + jobId);
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

function openModal() {
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('download-resume-pdf').hidden = !currentResumePdfUrl;
  hideReadinessChecklist();
  document.getElementById('resume-modal').classList.add('open');
}

function closeModal() { document.getElementById('resume-modal').classList.remove('open'); }

async function copyResume() {
  if (!currentResumeText) return;
  try { await navigator.clipboard.writeText(currentResumeText); } catch (_) {}
}

function downloadCurrentResumePdf() {
  if (!currentResumePdfUrl) return;
  showReadinessChecklist();
}

function confirmResumePdfDownload() {
  if (currentResumePdfUrl) window.open(currentResumePdfUrl, '_blank', 'noopener');
}

function showReadinessChecklist() {
  const panel = document.getElementById('readiness-panel');
  const summary = document.getElementById('readiness-summary');
  const list = document.getElementById('readiness-list');
  if (!panel || !summary || !list) return;

  const checks = buildReadinessChecks(currentResumeText || '', currentJdText || '');
  const failCount = checks.filter((c) => c.status === 'fail').length;
  const warnCount = checks.filter((c) => c.status === 'warn').length;
  summary.textContent = failCount > 0
    ? failCount + ' fail, ' + warnCount + ' warn before download'
    : warnCount > 0
      ? warnCount + ' warnings before download'
      : 'Ready for PDF download';
  summary.className = 'readiness-summary ' + (
    failCount > 0 ? 'readiness-fail' : warnCount > 0 ? 'readiness-warn' : 'readiness-pass'
  );
  list.innerHTML = checks.map((check) => '<li class="readiness-item readiness-' + check.status + '">'
    + '<span class="readiness-status">' + check.status.toUpperCase() + '</span>'
    + '<div><strong>' + escHtml(check.label) + '</strong><span>' + escHtml(check.message) + '</span></div>'
    + '</li>').join('');
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
  const matchedKeywords = jdKeywords.filter((word) => resume.includes(word));
  const jdKeywordRatio = jdKeywords.length === 0 ? 0 : matchedKeywords.length / jdKeywords.length;
  const jdKeywordCheck = jdKeywords.length === 0
    ? readiness('warn', 'JD keywords', 'No full JD text is available, so keyword alignment cannot be verified.')
    : jdKeywordRatio >= 0.5
      ? readiness('pass', 'JD keywords', 'Matches ' + matchedKeywords.length + '/' + jdKeywords.length + ' important JD terms.')
      : jdKeywordRatio >= 0.25
        ? readiness('warn', 'JD keywords', 'Matches ' + matchedKeywords.length + '/' + jdKeywords.length + ' important JD terms; add missing role keywords if they are truthful.')
        : readiness('fail', 'JD keywords', 'Only ' + matchedKeywords.length + '/' + jdKeywords.length + ' important JD terms appear in the resume.');

  const jdSkills = skillKeywords(jd);
  const matchedSkills = jdSkills.filter((skill) => resume.includes(skill));
  const skillCheck = jdSkills.length === 0
    ? readiness('warn', 'Required skills', 'No recognizable must-have skills were found in the JD text.')
    : matchedSkills.length === jdSkills.length
      ? readiness('pass', 'Required skills', 'Covers ' + matchedSkills.length + '/' + jdSkills.length + ' detected JD skills.')
      : matchedSkills.length > 0
        ? readiness('warn', 'Required skills', 'Covers ' + matchedSkills.length + '/' + jdSkills.length + ' detected JD skills; review the missing ones.')
        : readiness('fail', 'Required skills', 'Detected JD skills are not visible in the tailored resume.');

  const wordCount = resumeWords.length;
  const lengthCheck = wordCount >= 250 && wordCount <= 900
    ? readiness('pass', 'Resume length', wordCount + ' words is within a recruiter-friendly range.')
    : wordCount >= 150 && wordCount <= 1200
      ? readiness('warn', 'Resume length', wordCount + ' words may be acceptable, but review density before sending.')
      : readiness('fail', 'Resume length', wordCount + ' words is outside the expected range for a focused resume.');

  const hasPlaceholders = /\b(todo|tbd|lorem|placeholder|xxx)\b/i.test(resumeText);
  const hasSections = /\b(experience|skills|projects|education|summary)\b/i.test(resumeText);
  const formatCheck = !hasPlaceholders && hasSections && resumeText.split('\n').length >= 6
    ? readiness('pass', 'Format', 'Contains resume sections and no obvious placeholders.')
    : hasPlaceholders
      ? readiness('fail', 'Format', 'Remove placeholder text before exporting.')
      : readiness('warn', 'Format', 'Section structure is not obvious; review formatting before exporting.');

  const metricMatches = resumeText.match(/\b(\d+[%+]|\$[\d,.]+|\d+x|\d+\s*(users|customers|requests|hours|days|weeks|months|years|people|teams))\b/gi) || [];
  const metricsCheck = metricMatches.length >= 2
    ? readiness('pass', 'Quantified impact', 'Includes ' + metricMatches.length + ' quantified proof points.')
    : metricMatches.length === 1
      ? readiness('warn', 'Quantified impact', 'Only one quantified result is visible; add more evidence if accurate.')
      : readiness('fail', 'Quantified impact', 'No quantified achievements detected.');

  const riskyClaims = resumeText.match(/\b(expert in everything|guaranteed|world-class|best-in-class|master of all|flawless)\b/gi) || [];
  const riskCheck = riskyClaims.length === 0
    ? readiness('pass', 'Risk statement', 'No obvious overclaiming markers detected.')
    : readiness('warn', 'Risk statement', 'Review potentially risky wording: ' + riskyClaims.slice(0, 3).join(', ') + '.');

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
    .map((entry) => entry[0]);
}

function skillKeywords(text) {
  const catalog = [
    'python', 'fastapi', 'django', 'flask', 'sql', 'postgres', 'postgresql',
    'mysql', 'redis', 'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'react',
    'typescript', 'javascript', 'node', 'etl', 'airflow', 'spark', 'api',
    'graphql', 'terraform', 'ci/cd', 'linux', 'machine learning',
  ];
  return catalog.filter((skill) => text.includes(skill));
}

function resumeActionsHtml(item) {
  if (!item.resume_id) return '<span style="color:var(--muted);font-size:0.8rem">Pending</span>';
  return '<div class="flex"><button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal(\'' + item.id + '\')">View</button>'
    + '<button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal(\'' + item.id + '\', true)">PDF</button></div>';
}

function renderTags(id, items) {
  document.getElementById(id).innerHTML = (items || []).map((t) => '<li>' + escHtml(t) + '</li>').join('');
}

function jsonOptions(method, payload) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}

function setEvalStatus(msg) { document.getElementById('eval-status').textContent = msg; }
function setEvalError(msg) { document.getElementById('eval-error').textContent = msg; }
function setEvalBtnDisabled(v) { document.getElementById('eval-btn').disabled = v; }
function hideResult() { document.getElementById('eval-result').style.display = 'none'; }

function fmtDate(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('zh-TW', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtStatus(s) {
  if (s === 'ready_to_submit') return 'Ready';
  if (s === 'needs_tailoring') return 'Tailoring';
  if (s === 'skip') return 'Skipped';
  return s || '-';
}

function escHtml(s) { return UI.escHtml(s); }
async function apiFetch(url, options) { return UI.apiFetch(url, options); }
function formatApiError(response, payload, options) { return UI.formatApiError(response, payload, options); }

document.getElementById('resume-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
