# Study workspace redesign references

These mockups are planning references only. They do not correspond to implemented UI changes.

- `study-assistant-ui-proposal.html` — unified application rail, first-class Library view, Chat, exam setup, and generation wait-state proposal.
- `study-assistant-recent-exams-proposal.html` — Recent exams list, resume flow, and graded-review proposal.

## Implementation plan

1. Replace the nested sidebars with one persistent application rail for Chat, Exams, and Resources, while preserving direct routes.
2. Add a first-class Library catalog and API that shows document metadata, detected chapters, and upload state.
3. Rework Chat and Exams into centered workspace views; move recent exams into its own sub-view with resume and review states.
4. Add honest generation status: completed local phases plus an indeterminate provider-wait state. Add percentages only if a provider exposes verifiable progress.
5. Add responsive and accessibility coverage, component/API tests, and complete frontend/backend verification.
