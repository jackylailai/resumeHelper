const filters = document.getElementById("application-filters");
const body = document.getElementById("applications-body");
const trackerStatus = document.getElementById("tracker-status");
const resultCount = document.getElementById("result-count");
const prevPage = document.getElementById("prev-page");
const nextPage = document.getElementById("next-page");
const pageRange = document.getElementById("page-range");
const opportunitiesBody = document.getElementById("opportunities-body");
const opportunitiesStatus = document.getElementById("opportunities-status");
const refreshOpportunities = document.getElementById("refresh-opportunities");
const UI = window.ResumeHelper;

const PAGE_SIZE = 25;
const APPLICATION_STATUSES = [
    "planned",
    "applied",
    "interviewing",
    "rejected",
    "offer",
    "archived",
];
const pagination = {
    limit: PAGE_SIZE,
    offset: 0,
    total: 0,
};

filters.addEventListener("submit", async (event) => {
    event.preventDefault();
    pagination.offset = 0;
    await loadApplications();
});

prevPage.addEventListener("click", async () => {
    pagination.offset = Math.max(0, pagination.offset - pagination.limit);
    await loadApplications();
});

nextPage.addEventListener("click", async () => {
    const nextOffset = pagination.offset + pagination.limit;
    if (nextOffset < pagination.total) {
        pagination.offset = nextOffset;
        await loadApplications();
    }
});

refreshOpportunities.addEventListener("click", async () => {
    await loadOpportunities();
});

window.addEventListener("DOMContentLoaded", () => {
    loadOpportunities();
    loadApplications();
});

async function loadOpportunities() {
    opportunitiesStatus.textContent = "Loading...";
    opportunitiesBody.innerHTML = '<tr><td colspan="6" class="empty-row">Loading...</td></tr>';

    const { response, payload } = await UI.safeApiFetch("/api/job-opportunities");
    if (!response.ok) {
        opportunitiesStatus.textContent = UI.formatApiError(response, payload, {
            includeStatus: true,
        });
        opportunitiesBody.innerHTML = (
            '<tr><td colspan="6" class="empty-row">Could not load opportunities.</td></tr>'
        );
        return;
    }

    const opportunities = payload.data ?? [];
    opportunitiesStatus.textContent = `${opportunities.length} ready to review`;
    if (opportunities.length === 0) {
        opportunitiesBody.innerHTML = (
            '<tr><td colspan="6" class="empty-row">No high-fit untracked jobs right now.</td></tr>'
        );
        return;
    }

    opportunitiesBody.innerHTML = "";
    for (const opportunity of opportunities) {
        opportunitiesBody.appendChild(opportunityRow(opportunity));
    }
}

function opportunityRow(opportunity) {
    const row = document.createElement("tr");

    const company = document.createElement("td");
    company.textContent = opportunity.company || "Unknown";

    const title = document.createElement("td");
    title.textContent = `${opportunity.title || "Untitled"} (${opportunity.source})`;

    const score = document.createElement("td");
    score.textContent = opportunity.score == null ? "-" : `${opportunity.score}/100`;

    const status = document.createElement("td");
    status.textContent = statusLabel(opportunity.status);

    const links = document.createElement("td");
    const linkWrap = document.createElement("div");
    linkWrap.className = "selection-actions";
    const sourceLink = document.createElement("a");
    sourceLink.className = "button-link inline-button";
    sourceLink.href = opportunity.source_url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    sourceLink.textContent = "Apply";
    const detailLink = document.createElement("a");
    detailLink.className = "button-link inline-button";
    detailLink.href = opportunity.frontend_url;
    detailLink.textContent = "JD detail";
    linkWrap.append(sourceLink, detailLink);
    links.appendChild(linkWrap);

    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = opportunity.tracked ? "Tracked" : "Track";
    button.disabled = opportunity.tracked;
    button.addEventListener("click", () => trackOpportunity(opportunity, button));
    action.appendChild(button);

    row.append(company, title, score, status, links, action);
    return row;
}

async function trackOpportunity(opportunity, button) {
    button.disabled = true;
    button.textContent = "Tracking...";
    opportunitiesStatus.textContent = "Creating application...";
    const { response, payload } = await UI.safeApiFetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            job_listing_id: opportunity.job_listing_id,
            job_analysis_id: opportunity.job_analysis_id,
            generated_resume_id: opportunity.generated_resume_id,
            status: "planned",
        }),
    });
    if (!response.ok) {
        button.disabled = false;
        button.textContent = "Track";
        opportunitiesStatus.textContent = UI.formatApiError(response, payload, {
            includeStatus: true,
        });
        return;
    }
    opportunitiesStatus.textContent = payload.meta?.existing
        ? "Already tracked."
        : "Added to applications.";
    await loadOpportunities();
    await loadApplications();
}

async function loadApplications() {
    trackerStatus.textContent = "Loading...";
    body.innerHTML = '<tr><td colspan="6" class="empty-row">Loading...</td></tr>';

    const params = new URLSearchParams();
    const query = document.getElementById("q").value.trim();
    const status = document.getElementById("status").value;
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    params.set("sort_by", document.getElementById("sort-by").value);
    params.set("sort_dir", document.getElementById("sort-dir").value);
    params.set("limit", String(pagination.limit));
    params.set("offset", String(pagination.offset));

    const { response, payload } = await UI.safeApiFetch(`/api/applications?${params}`);
    if (!response.ok) {
        trackerStatus.textContent = UI.formatApiError(response, payload, {
            includeStatus: true,
        });
        body.innerHTML = (
            '<tr><td colspan="6" class="empty-row">Could not load applications.</td></tr>'
        );
        pagination.total = 0;
        updatePaginationControls({ rangeStart: 0, rangeEnd: 0 });
        return;
    }

    const applications = payload.data ?? [];
    pagination.total = payload.meta?.total ?? applications.length;
    pagination.limit = payload.meta?.limit ?? PAGE_SIZE;
    pagination.offset = payload.meta?.offset ?? pagination.offset;
    updatePaginationControls({
        rangeStart: payload.meta?.range_start ?? 0,
        rangeEnd: payload.meta?.range_end ?? 0,
    });

    if (applications.length === 0) {
        trackerStatus.textContent = "No applications found.";
        body.innerHTML = (
            '<tr><td colspan="6" class="empty-row">No tracked applications yet.</td></tr>'
        );
        return;
    }

    trackerStatus.textContent = "";
    body.innerHTML = "";
    for (const application of applications) {
        body.appendChild(applicationRow(application));
    }
}

function applicationRow(application) {
    const row = document.createElement("tr");

    const company = document.createElement("td");
    company.textContent = application.company || "Unknown";

    const title = document.createElement("td");
    if (application.source_url) {
        const link = document.createElement("a");
        link.href = application.source_url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = application.title || "Untitled";
        title.appendChild(link);
    } else {
        title.textContent = application.title || "Untitled";
    }

    const score = document.createElement("td");
    score.textContent = application.score == null ? "-" : `${application.score}/100`;

    const pdf = document.createElement("td");
    if (application.pdf_url) {
        const link = document.createElement("a");
        link.className = "button-link tracker-pdf-link";
        link.href = application.pdf_url;
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = "PDF";
        pdf.appendChild(link);
    } else {
        pdf.textContent = "-";
        pdf.className = "muted";
    }

    const status = document.createElement("td");
    const statusSelect = document.createElement("select");
    statusSelect.className = "compact-control";
    for (const value of APPLICATION_STATUSES) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = statusLabel(value);
        statusSelect.appendChild(option);
    }
    statusSelect.value = application.status;
    statusSelect.addEventListener("change", () => {
        updateApplication(application.id, { status: statusSelect.value });
    });
    status.appendChild(statusSelect);

    const followUp = document.createElement("td");
    const followUpInput = document.createElement("input");
    followUpInput.className = "compact-control";
    followUpInput.type = "date";
    followUpInput.value = application.follow_up_date || "";
    followUpInput.addEventListener("change", () => {
        updateApplication(application.id, {
            follow_up_date: followUpInput.value || null,
        });
    });
    followUp.appendChild(followUpInput);

    row.append(company, title, score, pdf, status, followUp);
    return row;
}

async function updateApplication(id, patch) {
    trackerStatus.textContent = "Saving...";
    const { response, payload } = await UI.safeApiFetch(`/api/applications/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
    });
    if (!response.ok) {
        trackerStatus.textContent = UI.formatApiError(response, payload, {
            includeStatus: true,
        });
        return;
    }
    trackerStatus.textContent = "Saved.";
}

function updatePaginationControls({ rangeStart, rangeEnd }) {
    resultCount.textContent = `${pagination.total} total`;
    pageRange.textContent = (
        pagination.total === 0 ? "0 of 0" : `${rangeStart}-${rangeEnd} of ${pagination.total}`
    );
    prevPage.disabled = pagination.offset <= 0;
    nextPage.disabled = pagination.offset + pagination.limit >= pagination.total;
}

function statusLabel(status) {
    if (status === "ready_to_submit") return "Ready";
    if (status === "needs_tailoring") return "Tailoring";
    if (status === "skip") return "Skipped";
    if (status === "planned") return "Planned";
    if (status === "applied") return "Applied";
    if (status === "interviewing") return "Interviewing";
    if (status === "rejected") return "Rejected";
    if (status === "offer") return "Offer";
    if (status === "archived") return "Archived";
    return status || "-";
}
