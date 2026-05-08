const filters = document.getElementById("filters");
const jobList = document.getElementById("job-list");
const listStatus = document.getElementById("list-status");
const resultCount = document.getElementById("result-count");
const detailEmpty = document.getElementById("detail-empty");
const detail = document.getElementById("detail");
const profileSelect = document.getElementById("profile-select");
const scoreSelected = document.getElementById("score-selected");
const batchStatus = document.getElementById("batch-status");
const batchResults = document.getElementById("batch-results");
const pasteJd = document.getElementById("paste-jd");
const scorePasted = document.getElementById("score-pasted");
const pasteStatus = document.getElementById("paste-status");
const pasteResult = document.getElementById("paste-result");

let selectedListingId = null;
let currentListings = [];

filters.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadListings();
});

scoreSelected.addEventListener("click", async () => {
    await scoreSelectedListings();
});

scorePasted.addEventListener("click", async () => {
    await scorePastedJd();
});

window.addEventListener("DOMContentLoaded", () => {
    loadProfiles();
    loadListings();
});

async function loadProfiles() {
    profileSelect.innerHTML = "";
    appendOption(profileSelect, "", "Loading profiles...");

    const { response, payload } = await safeApiFetch("/api/profiles");
    profileSelect.innerHTML = "";

    if (!response.ok) {
        appendOption(profileSelect, "", "Could not load profiles");
        batchStatus.textContent = formatError(response, payload);
        return;
    }

    const profiles = payload.data ?? [];
    if (profiles.length === 0) {
        appendOption(profileSelect, "", "No profiles yet");
        return;
    }

    for (const profile of profiles) {
        const label = profile.name || `Untitled #${profile.id}`;
        appendOption(profileSelect, String(profile.id), label);
    }
}

function appendOption(select, value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
}

async function loadListings() {
    listStatus.textContent = "Loading...";
    jobList.innerHTML = "";
    resultCount.textContent = "";

    const params = new URLSearchParams();
    for (const field of ["q", "source", "analyzed"]) {
        const value = document.getElementById(field).value.trim();
        if (value) params.set(field, value);
    }
    params.set("limit", "50");

    const { response, payload } = await safeApiFetch(`/api/job-listings?${params}`);
    if (!response.ok) {
        listStatus.textContent = formatError(response, payload);
        return;
    }

    const listings = payload.data ?? [];
    currentListings = listings;
    resultCount.textContent = `${payload.meta?.total ?? listings.length} total`;

    if (listings.length === 0) {
        listStatus.textContent = "No job listings found.";
        return;
    }

    listStatus.textContent = "";
    for (const listing of listings) {
        const item = document.createElement("li");
        item.className = "job-list-item";

        const label = document.createElement("label");
        label.className = "job-select";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = listing.id;
        checkbox.dataset.selectListing = listing.id;
        checkbox.disabled = !listing.has_description;
        checkbox.setAttribute("aria-label", `Select ${listing.title}`);
        label.appendChild(checkbox);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "job-row";
        button.dataset.id = listing.id;
        button.innerHTML = `
            <span class="job-row-title"></span>
            <span class="job-row-meta"></span>
            <span class="job-row-preview"></span>
        `;
        button.querySelector(".job-row-title").textContent = listing.title;
        button.querySelector(".job-row-meta").textContent = [
            listing.company,
            listing.source,
            listing.location,
            listingStatusText(listing),
        ].filter(Boolean).join(" - ");
        button.querySelector(".job-row-preview").textContent = (
            listing.description_preview || "No JD text"
        );
        button.classList.toggle("selected", selectedListingId === listing.id);
        button.addEventListener("click", () => loadDetail(listing.id));

        item.appendChild(label);
        item.appendChild(button);
        jobList.appendChild(item);
    }
}

async function scoreSelectedListings() {
    const ids = Array.from(
        document.querySelectorAll("[data-select-listing]:checked")
    ).map((input) => input.value);
    const profileId = profileSelect.value;

    batchResults.hidden = true;
    batchResults.innerHTML = "";

    if (!profileId) {
        batchStatus.textContent = "Choose a profile first.";
        return;
    }
    if (ids.length === 0) {
        batchStatus.textContent = "Select at least one listing.";
        return;
    }

    scoreSelected.disabled = true;
    batchStatus.textContent = "Scoring selected listings...";

    const { response, payload } = await safeApiFetch("/api/evaluate/by-listings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            profile_id: Number(profileId),
            job_listing_ids: ids,
        }),
    });

    scoreSelected.disabled = false;
    if (!response.ok) {
        batchStatus.textContent = formatError(response, payload);
        return;
    }

    const data = payload.data;
    batchStatus.textContent = (
        `Scored ${data.succeeded}/${data.total}; ${data.failed} failed.`
    );
    renderBatchResults(data.results ?? []);
    await loadListings();
    if (selectedListingId) {
        await loadDetail(selectedListingId);
    }
}

function renderBatchResults(results) {
    batchResults.hidden = false;
    const list = document.createElement("ol");
    list.className = "batch-result-list";

    for (const result of results) {
        const item = document.createElement("li");
        item.className = result.error ? "batch-result error" : "batch-result";
        const label = listingLabel(result.listing_id);
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

async function scorePastedJd() {
    const profileId = profileSelect.value;
    const jdText = pasteJd.value.trim();

    pasteResult.hidden = true;
    pasteResult.innerHTML = "";

    if (!profileId) {
        pasteStatus.textContent = "Choose a profile first.";
        return;
    }
    if (!jdText) {
        pasteStatus.textContent = "Paste a job description first.";
        return;
    }

    scorePasted.disabled = true;
    pasteStatus.textContent = "Scoring pasted JD...";

    const { response, payload } = await safeApiFetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            profile_id: Number(profileId),
            jd_text: jdText,
        }),
    });

    scorePasted.disabled = false;
    if (!response.ok) {
        pasteStatus.textContent = formatError(response, payload);
        return;
    }

    pasteStatus.textContent = "Scored pasted JD.";
    renderPastedResult(payload.data, payload.meta?.cached === true);
}

function renderPastedResult(result, cached) {
    pasteResult.hidden = false;
    pasteResult.innerHTML = "";

    const score = document.createElement("div");
    score.className = "result-score";
    score.textContent = (
        `${result.score}/100 ${formatStatus(result.status)}`
        + (cached ? " (cached)" : "")
    );

    const message = document.createElement("p");
    message.className = "muted";
    message.textContent = result.message || result.explanation || "";

    pasteResult.appendChild(score);
    pasteResult.appendChild(message);
}

function listingLabel(id) {
    const listing = currentListings.find((item) => item.id === id);
    if (!listing) return id;
    return `${listing.title} - ${listing.company}`;
}

async function loadDetail(id) {
    selectedListingId = id;
    for (const row of document.querySelectorAll(".job-row")) {
        row.classList.toggle("selected", row.dataset.id === id);
    }

    const { response, payload } = await safeApiFetch(`/api/job-listings/${id}`);
    if (!response.ok) {
        detailEmpty.hidden = false;
        detail.hidden = true;
        detailEmpty.textContent = formatError(response, payload);
        return;
    }

    const listing = payload.data;
    detailEmpty.hidden = true;
    detail.hidden = false;

    document.getElementById("detail-source").textContent = (
        `${listing.source} / ${listing.source_id}`
    );
    document.getElementById("detail-title").textContent = listing.title;
    document.getElementById("detail-company").textContent = listing.company;
    document.getElementById("detail-location").textContent = (
        listing.location || "Not provided"
    );
    document.getElementById("detail-scraped").textContent = (
        new Date(listing.scraped_at).toLocaleString()
    );
    document.getElementById("detail-status").textContent = listingStatusText(listing);
    document.getElementById("detail-description").textContent = (
        listing.description || "No JD text"
    );

    const link = document.getElementById("detail-url");
    link.href = listing.url;
    link.hidden = !listing.url;
}

function listingStatusText(listing) {
    if (!listing.analyzed) return "Unanalyzed";
    if (listing.last_score == null) return "Analyzed";
    return `${listing.last_score}/100 ${formatStatus(listing.last_status)}`;
}

function formatStatus(status) {
    if (status === "ready_to_submit") return "Ready";
    if (status === "needs_tailoring") return "Tailoring";
    if (status === "skip") return "Skipped";
    return status || "Analyzed";
}

async function apiFetch(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = {};

    if (text) {
        try {
            payload = JSON.parse(text);
        } catch {
            payload = {
                error: {
                    code: "non_json_response",
                    message: text.slice(0, 160),
                    details: {},
                },
                meta: {},
            };
        }
    }

    return { response, payload };
}

async function safeApiFetch(url, options) {
    try {
        return await apiFetch(url, options);
    } catch (error) {
        return {
            response: {
                ok: false,
                status: 0,
                statusText: "Network error",
                headers: new Headers(),
            },
            payload: {
                error: {
                    code: "network_error",
                    message: error instanceof Error ? error.message : "Network error",
                    details: {},
                },
                meta: {},
            },
        };
    }
}

function formatError(response, payload) {
    const message = payload.error?.message ?? response.statusText ?? "Request failed";
    const requestId = payload.meta?.request_id ?? response.headers.get("X-Request-ID");
    const suffix = requestId ? ` Request ID: ${requestId}` : "";
    return `Error ${response.status}: ${message}.${suffix}`;
}
