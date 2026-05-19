// Resume modal lifecycle, version selection, compare, edit, and PDF actions.
// Loaded after app.js; beautify/readiness helpers are provided by sibling feature scripts.

async function fetchAndOpenModal(jobId, showChecklist) {
  try {
    const { response: res, payload: body } = await apiFetch('/api/history/' + jobId);
    if (!res.ok) return;
    const job = body.data || {};
    const resumes = job.generated_resumes || [];
    currentResumeVersions = resumes;
    currentBaselineText = job.baseline_profile_text || '';
    currentJdText = job.jd_full_text || job.jd_snippet || currentJdText;
    if (resumes.length > 0) {
      const resume = resumes[0];
      currentResumeId = resume.id;
      currentResumeText = resume.resume_text;
      currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
      currentBeautifications = resume.beautifications || [];
    } else {
      currentResumeId = null;
      currentResumeText = currentBaselineText || '(no generated resume version yet)';
      currentResumePdfUrl = job.profile_id ? '/api/profiles/' + job.profile_id + '/pdf' : null;
      currentBeautifications = [];
    }
    openModal();
    if (showChecklist) showReadinessChecklist();
  } catch (_) {}
}

// ---- Modal ----
function openModal() {
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('download-resume-pdf').hidden = !currentResumePdfUrl;
  document.getElementById('beautify-open-btn').hidden = !currentResumeId;
  document.getElementById('edit-resume-btn').hidden = !currentResumeId;
  document.getElementById('copy-status').textContent = '';
  renderResumeVersions();
  renderResumeCompare(false);
  closeResumeEditor();
  hideReadinessChecklist();
  closeBeautifyPanel();
  document.getElementById('resume-modal').classList.add('open');
}

function closeModal() {
  document.getElementById('resume-modal').classList.remove('open');
}

async function copyResume() {
  if (!currentResumeText) return;
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(currentResumeText);
    status.textContent = 'Copied tailored resume.';
    status.className = 'status-msg modal-status readiness-pass';
  } catch (e) {
    status.textContent = 'Copy failed: ' + e.message;
    status.className = 'status-msg modal-status readiness-fail';
  }
}

function renderResumeVersions() {
  const el = document.getElementById('resume-versions');
  if (!el) return;
  if (!currentResumeVersions || currentResumeVersions.length === 0) {
    el.innerHTML = '<span class="status-msg">No tailored resume versions yet.</span>';
    return;
  }
  el.innerHTML = currentResumeVersions.map(function(resume, index) {
    const label = index === 0 ? 'Latest' : 'Version ' + (currentResumeVersions.length - index);
    const source = resume.revision_source === 'user_edited' ? 'User edit' : 'AI draft';
    const exported = resume.exported_at ? ' · exported' : '';
    const active = resume.id === currentResumeId ? ' active' : '';
    return '<button class="btn btn-sm btn-muted version-btn' + active + '" type="button" onclick="selectResumeVersion(\'' + resume.id + '\')">'
      + escHtml(label) + ' · ' + escHtml(source) + exported + ' · ' + fmtDate(resume.created_at)
      + '</button>';
  }).join('');
}

function selectResumeVersion(resumeId) {
  const resume = currentResumeVersions.find(item => item.id === resumeId);
  if (!resume) return;
  currentResumeId = resume.id;
  currentResumeText = resume.resume_text;
  currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
  currentBeautifications = resume.beautifications || [];
  document.getElementById('modal-resume-text').textContent = currentResumeText || '(no text)';
  document.getElementById('download-resume-pdf').hidden = !currentResumePdfUrl;
  document.getElementById('beautify-open-btn').hidden = !currentResumeId;
  document.getElementById('edit-resume-btn').hidden = !currentResumeId;
  closeResumeEditor();
  renderResumeVersions();
  renderResumeCompare(!document.getElementById('resume-compare').hidden);
  renderBeautifyHistory();
}

function toggleResumeCompare() {
  const panel = document.getElementById('resume-compare');
  renderResumeCompare(panel.hidden);
}

function renderResumeCompare(show) {
  const panel = document.getElementById('resume-compare');
  if (!panel) return;
  panel.hidden = !show;
  document.getElementById('compare-resume-btn').classList.toggle('active', show);
  if (!show) return;
  document.getElementById('baseline-resume-text').textContent = currentBaselineText || '(baseline profile text not available)';
  document.getElementById('tailored-resume-text').textContent = currentResumeText || '(no tailored resume selected)';
}

function toggleResumeEditor(force) {
  const panel = document.getElementById('resume-editor-panel');
  if (!panel || !currentResumeId) return;
  const show = typeof force === 'boolean' ? force : panel.hidden;
  panel.hidden = !show;
  document.getElementById('edit-resume-btn').classList.toggle('active', show);
  if (show) {
    document.getElementById('resume-editor-text').value = currentResumeText || '';
    document.getElementById('resume-editor-status').textContent = '';
  }
}

function closeResumeEditor() {
  const panel = document.getElementById('resume-editor-panel');
  if (panel) panel.hidden = true;
  const button = document.getElementById('edit-resume-btn');
  if (button) button.classList.remove('active');
}

async function saveResumeRevision() {
  if (!currentResumeId) return;
  const text = document.getElementById('resume-editor-text').value.trim();
  const status = document.getElementById('resume-editor-status');
  const button = document.getElementById('save-resume-revision');
  if (!text) {
    status.textContent = 'Draft text cannot be blank.';
    status.className = 'status-msg readiness-fail';
    return;
  }

  button.disabled = true;
  status.textContent = 'Saving revision...';
  status.className = 'status-msg';
  try {
    const { response: res, payload: body } = await apiFetch('/api/generated-resumes/' + currentResumeId + '/revisions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_text: text }),
    });
    if (!res.ok) {
      status.textContent = 'Save failed: ' + (body?.error?.message || ('HTTP ' + res.status));
      status.className = 'status-msg readiness-fail';
      return;
    }
    const revision = body.data;
    currentResumeVersions = [revision].concat(currentResumeVersions || []);
    currentResumeId = revision.id;
    currentResumeText = revision.resume_text;
    currentResumePdfUrl = revision.pdf_url || '/api/generated-resumes/' + revision.id + '/pdf';
    currentBeautifications = revision.beautifications || [];
    document.getElementById('modal-resume-text').textContent = currentResumeText;
    document.getElementById('download-resume-pdf').hidden = false;
    status.textContent = 'Revision saved. PDF export will use this draft.';
    status.className = 'status-msg readiness-pass';
    renderResumeVersions();
    renderResumeCompare(!document.getElementById('resume-compare').hidden);
    closeResumeEditor();
  } catch (e) {
    status.textContent = 'Network error: ' + e.message;
    status.className = 'status-msg readiness-fail';
  } finally {
    button.disabled = false;
  }
}

function downloadCurrentResumePdf() {
  if (!currentResumePdfUrl) return;
  showReadinessChecklist();
}

function confirmResumePdfDownload() {
  if (!currentResumePdfUrl) return;
  window.open(currentResumePdfUrl, '_blank', 'noopener');
}

document.getElementById('resume-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});
