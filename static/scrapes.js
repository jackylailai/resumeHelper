const profileSelect = document.getElementById("profile-select");
const scrapeForm = document.getElementById("scrape-form");
const scrapeSource = document.getElementById("scrape-source");
const scrapeKeyword = document.getElementById("scrape-keyword");
const scrapeLimit = document.getElementById("scrape-limit");
const scrapeEvaluateAfter = document.getElementById("scrape-evaluate-after");
const scrapeMustContain = document.getElementById("scrape-must-contain");
const scrapeRegex = document.getElementById("scrape-regex");
const runScrapeButton = document.getElementById("run-scrape");
const replaceScrapeButton = document.getElementById("replace-scrape");
const stopScrapeButton = document.getElementById("stop-scrape");
const evaluatePendingButton = document.getElementById("evaluate-pending");
const refreshScrapeRuns = document.getElementById("refresh-scrape-runs");
const scrapeActiveSummary = document.getElementById("scrape-active-summary");
const scrapeStatus = document.getElementById("scrape-status");
const scrapeRuns = document.getElementById("scrape-runs");
const batchResults = document.getElementById("batch-results");
const UI = window.ResumeHelper;

let scrapeRefreshTimer = null;

scrapeRuns.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-copy-run-id]");
    if (!target) return;
    const full = target.getAttribute("data-copy-run-id");
    if (!full) return;
    const original = target.textContent;
    try {
        await navigator.clipboard.writeText(full);
        target.textContent = "Copied!";
    } catch {
        target.textContent = "Copy failed";
    }
    setTimeout(() => { target.textContent = original; }, 1200);
});

scrapeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runScrape(false);
});

replaceScrapeButton.addEventListener("click", async () => {
    await runScrape(true);
});

stopScrapeButton.addEventListener("click", async () => {
    await stopCurrentScrape();
});

evaluatePendingButton.addEventListener("click", async () => {
    await evaluatePendingListings();
});

refreshScrapeRuns.addEventListener("click", async () => {
    await loadScrapeRuns();
});

window.addEventListener("DOMContentLoaded", () => {
    loadProfiles();
    loadScrapeRuns();
});

async function runScrape(stopExisting) {
    const keyword = scrapeKeyword.value.trim();
    const limit = Number(scrapeLimit.value || 25);
    if (!keyword) {
        scrapeStatus.textContent = "Enter a keyword before scraping.";
        UI.toast.warning("Enter a keyword before scraping.");
        scrapeKeyword.focus();
        return;
    }

    setScrapeButtonsBusy(true);
    scrapeStatus.textContent = stopExisting
        ? "Stopping current scrape and queueing new keyword..."
        : "Queueing scrape schedule...";

    const requestBody = {
        source: scrapeSource.value,
        keyword,
        limit,
        evaluate_after_scrape: scrapeEvaluateAfter.checked,
        evaluate_limit: 100,
        stop_existing: stopExisting,
    };
    const profileId = profileSelect.value;
    if (profileId) requestBody.profile_id = Number(profileId);
    const mustContain = parseMustContain(scrapeMustContain?.value || "");
    if (mustContain.length > 0) {
        requestBody.must_contain = mustContain;
        requestBody.match_mode = getSelectedMatchMode();
        requestBody.regex = Boolean(scrapeRegex?.checked);
    }

    const { response, payload } = await safeApiFetch("/api/scrape/control/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
    });

    setScrapeButtonsBusy(false);
    if (!response.ok) {
        setApiError(scrapeStatus, response, payload);
        UI.toast.fromApiError(response, payload, { title: "Scrape failed to start" });
        if (payload?.error?.details) {
            renderScrapeControlStatus(payload.error.details);
        }
        return;
    }

    const runs = payload.data?.runs ?? [];
    scrapeStatus.textContent = `Queued ${runs.length} scrape run(s).`;
    UI.toast.success(`Queued ${runs.length} scrape run(s).`, { title: "Scrape started" });
    if (payload.meta?.active_status) {
        renderScrapeControlStatus(payload.meta.active_status);
    } else {
        renderScrapeRuns(runs);
    }
    scheduleScrapeStatusRefresh();
}

async function stopCurrentScrape() {
    setScrapeButtonsBusy(true);
    scrapeStatus.textContent = "Requesting scrape stop...";

    const { response, payload } = await safeApiFetch("/api/scrape/control/stop", {
        method: "POST",
    });

    setScrapeButtonsBusy(false);
    if (!response.ok) {
        setApiError(scrapeStatus, response, payload);
        return;
    }

    const cancelled = payload.meta?.cancelled_runs ?? [];
    scrapeStatus.textContent = cancelled.length
        ? `Stop requested for ${cancelled.length} scrape run(s).`
        : "No active scrape runs.";
    renderScrapeControlStatus(payload.data);
    scheduleScrapeStatusRefresh();
}

async function evaluatePendingListings() {
    evaluatePendingButton.disabled = true;
    scrapeStatus.textContent = "Evaluating pending listings...";
    batchResults.hidden = true;
    batchResults.innerHTML = "";

    const requestBody = { limit: 100 };
    const profileId = profileSelect.value;
    if (profileId) requestBody.profile_id = Number(profileId);
    if (!["all", "all_with_linkedin"].includes(scrapeSource.value)) {
        requestBody.source = scrapeSource.value;
    }

    const { response, payload } = await safeApiFetch("/api/evaluate/pending-listings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
    });

    evaluatePendingButton.disabled = false;
    if (!response.ok) {
        setApiError(scrapeStatus, response, payload);
        return;
    }

    const data = payload.data;
    scrapeStatus.textContent = (
        `Evaluated ${data.succeeded}/${data.total}; ${data.failed} failed; ` +
        `${data.skipped ?? 0} skipped; ${data.blocked ?? 0} blocked.`
    );
    renderBatchResults(data.results ?? []);
    await loadScrapeRuns();
}

async function loadScrapeRuns() {
    const { response, payload } = await safeApiFetch("/api/scrape/control");
    if (!response.ok) {
        setApiError(scrapeStatus, response, payload);
        return false;
    }
    renderScrapeControlStatus(payload.data);
    return Boolean(payload.data?.active);
}

function renderScrapeControlStatus(status) {
    const activeRuns = status?.active_runs ?? [];
    const recentRuns = status?.recent_runs ?? [];
    if (activeRuns.length > 0) {
        const keywords = [...new Set(activeRuns.map((run) => run.keyword))].join(", ");
        const sources = [...new Set(activeRuns.map((run) => run.source))].join(", ");
        scrapeActiveSummary.innerHTML = (
            `<strong>Running:</strong> ${esc(keywords)} `
            + `<span class="muted">(${esc(sources)})</span>`
        );
        stopScrapeButton.disabled = false;
    } else {
        scrapeActiveSummary.textContent = "No active scrape schedule.";
        stopScrapeButton.disabled = true;
    }
    renderScrapeRuns(recentRuns);
}

function renderScrapeRuns(runs) {
    if (!runs || runs.length === 0) {
        scrapeRuns.innerHTML = (
            '<div class="empty-row">'
            + 'No scrape runs yet.'
            + ' <button class="empty-cta" type="button" id="empty-run-first">Run your first scrape</button>'
            + '</div>'
        );
        document.getElementById("empty-run-first")?.addEventListener("click", () => {
            scrapeKeyword.focus();
        });
        return;
    }

    scrapeRuns.innerHTML = `
        <table class="scrape-run-table">
            <thead>
                <tr>
                    <th>Id</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Keyword</th>
                    <th>Stats</th>
                    <th>Started</th>
                    <th>Finished</th>
                    <th>Errors</th>
                </tr>
            </thead>
            <tbody>
                ${runs.map((run) => `
                    <tr>
                        <td>${renderRunId(run.id)}</td>
                        <td>${esc(run.source)}</td>
                        <td>
                            <span class="run-status run-${esc(run.status)}">
                                ${formatRunStatus(run.status)}
                            </span>
                            ${renderFilterHint(run)}
                        </td>
                        <td>${esc(run.keyword)}</td>
                        <td>${renderStatChips(run)}</td>
                        <td>${formatDate(run.started_at)}</td>
                        <td>${run.finished_at ? formatDate(run.finished_at) : "-"}</td>
                        <td>${run.error_summary ? esc(run.error_summary) : ""}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;
}

function renderRunId(runId) {
    if (!runId) return '<span class="muted">-</span>';
    const full = String(runId);
    const short = full.slice(0, 8);
    return (
        `<code class="run-id" data-copy-run-id="${esc(full)}" `
        + `title="${esc(full)} — click to copy">${esc(short)}</code>`
    );
}

function renderFilterHint(run) {
    if (run.status !== "succeeded") return "";
    const filtered = run.skipped_by_filter ?? 0;
    const kept = (run.inserted ?? 0) + (run.updated ?? 0);
    if (filtered <= 0 || kept > 0) return "";
    const label = `Filter rejected all ${filtered} candidate${filtered === 1 ? "" : "s"}`;
    return `<span class="run-filter-hint" title="${esc(label)}.">${esc(label.toLowerCase())}</span>`;
}

function renderStatChips(run) {
    const items = [
        { label: "inserted", value: run.inserted ?? 0, kind: "ok" },
        { label: "updated", value: run.updated ?? 0, kind: "neutral" },
        { label: "skipped", value: run.skipped ?? 0, kind: "neutral" },
        { label: "failed", value: run.failed ?? 0, kind: "warn" },
        { label: "filtered", value: run.skipped_by_filter ?? 0, kind: "neutral" },
    ];
    return items
        .map((item) => (
            `<span class="stat-chip stat-chip-${item.kind}" title="${item.label}">`
            + `<span class="stat-chip-label">${item.label}</span>`
            + `<span class="stat-chip-value">${item.value}</span>`
            + `</span>`
        ))
        .join("");
}

function renderBatchResults(results) {
    batchResults.hidden = false;
    const list = document.createElement("ol");
    list.className = "batch-result-list";

    const orderedResults = [...results].sort((left, right) => (
        Number(Boolean(right.error)) - Number(Boolean(left.error))
    ));
    for (const result of orderedResults) {
        const item = document.createElement("li");
        item.className = result.error ? "batch-result error" : "batch-result";
        const label = result.listing_id || "listing";
        if (result.error) {
            item.textContent = `${label}: ${result.error}`;
        } else {
            item.textContent = (
                `${label}: ${result.score}/100 ${formatStatus(result.status)}`
                + (result.cached ? " (cached)" : "")
            );
        }
        list.appendChild(item);
    }

    batchResults.innerHTML = "";
    batchResults.appendChild(list);
}

function scheduleScrapeStatusRefresh() {
    if (scrapeRefreshTimer) clearTimeout(scrapeRefreshTimer);
    let attempts = 0;
    const refresh = async () => {
        attempts += 1;
        const active = await loadScrapeRuns();
        if (active && attempts < 90) {
            scrapeRefreshTimer = setTimeout(refresh, 2000);
        }
    };
    scrapeRefreshTimer = setTimeout(refresh, 1000);
}

async function loadProfiles() {
    profileSelect.innerHTML = "";
    appendOption(profileSelect, "", "Loading profiles...");

    const { response, payload } = await safeApiFetch("/api/profiles");
    profileSelect.innerHTML = "";

    if (!response.ok) {
        appendOption(profileSelect, "", "Could not load profiles");
        setApiError(scrapeStatus, response, payload);
        return;
    }

    const profiles = payload.data ?? [];
    if (profiles.length === 0) {
        appendOption(profileSelect, "", "No profiles yet");
        return;
    }

    const defaultProfile = profiles.find((profile) => profile.is_default) || profiles[0];
    appendOption(
        profileSelect,
        "",
        `Default: ${defaultProfile.name || `Untitled #${defaultProfile.id}`}`,
    );
    for (const profile of profiles) {
        const label = (
            `${profile.name || `Untitled #${profile.id}`}`
            + (profile.is_default ? " (default)" : "")
        );
        appendOption(profileSelect, String(profile.id), label);
    }
}

function appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
}

function setScrapeButtonsBusy(isBusy) {
    runScrapeButton.disabled = isBusy;
    replaceScrapeButton.disabled = isBusy;
    stopScrapeButton.disabled = isBusy;
}

function formatRunStatus(status) {
    if (status === "succeeded") return "Succeeded";
    if (status === "partial") return "Partial";
    if (status === "failed") return "Failed";
    if (status === "cancel_requested") return "Stopping";
    if (status === "cancelled") return "Cancelled";
    if (status === "running") return "Running";
    return "Queued";
}

function formatStatus(status) {
    if (status === "ready_to_submit") return "Ready";
    if (status === "needs_tailoring") return "Tailoring";
    if (status === "skip") return "Skipped";
    if (status === "failed-invalid") return "Failed invalid";
    return status || "Analyzed";
}

function formatDate(value) {
    return value ? new Date(value).toLocaleString() : "-";
}

async function safeApiFetch(url, options) {
    return UI.safeApiFetch(url, options);
}

function setApiError(element, response, payload) {
    element.innerHTML = UI.apiErrorBanner(response, payload, { includeStatus: true });
}

function esc(value) {
    return UI.escHtml(value);
}

function parseMustContain(raw) {
    return raw
        .split(",")
        .map((term) => term.trim())
        .filter((term) => term.length > 0);
}

function getSelectedMatchMode() {
    const checked = document.querySelector('input[name="scrape_match_mode"]:checked');
    return checked?.value === "any" ? "any" : "all";
}
