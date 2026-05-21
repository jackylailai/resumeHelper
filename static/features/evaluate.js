// Evaluate flow and tailoring polling.
// Loaded after app.js; uses shared global resume state from app.js.

const TAILORING_POLL_MS = 2000;

// ---- Evaluate ----
async function runEvaluate() {
  const jd = document.getElementById('jd-input').value.trim();
  if (!jd) { UI.toast.warning('Please paste a job description.'); return; }

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
    if (!res.ok) {
      setEvalApiError(res, body);
      UI.toast.fromApiError(res, body, { title: 'Evaluate failed' });
      return;
    }
    data = body.data;
    cached = body.meta?.cached === true;
  } catch (e) {
    setEvalError('Network error: ' + e.message);
    UI.toast.error('Network error: ' + e.message, { title: 'Evaluate failed' });
    return;
  } finally {
    setEvalBtnDisabled(false);
    setEvalStatus('');
  }

  renderEvalResult(data, cached);
  UI.toast.success(
    `Scored ${data.score}/100 — ${data.status}${cached ? ' (cached)' : ''}`,
    { title: 'Evaluate' },
  );

  if (data.status === 'needs_tailoring') {
    showTailoringSpinner(data.tailoring_status);
    if (data.tailoring_job_id) {
      startPoll(data.tailoring_job_id, data.job_analysis_id);
    } else {
      startPoll(data.job_analysis_id);
    }
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
  renderActionableGaps(data.gaps);
  renderResultActions(data);

  document.getElementById('tailoring-spinner').style.display = 'none';
  document.getElementById('tailoring-done').style.display = 'none';
  document.getElementById('eval-result').style.display = 'block';
}

function renderResultActions(data) {
  const el = document.getElementById('result-actions');
  if (!el) return;
  if (data.status === 'ready_to_submit') {
    el.innerHTML = '<div class="next-action next-ready">'
      + '<strong>Ready to submit</strong>'
      + '<span>This match is high enough to use the current resume as-is.</span>'
      + '<a class="btn btn-sm btn-green" href="#submittable" onclick="switchTab(\'submittable\')">Open Submittable</a>'
      + '</div>';
    return;
  }
  if (data.status === 'needs_tailoring') {
    const statusText = data.tailoring_status
      ? ' Current status: ' + escHtml(formatTailoringStatus(data.tailoring_status)) + '.'
      : '';
    const summary = data.tailoring_job_id
      ? 'Resume generation is running as a durable job. Review the gaps while it finishes.'
      : 'Review the gaps below while the tailored resume is generated.';
    el.innerHTML = '<div class="next-action next-tailoring">'
      + '<strong>Tailoring queued</strong>'
      + '<span>' + summary + statusText + '</span>'
      + '</div>';
    return;
  }
  el.innerHTML = '<div class="next-action next-skip">'
    + '<strong>Skip recommended</strong>'
    + '<span>The score is below the tailoring threshold. Keep it in history, or compare against a stronger profile later.</span>'
    + '<a class="btn btn-sm btn-muted" href="/jobs.html">Browse JD Database</a>'
    + '</div>';
}

function renderActionableGaps(items) {
  const ul = document.getElementById('result-gaps');
  const gaps = items || [];
  if (gaps.length === 0) {
    ul.innerHTML = '<li>No major gaps detected.</li>';
    return;
  }
  ul.innerHTML = gaps.map(function(gap) {
    return '<li><strong>' + escHtml(gap) + '</strong><span>Find truthful resume evidence, metrics, or project context before adding this.</span></li>';
  }).join('');
}

function statusBadgeClass(status) {
  return UI.statusBadgeClass(status);
}

function statusPillClass(status) {
  return UI.statusPillClass(status);
}

// ---- Polling for tailoring ----
function startPoll(tailoringJobId, jobAnalysisId) {
  stopPoll();
  if (jobAnalysisId) {
    pollTimer = setInterval(() => pollTailoringJob(tailoringJobId, jobAnalysisId), TAILORING_POLL_MS);
    pollTailoringJob(tailoringJobId, jobAnalysisId);
    return;
  }
  pollTimer = setInterval(() => pollTailoringHistory(tailoringJobId), TAILORING_POLL_MS);
  pollTailoringHistory(tailoringJobId);
}

async function pollTailoringJob(tailoringJobId, jobAnalysisId) {
  try {
    const { response: res, payload: body } = await apiFetch('/api/jobs/' + encodeURIComponent(tailoringJobId));
    if (!res.ok) return;

    const job = body.data || {};
    const status = job.status || job.tailoring_status || '';
    updateTailoringProgress(job);

    if (status === 'succeeded') {
      const resolvedAnalysisId = jobAnalysisId || job.job_analysis_id || job.result_payload?.job_analysis_id;
      if (resolvedAnalysisId && await loadTailoredResumeFromHistory(resolvedAnalysisId)) {
        stopPoll();
      }
      return;
    }

    if (status === 'failed' || status === 'cancelled') {
      stopPoll();
      showTailoringFailure(job);
    }
  } catch (_) {}
}

async function pollTailoringHistory(jobAnalysisId) {
  try {
    if (await loadTailoredResumeFromHistory(jobAnalysisId)) {
      stopPoll();
    }
  } catch (_) {}
}

async function loadTailoredResumeFromHistory(jobAnalysisId) {
  const { response: res, payload: body } = await apiFetch('/api/history/' + encodeURIComponent(jobAnalysisId));
  if (!res.ok) return false;
  return applyTailoringHistory(body.data || {});
}

function applyTailoringHistory(job) {
  const tailoringStatus = job.tailoring_status || '';
  if (tailoringStatus === 'failed' || tailoringStatus === 'cancelled') {
    showTailoringFailure(job);
    return true;
  }

  if (!(job.can_submit && job.generated_resumes && job.generated_resumes.length > 0)) {
    updateTailoringProgress(job);
    return false;
  }

  const resume = job.generated_resumes[0];
  currentResumeVersions = job.generated_resumes || [];
  currentBaselineText = job.baseline_profile_text || null;
  currentResumeId = resume.id;
  currentResumeText = resume.resume_text;
  currentResumePdfUrl = resume.pdf_url || '/api/generated-resumes/' + resume.id + '/pdf';
  currentBeautifications = resume.beautifications || [];
  currentJdText = job.jd_full_text || currentJdText;
  document.getElementById('tailoring-spinner').style.display = 'none';
  document.getElementById('tailoring-done').style.display = 'flex';
  return true;
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function showTailoringSpinner(status) {
  document.getElementById('tailoring-spinner').style.display = 'flex';
  document.getElementById('tailoring-done').style.display = 'none';
  updateTailoringProgress({ status: status || 'queued' });
}

function updateTailoringProgress(job) {
  const spinner = document.getElementById('tailoring-spinner');
  if (!spinner) return;
  const label = spinner.querySelector('span:last-child');
  if (!label) return;

  const status = formatTailoringStatus(job.status || job.tailoring_status || 'running');
  const progress = formatTailoringProgress(job);
  label.textContent = 'Tailoring ' + status + (progress ? ' - ' + progress : '') + ' - polling every 2s...';
}

function formatTailoringProgress(job) {
  if (job.progress_message) return job.progress_message;
  if (job.progress_percent != null) return String(job.progress_percent) + '%';
  if (job.progress_current != null && job.progress_total != null) {
    return String(job.progress_current) + '/' + String(job.progress_total);
  }
  return '';
}

function formatTailoringStatus(status) {
  if (status === 'queued') return 'queued';
  if (status === 'running') return 'in progress';
  if (status === 'succeeded') return 'succeeded';
  if (status === 'failed') return 'failed';
  if (status === 'cancelled') return 'cancelled';
  return status || 'in progress';
}

function showTailoringFailure(job) {
  const status = job.status || job.tailoring_status || 'failed';
  const isCancelled = status === 'cancelled';
  const title = isCancelled ? 'Tailoring cancelled' : 'Tailoring failed';
  const message = job.error_message || job.message || (
    isCancelled
      ? 'Resume tailoring was cancelled before a draft was generated.'
      : 'Resume tailoring did not finish. Check the job status or try evaluating again.'
  );
  const code = job.error_code ? ' (' + job.error_code + ')' : '';

  document.getElementById('tailoring-spinner').style.display = 'none';
  document.getElementById('tailoring-done').style.display = 'none';

  const el = document.getElementById('result-actions');
  if (el) {
    el.innerHTML = '<div class="next-action next-skip">'
      + '<strong>' + escHtml(title) + '</strong>'
      + '<span>' + escHtml(message + code) + '</span>'
      + '</div>';
  }

  if (isCancelled) {
    UI.toast.warning(message, { title });
  } else {
    UI.toast.error(message, { title });
  }
}
