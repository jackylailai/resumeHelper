// State
let currentResumeText = null;
let pollTimer = null;
let profileLoaded = false;

// ---- Init ----
window.addEventListener('DOMContentLoaded', () => {
  checkProfile();
});

// ---- Tab switching ----
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'history') loadHistory();
  if (name === 'submittable') loadSubmittable();
  if (name === 'profile') loadProfile();
}

// ---- Profile ----
async function checkProfile() {
  try {
    const res = await fetch('/api/profile');
    const body = await res.json();
    if (res.ok && body.data?.skills_text) {
      profileLoaded = true;
      setHeaderBadge(true);
      document.getElementById('no-profile-notice').style.display = 'none';
    } else {
      profileLoaded = false;
      setHeaderBadge(false);
      document.getElementById('no-profile-notice').style.display = 'block';
    }
  } catch (_) {}
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
  try {
    const res = await fetch('/api/profile');
    const body = await res.json();
    if (res.ok && body.data?.skills_text) {
      showProfilePreview(body.data.skills_text);
    }
  } catch (_) {}
}

function showProfilePreview(text) {
  document.getElementById('profile-input').value = text;
  document.getElementById('profile-preview-wrap').style.display = 'block';
}

async function uploadProfilePdf(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('profile-filename').textContent = file.name;
  document.getElementById('profile-error').textContent = '';
  document.getElementById('profile-success').textContent = '';
  document.getElementById('profile-upload-progress').style.display = 'flex';
  document.getElementById('profile-preview-wrap').style.display = 'none';
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/profile/upload', { method: 'POST', body: form });
    const body = await res.json();
    if (!res.ok) {
      document.getElementById('profile-error').textContent = body?.error?.message || 'Upload failed.';
      return;
    }
    document.getElementById('profile-success').textContent = 'Profile saved from PDF!';
    showProfilePreview(body.data.skills_text);
    profileLoaded = true;
    setHeaderBadge(true);
    document.getElementById('no-profile-notice').style.display = 'none';
  } catch (e) {
    document.getElementById('profile-error').textContent = 'Network error: ' + e.message;
  } finally {
    document.getElementById('profile-upload-progress').style.display = 'none';
    input.value = '';
  }
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
    const res = await fetch('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jd_text: jd }),
    });
    const body = await res.json();
    if (!res.ok) { setEvalError(body?.error?.message || res.statusText); return; }
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
  if (status === 'ready_to_submit') return 'badge-ready';
  if (status === 'needs_tailoring') return 'badge-tailoring';
  return 'badge-skip';
}

function statusPillClass(status) {
  if (status === 'ready_to_submit') return 'pill pill-ready';
  if (status === 'needs_tailoring') return 'pill pill-tailoring';
  return 'pill pill-skip';
}

// ---- Polling for tailoring ----
function startPoll(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/history/' + jobId);
      const body = await res.json();
      if (!res.ok) return;
      const job = body.data;
      if (job.can_submit && job.generated_resumes && job.generated_resumes.length > 0) {
        stopPoll();
        currentResumeText = job.generated_resumes[0].resume_text;
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
  el.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const res = await fetch('/api/history');
    const body = await res.json();
    if (!res.ok) { el.innerHTML = '<div class="empty">Error loading history.</div>'; return; }
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
    el.innerHTML = '<div class="empty">Network error.</div>';
  }
}

// ---- Submittable ----
async function loadSubmittable() {
  const tbody = document.getElementById('submittable-body');
  tbody.innerHTML = '<tr><td colspan="5" class="empty">Loading…</td></tr>';
  try {
    const res = await fetch('/api/submittable');
    const body = await res.json();
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
        + '<td>' + (item.resume_id
          ? '<button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal(\'' + item.id + '\')">View</button>'
          : '<span style="color:var(--muted);font-size:0.8rem">—</span>') + '</td>'
        + '</tr>';
    }).join('');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">Network error.</td></tr>';
  }
}

async function fetchAndOpenModal(jobId) {
  try {
    const res = await fetch('/api/history/' + jobId);
    const body = await res.json();
    const resumes = body.data?.generated_resumes;
    if (resumes && resumes.length > 0) {
      currentResumeText = resumes[0].resume_text;
      openModal();
    }
  } catch (_) {}
}

// ---- Modal ----
function openModal() {
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('resume-modal').classList.add('open');
}

function closeModal() {
  document.getElementById('resume-modal').classList.remove('open');
}

async function copyResume() {
  if (!currentResumeText) return;
  try { await navigator.clipboard.writeText(currentResumeText); } catch (_) {}
}

// ---- Helpers ----
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
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.getElementById('resume-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
