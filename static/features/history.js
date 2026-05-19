// Evaluation history list.
// Loaded after app.js; fetchAndOpenModal is provided by resume-modal.js.

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
        html += '<div class="card" style="padding:0;overflow:hidden"><table><thead><tr><th>Score</th><th>JD Preview</th><th>Created</th><th>Submittable</th><th>Resume</th></tr></thead><tbody>';
        for (const item of items) {
          html += '<tr>'
            + '<td><span class="' + statusPillClass(item.status) + '">' + (item.score != null ? item.score : '—') + '</span></td>'
            + '<td><div class="jd-preview">' + escHtml(item.jd_snippet || '') + '</div></td>'
            + '<td style="font-size:0.8rem;color:var(--muted)">' + fmtDate(item.created_at) + '</td>'
            + '<td>' + (item.can_submit ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--muted)">—</span>') + '</td>'
            + '<td><button class="btn btn-sm btn-muted" onclick="fetchAndOpenModal(\'' + item.id + '\')">View</button></td>'
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
