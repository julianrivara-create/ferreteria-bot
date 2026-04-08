# Ferretería Training Interface Mini Demo

This demo is fully isolated from the normal tenant data.

## What is included

- workflow home with meaningful counts
- sandbox transcript with a selected incorrect answer
- clarification-needed case
- regression-focused case
- draft suggestion detail
- approved suggestion waiting apply
- queue views and usage page

## Quick open

1. Serve `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo/snapshots` with a static server:
   ```bash
   python3 -m http.server 8033 --directory "/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo/snapshots"
   ```
2. Open `http://127.0.0.1:8033/index.html`.

## Snapshot pages

- `01_workflow_home.html`
  - demonstrates: Unified entry point with counts, next actions, and regression follow-up.
  - source route: `/ops/ferreteria/training`
- `02_sandbox_review.html`
  - demonstrates: Transcript with review-any-message, structured review support, and a selected incorrect answer.
  - source route: `/ops/ferreteria/training/sandbox?session_id=training:39108979ae684fdcab55eb62592f5c15&review_message_id=ae100dc40f7e4004adabcbf10f3f0941`
- `03_case_clarification.html`
  - demonstrates: Saved case with structured review summary, coverage state, and guided suggestion creation.
  - source route: `/ops/ferreteria/training/cases/1b18263c27f942058d577b25ffcf66f4`
- `04_case_regression.html`
  - demonstrates: Case that already has a regression candidate and still needs a live-knowledge decision.
  - source route: `/ops/ferreteria/training/cases/ddaab547b7e14692b034efdec551a987`
- `05_suggestion_draft.html`
  - demonstrates: Draft knowledge change with semantic review context and before/after preview.
  - source route: `/ops/ferreteria/training/suggestions/8d2d54beaacd412a8d760dd3c83f30dc`
- `06_suggestion_approved.html`
  - demonstrates: Approved suggestion showing what is ready to go live next.
  - source route: `/ops/ferreteria/training/suggestions/285f040ee3b24353868d86c681456e79`
- `07_cases_queue.html`
  - demonstrates: Workflow-oriented case list with next-action and regression coverage cues.
  - source route: `/ops/ferreteria/training/cases`
- `08_suggestions_queue.html`
  - demonstrates: Draft, approved, and applied suggestions in one queue with human-readable change summaries.
  - source route: `/ops/ferreteria/training/suggestions`
- `09_usage.html`
  - demonstrates: Token and cost visibility in a populated demo state.
  - source route: `/ops/ferreteria/training/usage`

## Demo workspace

- profile: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo/workspace/profile.yaml`
- database: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo/workspace/ferreteria_training_demo.db`
- admin token used for snapshot rendering: `demo-admin-token`
