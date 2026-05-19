// Beautify panel.
// Loaded after app.js; readiness helpers are provided by readiness.js.

function openBeautifyPanel() {
  const panel = document.getElementById('beautify-panel');
  if (!panel) return;
  hideReadinessChecklist();
  renderBeautifyHistory();
  panel.hidden = false;
}

function closeBeautifyPanel() {
  const panel = document.getElementById('beautify-panel');
  if (panel) panel.hidden = true;
}

function renderBeautifyHistory() {
  const list = document.getElementById('beautify-history');
  if (!list) return;
  if (!currentBeautifications || currentBeautifications.length === 0) {
    list.innerHTML = '<li class="readiness-item readiness-warn"><span class="readiness-status">EMPTY</span><div><strong>No beautifications yet</strong><span>Click Run to generate a styled HTML + PDF from this tailored resume.</span></div></li>';
    return;
  }
  list.innerHTML = currentBeautifications.map(function(b) {
    return '<li class="readiness-item readiness-pass">'
      + '<span class="readiness-status">' + escHtml((b.style || 'modern').toUpperCase()) + '</span>'
      + '<div><strong>' + escHtml(b.prompt_version || 'beautify-v1') + ' · ' + fmtDate(b.created_at) + '</strong>'
      + '<span><a href="' + escHtml(b.html_url || '') + '" target="_blank" rel="noopener">Preview HTML</a> · '
      + '<a href="' + escHtml(b.pdf_url || '') + '" target="_blank" rel="noopener">Download PDF</a></span></div>'
      + '</li>';
  }).join('');
}

async function runBeautify() {
  if (!currentResumeId) return;
  const styleEl = document.getElementById('beautify-style');
  const runBtn = document.getElementById('beautify-run-btn');
  const statusEl = document.getElementById('beautify-status');
  const style = styleEl ? styleEl.value : 'modern';
  if (runBtn) runBtn.disabled = true;
  if (statusEl) {
    statusEl.textContent = 'Running beautify (~30-60s)...';
    statusEl.className = 'readiness-summary readiness-warn';
  }
  try {
    const { response: res, payload: body } = await apiFetch('/api/generated-resumes/' + currentResumeId + '/beautify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ style: style }),
    });
    if (!res.ok) {
      const msg = body?.error?.message || ('HTTP ' + res.status);
      if (statusEl) {
        statusEl.textContent = 'Beautify failed: ' + msg;
        statusEl.className = 'readiness-summary readiness-fail';
      }
      return;
    }
    const created = body.data;
    currentBeautifications = [created].concat(currentBeautifications);
    if (statusEl) {
      statusEl.textContent = 'Beautified — preview HTML or download PDF below.';
      statusEl.className = 'readiness-summary readiness-pass';
    }
    renderBeautifyHistory();
  } catch (e) {
    if (statusEl) {
      statusEl.textContent = 'Network error during beautify.';
      statusEl.className = 'readiness-summary readiness-fail';
    }
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}
