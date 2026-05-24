const opportunitiesBody = document.getElementById("opportunities-body");
const opportunitiesStatus = document.getElementById("opportunities-status");
const refreshOpportunities = document.getElementById("refresh-opportunities");
const UI = window.ResumeHelper;

refreshOpportunities.addEventListener("click", async () => {
    await loadOpportunities();
});

window.addEventListener("DOMContentLoaded", () => {
    loadOpportunities();
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
    button.textContent = "Tracked";
    await loadOpportunities();
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
