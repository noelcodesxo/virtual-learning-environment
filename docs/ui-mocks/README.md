# Study workspace redesign references

These mockups are planning references only. They do not correspond to implemented UI changes.

- `study-assistant-ui-proposal.html` — unified application rail, first-class Library view, Chat, exam setup, and generation wait-state proposal.
- `study-assistant-recent-exams-proposal.html` — Recent exams list, resume flow, and graded-review proposal.

## Reviewed implementation plan

### Scope and constraints

- This redesign changes the application UI only; it does not change document extraction, indexing, exam prompts, or the in-memory lifetime of exam history.
- EPUB and PDF remain the supported upload formats. A document shown in the catalog is already indexed and is labelled **Ready**; during an upload, the Resources view labels the current file **Adding and indexing**. The API does not persist a separate upload-job history, so the UI will not imply that it does.
- Exam generation remains a single synchronous request to the existing model provider. The UI must never show a percentage or claim that server-side source preparation has completed. It will acknowledge the selected source before requesting generation, then show an indeterminate **Waiting for the exam model response** status until the request completes or fails.

### 1. Define the application routes and shell

- Update `frontend/components/app-shell.tsx` to replace the two-button mode switch with one persistent application rail: **Chat** (`/`), **Exams** (`/exams`), and **Resources** (`/resources`). Preserve the existing direct URLs and mark the correct link with `aria-current`.
- Add `frontend/app/resources/page.tsx` for the Resources view and `frontend/app/exams/history/page.tsx` for the Recent exams destination. The existing `/exams` route remains the new-exam setup screen.
- Replace the shared nested-sidebar styling in `frontend/app/globals.css` with rail, centered-content, mobile-nav, and focus-state styles. On narrow screens the rail becomes a compact horizontal navigation bar; no navigation controls are hidden solely because of viewport size.

### 2. Expose a library catalog independently of the exam feature

- Extend `LibraryService` in `src/library.py` with a catalog method that returns each supported resource's existing title and chapters plus `filename` and lowercase `format` (`epub` or `pdf`). It reuses the cached extractor catalog and does not re-extract document text for the new fields.
- Add `GET /library` in `src/server.py`, outside the exam-feature gate. Its response is `{ documents: [{ title, filename, format, chapters }] }`, sorted by filename through the existing resource ordering. Keep `GET /books` unchanged for exam-builder compatibility.
- Add `LibraryDocument` / `LibraryResponse` response models and backend tests covering the response metadata and the fact that the route is available when the exam builder is disabled.
- Add matching `LibraryDocument` types and `api.library()` in `frontend/lib/types.ts` and `frontend/lib/api.ts`, with a frontend API-client test.

### 3. Build the Resources view and relocate uploading

- Add a `frontend/components/library-workspace.tsx` client component. It loads `api.library()` on entry and renders an empty, loading, error, and ready catalog state.
- Each catalog row displays title, EPUB/PDF format, detected chapter count, and a collapsible chapter list. The primary action is **Add document** and accepts the existing EPUB/PDF MIME types.
- Move the current upload behavior out of `ChatWorkspace`: keep the 50 MB client guard and server error messages, invalidate/reload the Resources catalog after a successful upload, and present upload status in the Resources view. Chat retains no document-upload control.

### 4. Rework chat and exams around centered workspaces

- Simplify `frontend/components/chat-workspace.tsx` by removing its secondary sidebar. Keep in-memory threads, New chat, model selection, message/source rendering, and error behavior. Place New chat in the chat header so existing chat behavior is retained without a second persistent column.
- Update `frontend/components/exam-builder.tsx` to remove its secondary sidebar and use direct links: **Recent exams** links to `/exams/history`, while **New exam** links to `/exams` from exam-taking and review states.
- Make `ExamBuilder` accept an `initialView` prop of `"configure" | "history"`. The `/exams/history` route passes `"history"`; it loads the existing `GET /exams` list, supports filters **All**, **In progress**, and **Completed**, and opens an existing exam/review with the current API behavior. The `/exams` route passes `"configure"`.
- Existing exam records remain session-only because the backend currently stores them in `state["exams"]`; copy in the UI will call these **Recent exams** rather than promise permanent history.

### 5. Implement honest generation feedback and verify

- When the user begins generation, show the selected resource/chapter immediately. While the single `api.generateExam` request is outstanding, show an indeterminate progress treatment with **Waiting for the exam model response** and accessible `role="status"`; on a request failure, return to setup and display the existing server error.
- Do not modify the exam-generation API or introduce polling/SSE in this redesign. Add a numeric percentage only in a later change if the provider sends verifiable progress events.
- Add or update focused backend tests in `src/library_test.py` and `src/server_test.py`, frontend API tests in `frontend/lib/api.test.ts`, and component-level tests only if a test harness is introduced without adding a dependency. Run `uv run pytest -q`, `npm test`, `npm run lint`, and `npm run build` from `frontend/`. Manually verify desktop and narrow layouts plus keyboard navigation, upload error/success, Resources catalog, new exam, recent/existing exam, and generation failure/success when the locally configured services are available.

## Plan-review record

**Initial gate result:** `STATUS: CHANGES_REQUIRED` — the original five-step outline did not identify the routes, component ownership, catalog API contract, feature-flag behavior, exam-history destination, or the exact honest-progress behavior.

**Revised gate result:** `STATUS: APPROVED_TO_IMPLEMENT` — the plan above resolves the identified contracts, preserves the existing routes and APIs where required, avoids invented progress, and includes concrete backend/frontend verification. Implementation may begin.
