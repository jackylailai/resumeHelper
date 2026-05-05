// Minimal upload UI. Implementation is fleshed out in US1 task T048
// and US2 task T073 (history view).

const form = document.getElementById("upload-form");
const result = document.getElementById("result");
const statusLine = document.getElementById("status-line");
const scoreCard = document.getElementById("score-card");

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    if (!formData.get("resume_id")) {
        formData.delete("resume_id");
    }

    result.hidden = false;
    statusLine.textContent = "Uploading…";
    scoreCard.hidden = true;

    const response = await fetch("/api/resumes", { method: "POST", body: formData });
    const payload = await response.json();

    if (!response.ok) {
        statusLine.textContent = `Error: ${payload.error?.message ?? response.statusText}`;
        return;
    }

    if (response.status === 200) {
        renderEvaluation(payload.data);
    } else if (response.status === 202) {
        await pollJob(payload.data.id);
    }
});

async function pollJob(jobId) {
    statusLine.textContent = `Job ${jobId}: pending…`;
    while (true) {
        await new Promise((r) => setTimeout(r, 1500));
        const res = await fetch(`/api/jobs/${jobId}`);
        const body = await res.json();
        const job = body.data;
        statusLine.textContent = `Job ${jobId}: ${job.status}`;
        if (job.status === "succeeded") {
            const evalRes = await fetch(`/api/evaluations/${job.evaluation_id}`);
            const evalBody = await evalRes.json();
            renderEvaluation(evalBody.data);
            return;
        }
        if (job.status === "failed") {
            statusLine.textContent = `Job failed: ${job.failure_reason ?? "unknown"}`;
            return;
        }
    }
}

function renderEvaluation(evaluation) {
    document.getElementById("score-value").textContent = String(evaluation.score);
    document.getElementById("explanation").textContent = evaluation.explanation;
    renderList("strengths", evaluation.strengths);
    renderList("gaps", evaluation.gaps);
    scoreCard.hidden = false;
    statusLine.textContent = `Evaluated in ${evaluation.latency_ms} ms.`;
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
