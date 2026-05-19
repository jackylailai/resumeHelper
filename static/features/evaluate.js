// Evaluate flow and tailoring polling.
// Loaded after app.js; uses shared global resume state from app.js.

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
    el.innerHTML = '<div class="next-action next-tailoring">'
      + '<strong>Tailoring queued</strong>'
      + '<span>Review the gaps below while the tailored resume is generated.</span>'
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
function startPoll(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const { response: res, payload: body } = await apiFetch('/api/history/' + jobId);
      if (!res.ok) return;
      const job = body.data;
      if (job.can_submit && job.generated_resumes && job.generated_resumes.length > 0) {
        stopPoll();
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
