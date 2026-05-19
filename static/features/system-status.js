// System readiness panel for the home page.
// Loaded after app.js; uses global UI/apiFetch/escHtml helpers.

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
    return '<div class="health-action"><span>' + message + '</span><a class="btn btn-sm btn-muted" href="/scrapes.html">Run Scrapes</a></div>';
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
