// Submittable resume list.
// Loaded after app.js; fetchAndOpenModal is provided by resume-modal.js.

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
