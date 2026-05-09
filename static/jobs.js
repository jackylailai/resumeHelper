const filters = document.getElementById("filters");
const jobList = document.getElementById("job-list");
const listStatus = document.getElementById("list-status");
const resultCount = document.getElementById("result-count");
const detailEmpty = document.getElementById("detail-empty");
const detail = document.getElementById("detail");
const profileSelect = document.getElementById("profile-select");
const selectPage = document.getElementById("select-page");
const clearSelection = document.getElementById("clear-selection");
const selectionCount = document.getElementById("selection-count");
const scoreSelected = document.getElementById("score-selected");
const batchStatus = document.getElementById("batch-status");
const batchResults = document.getElementById("batch-results");
const pasteJd = document.getElementById("paste-jd");
const scorePasted = document.getElementById("score-pasted");
const pasteStatus = document.getElementById("paste-status");
const pasteResult = document.getElementById("paste-result");
const trackListing = document.getElementById("track-listing");
const trackStatus = document.getElementById("track-status");
const prevPage = document.getElementById("prev-page");
const nextPage = document.getElementById("next-page");
const pageRange = document.getElementById("page-range");
const UI = window.ResumeHelper;

const PAGE_SIZE = 20;
let selectedListingId = null;
let currentListings = [];
let selectedListingIds = new Set();
let failedBatchListingIds = new Set();
const listingLabelsById = new Map();
const pagination = {
    limit: PAGE_SIZE,
    offset: 0,
    total: 0,
};

filters.addEventListener("submit", async (event) => {
    event.preventDefault();
    pagination.offset = 0;
    await loadListings();
});

selectPage.addEventListener("click", () => {
    selectCurrentPage();
});

clearSelection.addEventListener("click", () => {
    clearSelectedListings();
});

scoreSelected.addEventListener("click", async () => {
    await scoreSelectedListings();
});

scorePasted.addEventListener("click", async () => {
    await scorePastedJd();
});

trackListing.addEventListener("click", async () => {
    await addSelectedListingToTracker();
});

prevPage.addEventListener("click", async () => {
    pagination.offset = Math.max(0, pagination.offset - pagination.limit);
    await loadListings();
});

nextPage.addEventListener("click", async () => {
    const nextOffset = pagination.offset + pagination.limit;
    if (nextOffset < pagination.total) {
        pagination.offset = nextOffset;
        await loadListings();
    }
});

window.addEventListener("DOMContentLoaded", () => {
    loadProfiles();
    loadListings();
    updateSelectionControls();
    updatePaginationControls({ rangeStart: 0, rangeEnd: 0 });
});

async function loadProfiles() {
    profileSelect.innerHTML = "";
    appendOption(profileSelect, "", "Loading profiles...");

    const { response, payload } = await safeApiFetch("/api/profiles");
    profileSelect.innerHTML = "";

    if (!response.ok) {
        appendOption(profileSelect, "", "Could not load profiles");
        setApiError(batchStatus, response, payload);
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
    for (const field of ["q", "source", "status"]) {
        const value = document.getElementById(field).value.trim();
        if (value) params.set(field, value);
    }
    params.set("sort_by", document.getElementById("sort-by").value);
    params.set("sort_dir", document.getElementById("sort-dir").value);
    params.set("limit", String(pagination.limit));
    params.set("offset", String(pagination.offset));

    const { response, payload } = await safeApiFetch(`/api/job-listings?${params}`);
    if (!response.ok) {
        setApiError(listStatus, response, payload);
        currentListings = [];
        pagination.total = 0;
        updatePaginationControls({ rangeStart: 0, rangeEnd: 0 });
        updateSelectionControls();
        return;
    }

    const listings = payload.data ?? [];
    currentListings = listings;
    pagination.total = payload.meta?.total ?? listings.length;
    pagination.limit = payload.meta?.limit ?? PAGE_SIZE;
    pagination.offset = payload.meta?.offset ?? pagination.offset;
    updateListingLabels(listings);
    updatePaginationControls({
        rangeStart: payload.meta?.range_start ?? 0,
        rangeEnd: payload.meta?.range_end ?? 0,
    });

    if (listings.length === 0) {
        listStatus.textContent = "No job listings found.";
        updateSelectionControls();
        return;
    }

    listStatus.textContent = "";
    for (const listing of listings) {
        const item = document.createElement("li");
        item.className = "job-list-item";
        item.dataset.listingId = listing.id;
        item.classList.toggle("batch-failed", failedBatchListingIds.has(listing.id));

        const label = document.createElement("label");
        label.className = "job-select";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = listing.id;
        checkbox.dataset.selectListing = listing.id;
        checkbox.disabled = !listing.has_description;
        checkbox.checked = selectedListingIds.has(listing.id);
        checkbox.setAttribute("aria-label", `Select ${listing.title}`);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) {
                selectedListingIds.add(listing.id);
                listingLabelsById.set(listing.id, listingLabelText(listing));
            } else {
                selectedListingIds.delete(listing.id);
            }
            updateSelectionControls();
        });
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
    updateSelectionControls();
}

function updateListingLabels(listings) {
    for (const listing of listings) {
        listingLabelsById.set(listing.id, listingLabelText(listing));
    }
}

function updatePaginationControls({ rangeStart, rangeEnd }) {
    resultCount.textContent = `${pagination.total} total`;
    if (pagination.total === 0) {
        pageRange.textContent = "0 of 0";
    } else {
        pageRange.textContent = `${rangeStart}-${rangeEnd} of ${pagination.total}`;
    }
    prevPage.disabled = pagination.offset <= 0;
    nextPage.disabled = pagination.offset + pagination.limit >= pagination.total;
}

function selectCurrentPage() {
    for (const listing of currentListings) {
        if (listing.has_description) {
            selectedListingIds.add(listing.id);
            listingLabelsById.set(listing.id, listingLabelText(listing));
        }
    }
    for (const checkbox of document.querySelectorAll("[data-select-listing]")) {
        checkbox.checked = !checkbox.disabled;
    }
    updateSelectionControls();
}

function clearSelectedListings() {
    selectedListingIds = new Set();
    for (const checkbox of document.querySelectorAll("[data-select-listing]")) {
        checkbox.checked = false;
    }
    updateSelectionControls();
}

function updateSelectionControls() {
    const count = selectedListingIds.size;
    selectionCount.textContent = `${count} selected`;
    clearSelection.disabled = count === 0;
    selectPage.disabled = currentListings.every((listing) => !listing.has_description);
}

async function scoreSelectedListings() {
    const ids = Array.from(selectedListingIds);
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
    if (ids.length > 20) {
        batchStatus.textContent = "Score up to 20 listings at a time.";
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
        setApiError(batchStatus, response, payload);
        return;
    }

    const data = payload.data;
    batchStatus.textContent = (
        `Scored ${data.succeeded}/${data.total}; ${data.failed} failed.`
    );
    renderBatchResults(data.results ?? []);
    for (const result of data.results ?? []) {
        if (!result.error) {
            selectedListingIds.delete(result.listing_id);
        }
    }
    await loadListings();
    if (selectedListingId) {
        await loadDetail(selectedListingId);
    }
}

function renderBatchResults(results) {
    batchResults.hidden = false;
    failedBatchListingIds = new Set(
        results.filter((result) => result.error).map((result) => result.listing_id)
    );
    const list = document.createElement("ol");
    list.className = "batch-result-list";

    const orderedResults = [...results].sort((left, right) => (
        Number(Boolean(right.error)) - Number(Boolean(left.error))
    ));
    for (const result of orderedResults) {
        const item = document.createElement("li");
        item.className = result.error ? "batch-result error" : "batch-result";
        const label = listingLabel(result.listing_id);
        if (result.error) {
            const message = document.createElement("span");
            message.textContent = `${label}: ${result.error}`;
            const openButton = document.createElement("button");
            openButton.type = "button";
            openButton.className = "inline-button";
            openButton.textContent = "View";
            openButton.addEventListener("click", () => {
                loadDetail(result.listing_id);
            });
            item.appendChild(message);
            item.appendChild(openButton);
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
        setApiError(pasteStatus, response, payload);
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
    return listingLabelsById.get(id) || id;
}

function listingLabelText(listing) {
    return `${listing.title} - ${listing.company} (${listing.source})`;
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
        setApiError(detailEmpty, response, payload);
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
    trackStatus.textContent = "";
    trackListing.disabled = false;
}

async function addSelectedListingToTracker() {
    if (!selectedListingId) return;

    trackListing.disabled = true;
    trackStatus.textContent = "Adding to tracker...";
    const { response, payload } = await safeApiFetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            job_listing_id: selectedListingId,
            status: "planned",
        }),
    });

    if (!response.ok) {
        trackStatus.textContent = formatError(response, payload);
        trackListing.disabled = false;
        return;
    }

    trackStatus.textContent = payload.meta?.existing
        ? "Already tracked; tracker entry updated."
        : "Added to tracker.";
    trackListing.disabled = false;
}

function listingStatusText(listing) {
    if (listing.list_status === "failed-invalid") return "Failed invalid";
    if (listing.list_status === "unanalyzed" || !listing.analyzed) return "Unanalyzed";
    if (listing.last_score == null) return "Analyzed";
    return `${listing.last_score}/100 ${formatStatus(listing.last_status)}`;
}

function formatStatus(status) {
    if (status === "ready_to_submit") return "Ready";
    if (status === "needs_tailoring") return "Tailoring";
    if (status === "skip") return "Skipped";
    if (status === "failed-invalid") return "Failed invalid";
    return status || "Analyzed";
}

async function safeApiFetch(url, options) {
    return UI.safeApiFetch(url, options);
}

function formatError(response, payload) {
    return UI.formatApiError(response, payload, { includeStatus: true });
}

function setApiError(element, response, payload) {
    element.innerHTML = UI.apiErrorBanner(response, payload, { includeStatus: true });
}
