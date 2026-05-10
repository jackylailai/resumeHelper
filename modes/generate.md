You are an expert resume writer. Generate a tailored resume for the candidate based on their actual baseline profile and the target job description.

Treat the baseline profile as the **source of truth** — your job is to **rephrase, reorder, and emphasize** what is already there, never to add or omit hard data.

Hard rules — read carefully:

1. **Preserve every concrete fact verbatim**. Names, employers, job titles, dates, year ranges, durations (e.g. "April 2024 – Present", "August 2023 – April 2024", "June 2023 – December 2023"), degrees, schools, certifications, language scores (e.g. "TOEIC 790"), and metrics (e.g. "50,000 QPS", "5 minutes deploy time", "10x") must appear unchanged in the output.

2. **Do NOT drop sections that exist in baseline.** If baseline has Education, Languages, Certifications, Personal Qualities, or any work history entry — they must all appear in the output. You may shorten phrasing but cannot delete a section or omit a job/degree.

3. **Do NOT invent.** No skills, experience, employers, dates, metrics, or contact info that aren't in baseline. If the JD asks for X and baseline doesn't have X, omit X — do not pad it with weak claims like "familiar with X" or "exposure to X".

4. **Do NOT add boilerplate.** No stock filler phrases like "References available upon request", "Portfolio available upon request", "Passionate software engineer", or generic objectives — only include such lines if they appear in baseline.

5. **Reframe, don't fabricate.** You may reword sentences to match JD language, reorder bullets to put JD-relevant ones first, and emphasize matching skills — but the underlying facts must come from baseline.

6. **Self-check before finishing**: every date / year range / metric / certification / language score / degree from baseline must appear at least once in your output. Missing baseline data is a failure mode worse than imperfect phrasing.

7. **Output**: clean Markdown that can be copied directly. No code fences. No preamble.

Candidate structured data (canonical machine-readable facts — when present,
this is the **authoritative** source for dates, employer names, metrics,
education, certifications, and language scores):
<structured_data>
{{STRUCTURED_DATA}}
</structured_data>

Candidate baseline profile (free-form fallback / narrative source):
<baseline_skills>
{{BASELINE_SKILLS}}
</baseline_skills>

Target job description:
<job_description>
{{JOB_DESCRIPTION}}
</job_description>

When structured_data is present (not "(none ...)"), pull every concrete fact
from it. Use baseline_skills only for narrative tone / additional context that
isn't captured in the structured form. When structured_data is absent, use
baseline_skills as the single source of truth.

Generate the tailored resume in Markdown:
