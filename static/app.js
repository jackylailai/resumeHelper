const form = document.getElementById("upload-form");
const result = document.getElementById("result");
const statusLine = document.getElementById("status-line");
const scoreCard = document.getElementById("score-card");
const historySection = document.getElementById("history");
const historyList = document.getElementById("history-list");

let currentResumeId = null;

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    if (!formData.get("resume_id")) {
        formData.delete("resume_id");
    }

    result.hidden = false;
    statusLine.textContent = "Uploading…";
    scoreCard.hidden = true;
    historySection.hidden = true;

    const { response, payload } = await safeApiFetch(
        "/api/resumes",
        { method: "POST", body: formData }
    );

    if (!response.ok) {
        statusLine.textContent = formatError(response, payload);
        return;
    }

    if (response.status === 200) {
        renderEvaluation(payload.data, payload.meta?.cached === true);
        await loadHistory();
    } else if (response.status === 202) {
        await pollJob(payload.data.id);
        await loadHistory();
    }
});

async function pollJob(jobId) {
    statusLine.textContent = `Job ${jobId}: pending…`;
    while (true) {
        await new Promise((r) => setTimeout(r, 1500));
        const { response: res, payload: body } = await safeApiFetch(`/api/jobs/${jobId}`);
        if (!res.ok) {
            statusLine.textContent = formatError(res, body);
            return;
        }
        const job = body.data;
        statusLine.textContent = `Job ${jobId}: ${job.status}`;
        if (job.status === "succeeded") {
            const { response: evalRes, payload: evalBody } = await safeApiFetch(
                `/api/evaluations/${job.evaluation_id}`
            );
            if (!evalRes.ok) {
                statusLine.textContent = formatError(evalRes, evalBody);
                return;
            }
            renderEvaluation(evalBody.data, false);
            return;
        }
        if (job.status === "failed") {
            statusLine.textContent = `Job failed: ${job.failure_reason ?? "unknown"}`;
            return;
        }
    }
}

function renderEvaluation(evaluation, cached) {
    document.getElementById("score-value").textContent = String(evaluation.score);
    document.getElementById("explanation").textContent = evaluation.explanation;
    renderList("strengths", evaluation.strengths);
    renderList("gaps", evaluation.gaps);
    scoreCard.hidden = false;

    const cacheNote = cached ? " (from cache)" : "";
    statusLine.textContent = `Evaluated in ${evaluation.latency_ms} ms${cacheNote}.`;

    // Wire "Upload new version" button (shown after first eval)
    const btn = document.getElementById("reupload-btn");
    if (btn && currentResumeId) {
        btn.hidden = false;
        btn.onclick = () => {
            document.getElementById("resume-id").value = currentResumeId;
            document.getElementById("resume-file").focus();
            document.getElementById("upload-form").scrollIntoView({ behavior: "smooth" });
        };
    }
}

function renderList(id, items) {
    const ul = document.getElementById(id);
    ul.innerHTML = "";
    for (const item of items ?? []) {
        const li = document.createElement("li");
        li.textContent = item;
        ul.appendChild(li);
    }
}

async function loadHistory() {
    // Fetch most recently updated resume (current upload) to get its ID
    const { response: listRes, payload: listBody } = await safeApiFetch("/api/resumes");
    if (!listRes.ok) return;
    const resumes = listBody.data;
    if (!resumes || resumes.length === 0) return;

    const resume = resumes[0];
    currentResumeId = resume.id;

    // Fetch its version history
    const { response: verRes, payload: verBody } = await safeApiFetch(
        `/api/resumes/${resume.id}/versions`
    );
    if (!verRes.ok) return;
    const versions = verBody.data;

    historyList.innerHTML = "";
    for (const v of versions) {
        const li = document.createElement("li");
        const date = new Date(v.uploaded_at).toLocaleString();
        const scoreText = v.evaluation ? ` — score ${v.evaluation.score}` : "";
        const fileSizeKb = (v.file_size_bytes / 1024).toFixed(1);
        li.textContent = (
            `v${v.version_number}  ${date}  ` +
            `(${v.file_format.toUpperCase()}, ${fileSizeKb} KB)${scoreText}`
        );
        historyList.appendChild(li);
    }

    historySection.hidden = versions.length === 0;
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
            response: { ok: false, status: 0, statusText: "Network error", headers: new Headers() },
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
