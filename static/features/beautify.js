// Beautify panel + readiness checklist.
//
// Split out of app.js (#149). Loaded as a plain <script> AFTER app.js so the
// `var` state from app.js (currentResumeText, currentJdText, currentResumeId,
// currentBeautifications) is already on `window`. Helpers `escHtml`, `fmtDate`,
// and `apiFetch` are `function` declarations in app.js and are also global.

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

function showReadinessChecklist() {
  const panel = document.getElementById('readiness-panel');
  const summary = document.getElementById('readiness-summary');
  const list = document.getElementById('readiness-list');
  if (!panel || !summary || !list) return;

  const checks = buildReadinessChecks(currentResumeText || '', currentJdText || '');
  const failCount = checks.filter(c => c.status === 'fail').length;
  const warnCount = checks.filter(c => c.status === 'warn').length;
  summary.textContent = failCount > 0
    ? `${failCount} fail, ${warnCount} warn before download`
    : warnCount > 0
      ? `${warnCount} warnings before download`
      : 'Ready for PDF download';
  summary.className = 'readiness-summary ' + (
    failCount > 0 ? 'readiness-fail' : warnCount > 0 ? 'readiness-warn' : 'readiness-pass'
  );
  list.innerHTML = checks.map(function(check) {
    return '<li class="readiness-item readiness-' + check.status + '">'
      + '<span class="readiness-status">' + check.status.toUpperCase() + '</span>'
      + '<div><strong>' + escHtml(check.label) + '</strong><span>' + escHtml(check.message) + '</span></div>'
      + '</li>';
  }).join('');
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
  const matchedKeywords = jdKeywords.filter(word => resume.includes(word));
  const jdKeywordRatio = jdKeywords.length === 0 ? 0 : matchedKeywords.length / jdKeywords.length;
  const jdKeywordCheck = jdKeywords.length === 0
    ? readiness('warn', 'JD keywords', 'No full JD text is available, so keyword alignment cannot be verified.')
    : jdKeywordRatio >= 0.5
      ? readiness('pass', 'JD keywords', `Matches ${matchedKeywords.length}/${jdKeywords.length} important JD terms.`)
      : jdKeywordRatio >= 0.25
        ? readiness('warn', 'JD keywords', `Matches ${matchedKeywords.length}/${jdKeywords.length} important JD terms; add missing role keywords if they are truthful.`)
        : readiness('fail', 'JD keywords', `Only ${matchedKeywords.length}/${jdKeywords.length} important JD terms appear in the resume.`);

  const jdSkills = skillKeywords(jd);
  const matchedSkills = jdSkills.filter(skill => resume.includes(skill));
  const skillCheck = jdSkills.length === 0
    ? readiness('warn', 'Required skills', 'No recognizable must-have skills were found in the JD text.')
    : matchedSkills.length === jdSkills.length
      ? readiness('pass', 'Required skills', `Covers ${matchedSkills.length}/${jdSkills.length} detected JD skills.`)
      : matchedSkills.length > 0
        ? readiness('warn', 'Required skills', `Covers ${matchedSkills.length}/${jdSkills.length} detected JD skills; review the missing ones.`)
        : readiness('fail', 'Required skills', 'Detected JD skills are not visible in the tailored resume.');

  const wordCount = resumeWords.length;
  const lengthCheck = wordCount >= 250 && wordCount <= 900
    ? readiness('pass', 'Resume length', `${wordCount} words is within a recruiter-friendly range.`)
    : wordCount >= 150 && wordCount <= 1200
      ? readiness('warn', 'Resume length', `${wordCount} words may be acceptable, but review density before sending.`)
      : readiness('fail', 'Resume length', `${wordCount} words is outside the expected range for a focused resume.`);

  const hasPlaceholders = /\b(todo|tbd|lorem|placeholder|xxx)\b/i.test(resumeText);
  const hasSections = /\b(experience|skills|projects|education|summary)\b/i.test(resumeText);
  const formatCheck = !hasPlaceholders && hasSections && resumeText.split('\n').length >= 6
    ? readiness('pass', 'Format', 'Contains resume sections and no obvious placeholders.')
    : hasPlaceholders
      ? readiness('fail', 'Format', 'Remove placeholder text before exporting.')
      : readiness('warn', 'Format', 'Section structure is not obvious; review formatting before exporting.');

  const metricMatches = resumeText.match(/\b(\d+[%+]|\$[\d,.]+|\d+x|\d+\s*(users|customers|requests|hours|days|weeks|months|years|people|teams))\b/gi) || [];
  const metricsCheck = metricMatches.length >= 2
    ? readiness('pass', 'Quantified impact', `Includes ${metricMatches.length} quantified proof points.`)
    : metricMatches.length === 1
      ? readiness('warn', 'Quantified impact', 'Only one quantified result is visible; add more evidence if accurate.')
      : readiness('fail', 'Quantified impact', 'No quantified achievements detected.');

  const riskyClaims = resumeText.match(/\b(expert in everything|guaranteed|world-class|best-in-class|master of all|flawless)\b/gi) || [];
  const riskCheck = riskyClaims.length === 0
    ? readiness('pass', 'Risk statement', 'No obvious overclaiming markers detected.')
    : readiness('warn', 'Risk statement', `Review potentially risky wording: ${riskyClaims.slice(0, 3).join(', ')}.`);

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
    .map(entry => entry[0]);
}

function skillKeywords(text) {
  const catalog = [
    'python', 'fastapi', 'django', 'flask', 'sql', 'postgres', 'postgresql',
    'mysql', 'redis', 'aws', 'gcp', 'azure', 'docker', 'kubernetes', 'react',
    'typescript', 'javascript', 'node', 'etl', 'airflow', 'spark', 'api',
    'graphql', 'terraform', 'ci/cd', 'linux', 'machine learning',
  ];
  return catalog.filter(skill => text.includes(skill));
}
