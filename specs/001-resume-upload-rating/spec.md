# Feature Specification: Resume Upload & Rating

**Feature Branch**: `001-resume-upload-rating`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "Build an application that can help me upload my resume and update or modify even rating for that"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload Resume and Receive Rating (Priority: P1)

A user uploads their resume file to the system. The system processes the
document, evaluates its quality and fit, and returns a structured rating
(numeric score) along with a plain-language explanation of strengths and
areas for improvement.

**Why this priority**: This is the core value proposition of the system. No
other feature is useful without the ability to evaluate a resume.

**Independent Test**: Upload a sample PDF resume → system returns a score
between 0–100 and a written explanation. This flow delivers full value
on its own.

**Acceptance Scenarios**:

1. **Given** a user has a resume file (PDF or DOCX), **When** they upload it,
   **Then** the system stores the file, triggers evaluation, and returns a
   rating with a score and explanation within 30 seconds.
2. **Given** the upload is in progress, **When** evaluation takes longer than
   5 seconds, **Then** the system returns a `job_id` immediately and the user
   can poll for the result.
3. **Given** an unsupported file format is submitted, **When** the user
   uploads it, **Then** the system rejects the file with a clear error message
   listing supported formats.
4. **Given** the file exceeds the maximum allowed size, **When** the user
   uploads it, **Then** the system rejects the upload before processing begins.

---

### User Story 2 - Modify Resume and Get Updated Rating (Priority: P2)

A user who already has a resume on file updates its content (either by
re-uploading a new version or editing key sections) and receives a fresh
rating reflecting the changes. The system preserves all previous versions
and their ratings so the user can compare progress over time.

**Why this priority**: Iterative improvement is the main workflow loop.
Without update + re-rating, the tool becomes a one-shot utility rather than
an ongoing assistant.

**Independent Test**: After completing Story 1, re-upload a revised resume →
system creates a new version, re-evaluates, returns updated score and
explanation. Both the old and new rating remain accessible.

**Acceptance Scenarios**:

1. **Given** a user has an existing resume on file, **When** they upload a
   new version, **Then** the system creates a new version record, evaluates
   it, and returns the updated rating without overwriting the previous version.
2. **Given** two or more versions exist, **When** the user requests their
   rating history, **Then** the system returns all versions with their
   respective scores, explanations, and timestamps in reverse-chronological
   order.
3. **Given** the modified resume is identical in content to a previous
   version, **When** the user submits it, **Then** the system detects the
   duplicate and returns the cached rating without re-invoking evaluation.

---

### User Story 3 - View and Compare Ratings (Priority: P3)

A user can browse the history of all resume versions they have submitted,
compare scores across versions, and understand which changes led to score
improvements or regressions.

**Why this priority**: Visibility into history helps users make informed
editing decisions and validates that their changes are having the intended
effect.

**Independent Test**: After submitting two or more versions, list all ratings
→ system returns a sorted history showing score trend. Can be demonstrated
independently after Story 1 and Story 2.

**Acceptance Scenarios**:

1. **Given** multiple resume versions exist, **When** the user views their
   rating history, **Then** scores are displayed in order with upload date
   and a brief summary of the evaluation explanation.
2. **Given** the user selects any two versions, **When** they request a
   comparison, **Then** the system highlights the score difference and
   identifies which sections changed between versions.

---

### Edge Cases

- What happens when the LLM evaluation service is unavailable? System MUST
  queue the request and notify the user when evaluation completes, rather
  than returning a hard failure.
- What happens when a resume contains no parseable text (e.g., a scanned
  image PDF)? System MUST reject the file with a clear message explaining
  the limitation.
- What if the user uploads an extremely large number of versions? System MUST
  paginate history results and impose a reasonable per-user version limit
  (defaulting to 50 versions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept resume file uploads in PDF and DOCX formats.
- **FR-002**: System MUST enforce a maximum file size of 10 MB per upload.
- **FR-003**: System MUST evaluate each uploaded resume and produce a numeric
  score (0–100) and a plain-language explanation of the evaluation.
- **FR-004**: System MUST return a `job_id` for evaluations that take longer
  than 5 seconds and expose a status endpoint for polling.
- **FR-005**: System MUST store each uploaded resume as a distinct, immutable
  version; re-uploading creates a new version rather than overwriting.
- **FR-006**: System MUST allow users to retrieve the rating and explanation
  for any stored resume version.
- **FR-007**: System MUST return evaluation history (all versions with
  scores and timestamps) in reverse-chronological order.
- **FR-008**: System MUST detect duplicate resume content (same file hash)
  and return the cached rating without re-invoking evaluation.
- **FR-009**: System MUST gracefully handle LLM service unavailability by
  queuing the evaluation and notifying the user when complete.
- **FR-010**: System MUST reject files with no extractable text with a
  descriptive error message.
- **FR-011**: Ratings are generated against a specific job description 
  provided by the user (job-fit scoring). The user supplies or selects a 
  target job description, and the evaluation assesses how well the resume 
  matches the requirements of that role.
- **FR-012**: This is a single-user personal tool for the initial version. 
  No user accounts, no authentication, no multi-user data isolation required. 
  The system operates in single-user mode.

### Key Entities

- **Resume**: The uploaded document file. Has a unique ID, file reference,
  content hash, format, upload timestamp, and belongs to a user (or session
  for single-user mode).
- **ResumeVersion**: A specific immutable snapshot of a Resume. Carries
  version number, content hash, and upload timestamp. One Resume may have
  many ResumeVersions.
- **ResumeEvaluation**: The rating output for a ResumeVersion. Contains
  numeric score (0–100), explanation text, evaluation context (general or
  job-specific), prompt version used, and completion timestamp.
- **EvaluationJob**: Tracks the async evaluation lifecycle
  (`pending → running → succeeded → failed`) for a ResumeVersion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can upload a resume and receive a complete rating
  (score + explanation) within 30 seconds under normal conditions.
- **SC-002**: Users can submit a revised resume and see the updated rating
  without losing access to any previous version or rating.
- **SC-003**: 90% of users successfully complete the upload-to-rating flow
  on their first attempt without encountering errors.
- **SC-004**: The system correctly associates every rating with the exact
  resume version it evaluated, with zero mismatches.
- **SC-005**: Users can retrieve their full rating history (all versions)
  in under 2 seconds regardless of how many versions they have stored
  (up to the 50-version limit).
- **SC-006**: Duplicate resume submissions (same content) return the
  cached rating instantly (under 1 second) without re-evaluating.

## Assumptions

- PDF and DOCX are sufficient file formats for v1; other formats (TXT, ODT)
  are out of scope.
- Maximum file size of 10 MB covers the vast majority of real-world resumes.
- A per-user version cap of 50 is sufficient for individual use; this can be
  raised in a later version.
- Evaluation explanations are returned in English for v1; localization is
  out of scope.
- Mobile file upload support is desirable but the primary target is desktop
  web / API clients.
- The evaluation prompt version is stored with each result so that score
  changes caused by prompt updates are distinguishable from changes caused
  by resume edits.
- This is a single-user application; no authentication or user account 
  management is required. Data is stored locally for the single user.
