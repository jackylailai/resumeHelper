(function () {
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

    function requestId(response, payload) {
        return payload?.meta?.request_id || response.headers.get("X-Request-ID");
    }

    function formatApiError(response, payload, options = {}) {
        const message = payload?.error?.message || response.statusText || "Request failed";
        const id = requestId(response, payload);
        const suffix = id ? ` Request ID: ${id}` : "";
        const prefix = options.includeStatus ? `Error ${response.status}: ` : "";
        return `${prefix}${message}.${suffix}`;
    }

    function apiErrorBanner(response, payload, options = {}) {
        const message = payload?.error?.message || response.statusText || "Request failed";
        const id = requestId(response, payload);
        const prefix = options.includeStatus ? `Error ${response.status}: ` : "";
        return errorBanner(`${prefix}${message}.`, id);
    }

    function escHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function emptyState(message, extraClass = "") {
        const cls = extraClass ? `empty ${extraClass}` : "empty";
        return `<div class="${cls}">${escHtml(message)}</div>`;
    }

    function loadingState(message = "Loading...") {
        return emptyState(message);
    }

    function errorBanner(message, requestIdValue = "") {
        const requestHtml = requestIdValue
            ? ` <span class="request-id">Request ID: ${escHtml(requestIdValue)}</span>`
                + ` <button type="button" class="copy-request-id" data-copy-request-id="${escHtml(requestIdValue)}">Copy</button>`
            : "";
        return `<div class="error-msg">${escHtml(message)}${requestHtml}</div>`;
    }

    document.addEventListener("click", async function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.matches("[data-copy-request-id]")) {
            return;
        }
        const id = target.getAttribute("data-copy-request-id") || "";
        try {
            await navigator.clipboard.writeText(id);
            target.textContent = "Copied";
            setTimeout(() => { target.textContent = "Copy"; }, 1200);
        } catch {
            target.textContent = "Copy failed";
            setTimeout(() => { target.textContent = "Copy"; }, 1200);
        }
    });

    function statusBadgeClass(status) {
        if (status === "ready_to_submit") return "badge-ready";
        if (status === "needs_tailoring") return "badge-tailoring";
        return "badge-skip";
    }

    function statusPillClass(status) {
        if (status === "ready_to_submit") return "pill pill-ready";
        if (status === "needs_tailoring") return "pill pill-tailoring";
        return "pill pill-skip";
    }

    window.ResumeHelper = {
        apiFetch,
        safeApiFetch,
        formatApiError,
        apiErrorBanner,
        requestId,
        escHtml,
        emptyState,
        loadingState,
        errorBanner,
        statusBadgeClass,
        statusPillClass,
    };
})();
