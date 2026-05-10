You receive a candidate's free-form resume / profile text. Extract every concrete fact you can find into a structured JSON object. **Use only what is explicitly in the source — do not invent, paraphrase facts, or add boilerplate.** If a field has no source, omit it.

Return ONLY a JSON object (no code fences, no preamble). Schema:

```json
{
  "personal": {
    "name": "<full name>",
    "email": "<email>",
    "phone": "<phone>",
    "location": "<city / country>",
    "links": [{"label": "<LinkedIn|GitHub|Portfolio|...>", "url": "<url>"}]
  },
  "summary": "<elevator pitch paragraph>",
  "work_experience": [
    {
      "employer": "<company name verbatim>",
      "title": "<job title>",
      "location": "<city / country>",
      "start_date": "<YYYY-MM or YYYY>",
      "end_date": "<YYYY-MM or YYYY or null if current>",
      "is_current": <true|false>,
      "achievements": ["<bullet 1>", "<bullet 2>", ...]
    }
  ],
  "education": [
    {
      "school": "<school name>",
      "degree": "<Bachelor's|Master's|...>",
      "field": "<major / programme>",
      "start_date": "<YYYY>",
      "end_date": "<YYYY>"
    }
  ],
  "languages": [
    {"name": "<language>", "level": "<Native|Fluent|...>", "test": "<TOEIC|IELTS|...>", "score": "<score>"}
  ],
  "certifications": [
    {"name": "<cert name>", "issuer": "<org>", "date": "<YYYY-MM>"}
  ],
  "skills": {
    "languages": ["<programming language>"],
    "frameworks": ["<framework>"],
    "databases": ["<db>"],
    "cloud": ["<provider/service>"],
    "tools": ["<tool>"],
    "other": ["<other skill>"]
  },
  "personal_qualities": ["<quality 1>", "<quality 2>"]
}
```

Rules:
1. **Every value comes verbatim from source.** Dates, numbers, employer names, school names, certification names — copy as-is.
2. **Don't invent fields.** If source doesn't mention email / phone / location, omit those keys.
3. **Don't editorialize.** "Backend Engineer" stays "Backend Engineer". Don't expand to "Senior Backend Engineer" if the source doesn't say so.
4. **Don't summarize achievements.** Each bullet under work_experience must be a concrete claim from the source. If source has 5 bullets, output 5 bullets.
5. **Preserve the original language.** If source mixes Chinese and English, preserve the original wording for proper nouns and quotes; you may translate connectors only if it improves clarity.

Source profile:
<source>
{{SOURCE_TEXT}}
</source>

Output only the JSON object.
