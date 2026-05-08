const filters = document.getElementById("filters");
const jobList = document.getElementById("job-list");
const listStatus = document.getElementById("list-status");
const resultCount = document.getElementById("result-count");
const detailEmpty = document.getElementById("detail-empty");
const detail = document.getElementById("detail");

filters.addEventListener("submit", async (event) => {
    event.preventDefault();
    await loadListings();
});

window.addEventListener("DOMContentLoaded", () => {
    loadListings();
});

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
    resultCount.textContent = `${payload.meta?.total ?? listings.length} total`;

    if (listings.length === 0) {
        listStatus.textContent = "No job listings found.";
        return;
    }

    listStatus.textContent = "";
    for (const listing of listings) {
        const item = document.createElement("li");
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
            listing.analyzed ? "Analyzed" : "Unanalyzed",
        ].filter(Boolean).join(" - ");
        button.querySelector(".job-row-preview").textContent = (
            listing.description_preview || "No JD text"
        );
        button.addEventListener("click", () => loadDetail(listing.id));
        item.appendChild(button);
        jobList.appendChild(item);
    }
}

async function loadDetail(id) {
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
    document.getElementById("detail-status").textContent = (
        listing.analyzed ? "Analyzed" : "Unanalyzed"
    );
    document.getElementById("detail-description").textContent = (
        listing.description || "No JD text"
    );

    const link = document.getElementById("detail-url");
    link.href = listing.url;
    link.hidden = !listing.url;
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
