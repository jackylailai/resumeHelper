// Profile CRUD, PDF upload, and structured extraction.
// Loaded after app.js; exposes functions used by inline handlers in index.html.

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
  const structuredEl = document.getElementById('edit-profile-structured');
  if (structuredEl) {
    structuredEl.value = profile.structured_data
      ? JSON.stringify(profile.structured_data, null, 2)
      : '';
  }
  document.getElementById('edit-profile-error').textContent = '';
  document.getElementById('edit-profile-success').textContent = '';
  const statusEl = document.getElementById('structured-status');
  if (statusEl) {
    statusEl.textContent = profile.structured_data
      ? 'Loaded existing structured_data — edit and Save, or click Extract to overwrite from skills_text.'
      : 'Tailor pulls dates / metrics / sections from this when present. Use "Extract from Skills" to auto-fill via LLM (~30s).';
    statusEl.className = 'status-msg';
  }
  document.getElementById('edit-profile-card').style.display = 'block';
}

async function saveStructured() {
  const id = document.getElementById('edit-profile-id').value;
  const raw = document.getElementById('edit-profile-structured').value.trim();
  const statusEl = document.getElementById('structured-status');
  if (!id) return;
  let payload;
  if (!raw) {
    payload = {};
  } else {
    try {
      payload = JSON.parse(raw);
    } catch (e) {
      statusEl.textContent = 'Invalid JSON: ' + e.message;
      statusEl.className = 'status-msg readiness-fail';
      return;
    }
  }
  statusEl.textContent = 'Saving...';
  statusEl.className = 'status-msg';
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id + '/structured', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      statusEl.textContent = 'Save failed: ' + (body?.error?.message || ('HTTP ' + res.status));
      statusEl.className = 'status-msg readiness-fail';
      return;
    }
    statusEl.textContent = 'Structured data saved.';
    statusEl.className = 'status-msg readiness-pass';
    await loadProfile();
  } catch (e) {
    statusEl.textContent = 'Network error: ' + e.message;
    statusEl.className = 'status-msg readiness-fail';
  }
}

async function extractStructured() {
  const id = document.getElementById('edit-profile-id').value;
  const btn = document.getElementById('extract-structured-btn');
  const statusEl = document.getElementById('structured-status');
  const taEl = document.getElementById('edit-profile-structured');
  if (!id) return;
  btn.disabled = true;
  statusEl.textContent = 'Extracting (LLM, ~30s)...';
  statusEl.className = 'status-msg readiness-warn';
  try {
    const { response: res, payload: body } = await apiFetch('/api/profiles/' + id + '/structured/extract', {
      method: 'POST',
    });
    if (!res.ok) {
      statusEl.textContent = 'Extract failed: ' + (body?.error?.message || ('HTTP ' + res.status));
      statusEl.className = 'status-msg readiness-fail';
      return;
    }
    const profile = body.data;
    taEl.value = JSON.stringify(profile.structured_data || {}, null, 2);
    statusEl.textContent = 'Extracted from skills_text. Review, then Save.';
    statusEl.className = 'status-msg readiness-pass';
    await loadProfile();
  } catch (e) {
    statusEl.textContent = 'Network error: ' + e.message;
    statusEl.className = 'status-msg readiness-fail';
  } finally {
    btn.disabled = false;
  }
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
