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

1. Serve `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_check/snapshots` with a static server:
   ```bash
   python3 -m http.server 8033 --directory "/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_check/snapshots"
   ```
2. Open `http://127.0.0.1:8033/index.html`.

## Snapshot pages

- `01_workflow_home.html`
  - demonstrates: Unified entry point with counts, next actions, and regression follow-up.
  - source route: `/ops/ferreteria/training`
- `02_sandbox_review.html`
  - demonstrates: Transcript with review-any-message, structured review support, and a selected incorrect answer.
  - source route: `/ops/ferreteria/training/sandbox?session_id=training:71ff8fd8ff2642878407563656de6589&review_message_id=a1ef16f1427c42438fdd3ade06a4f5cc`
- `03_case_clarification.html`
  - demonstrates: Saved case with structured review summary, coverage state, and guided suggestion creation.
  - source route: `/ops/ferreteria/training/cases/3a284a0cee9d4dbd9fb3abc69329a971`
- `04_case_regression.html`
  - demonstrates: Case that already has a regression candidate and still needs a live-knowledge decision.
  - source route: `/ops/ferreteria/training/cases/146f6764859241f8a2d6aff081be56ec`
- `05_suggestion_draft.html`
  - demonstrates: Draft knowledge change with semantic review context and before/after preview.
  - source route: `/ops/ferreteria/training/suggestions/278a52022e6a4b608995382ad07ca012`
- `06_suggestion_approved.html`
  - demonstrates: Approved suggestion showing what is ready to go live next.
  - source route: `/ops/ferreteria/training/suggestions/1ba3f8ab183d4dfbbcaf422d67b8e80b`
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

- profile: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_check/workspace/profile.yaml`
- database: `/Users/julian/Desktop/Cerrados/Ferreteria/tmp/training_demo_check/workspace/ferreteria_training_demo.db`
- admin token used for snapshot rendering: `demo-admin-token`
