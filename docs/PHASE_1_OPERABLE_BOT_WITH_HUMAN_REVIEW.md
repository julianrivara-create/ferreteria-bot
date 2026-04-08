# Phase 1 — Operable Bot With Human Review

## 1. Phase 1 objective

Phase 1 is complete when the current ferreteria bot can:

- receive a real customer request through the existing runtime,
- generate a preliminary quote for supported catalog scenarios,
- persist quote state durably in the ferreteria SQLite database,
- route customer acceptance into a human review workflow instead of pretending a sale is closed,
- and let the business maintain day-to-day knowledge without editing Python for each small change.

In implementation terms, success means:

- the bot runtime in `bot_sales` stays product-first and deterministic,
- `quotes`, `quote_lines`, `quote_events`, `handoffs`, and `unresolved_terms` are durable,
- quote acceptance creates a review request and operator queue item,
- operators can inspect accepted quotes and unresolved terms from a small admin surface,
- and FAQs, synonyms, and clarification rules are editable through tenant knowledge files and admin endpoints.

This phase is about making the bot operationally real and safe. It is not about making it universally intelligent.

## 2. Scope of Phase 1

### Included

- Durable quote persistence
- Review-requested acceptance workflow
- Minimal admin surface for operators
- Basic tenant-editable business knowledge
- Preservation of the current ferreteria-first routing and FAQ behavior
- Regression protection for current ferreteria flows

### Excluded

- Autonomous closing or confirmed-sale automation
- Full obra/project quote intelligence
- Universal product comprehension
- Multi-industry abstractions
- RAG, embeddings, vector DBs
- CRM shell expansion
- Payment orchestration, stock decrement, logistics automation

Anything beyond these boundaries belongs to later phases and is out of scope for Phase 1.

## 3. Architecture for Phase 1

### Runtime

Keep the existing runtime shape:

- [`bot_sales/runtime.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/runtime.py) resolves the ferreteria runtime.
- [`bot_sales/bot.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/bot.py) remains the main orchestrator.
- [`bot_sales/ferreteria_quote.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/ferreteria_quote.py) remains the deterministic quote engine.
- [`bot_sales/core/business_logic.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/core/business_logic.py) remains the stock/FAQ/business bridge.

Runtime rule for Phase 1:

- in-memory session state may remain as a working cache,
- but the DB is the source of truth for active quotes and handoff state.

### Persistence

Use the ferreteria tenant SQLite DB already referenced by the tenant profile.

Persistence responsibilities live inside `bot_sales`, not in the Flask app:

- [`bot_sales/persistence/quote_store.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/persistence/quote_store.py)
- [`bot_sales/services/quote_service.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/services/quote_service.py)
- [`bot_sales/services/handoff_service.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/services/handoff_service.py)

### Editable knowledge

Day-to-day business-adjustable knowledge lives under:

- [`data/tenants/ferreteria/knowledge/`](/Users/julian/Desktop/Cerrados/Ferreteria/data/tenants/ferreteria/knowledge)

Loaded through:

- [`bot_sales/knowledge/loader.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/loader.py)
- [`bot_sales/knowledge/validators.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/validators.py)
- [`bot_sales/knowledge/defaults.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/defaults.py)

### Human review handoff

Acceptance is treated as:

- quote accepted by the customer,
- internal review requested,
- follow-up still pending human validation.

No automatic sale confirmation is allowed in this phase.

### Minimal admin

Use the existing Flask app as the host surface, but keep the admin small and ferreteria-specific:

- API blueprint: [`app/api/ferreteria_admin_routes.py`](/Users/julian/Desktop/Cerrados/Ferreteria/app/api/ferreteria_admin_routes.py)
- UI blueprint: [`app/ui/ferreteria_admin_routes.py`](/Users/julian/Desktop/Cerrados/Ferreteria/app/ui/ferreteria_admin_routes.py)
- Templates: [`app/ui/templates/ferreteria_admin/`](/Users/julian/Desktop/Cerrados/Ferreteria/app/ui/templates/ferreteria_admin)

### Boundaries

#### Code-owned

- Quote parsing
- Resolver scoring
- Line targeting
- Pack/unit safety
- Quote lifecycle transitions
- Persistence writes
- Channel/runtime mechanics
- Admin auth

#### Business-editable

- Synonyms / aliases
- FAQ content
- Clarification rules
- Family rules
- Blocked/confusing terms
- Complementary rules
- Acceptance phrase lists

#### Stored in DB

- Quotes
- Quote lines
- Quote events
- Handoffs
- Unresolved terms
- Knowledge change audit

#### Visible in admin

- Accepted/review queue
- Quote detail and events
- Unresolved terms review
- FAQ editing
- Synonym editing
- Clarification rule editing

## 4. Persistence design for Phase 1

### `quotes`

Purpose:

- durable root record for each quote/session lifecycle.

Required fields:

- `id`
- `tenant_id`
- `session_id`
- `channel`
- `customer_ref`
- `customer_name`
- `customer_phone`
- `customer_email`
- `status`
- `currency`
- `resolved_total_amount`
- `has_blocking_lines`
- `accepted_at`
- `closed_at`
- `last_customer_message_at`
- `last_bot_message_at`
- `created_at`
- `updated_at`

Statuses:

- `open`
- `waiting_customer_input`
- `review_requested`
- `under_internal_review`
- `revision_requested`
- `ready_for_followup`
- `closed_completed`
- `closed_cancelled`

Relationships:

- one quote has many `quote_lines`
- one quote has many `quote_events`
- one quote has many `handoffs`

Operational value:

- restart-safe quote state
- queue filtering by status
- durable operator visibility

### `quote_lines`

Purpose:

- current line items of the quote, including confidence and clarification needs.

Required fields:

- `id`
- `quote_id`
- `line_number`
- `source_text`
- `normalized_text`
- `requested_qty`
- `unit_hint`
- `line_status`
- `confidence_score`
- `selected_sku`
- `selected_name`
- `selected_category`
- `selected_unit_price`
- `presentation_note`
- `clarification_prompt`
- `resolution_reason`
- `alternatives_json`
- `complementary_json`
- `active`
- `created_at`
- `updated_at`

Statuses:

- `resolved_high_confidence`
- `resolved_needs_confirmation`
- `ambiguous`
- `unresolved`
- `blocked_by_missing_info`

Relationships:

- many lines belong to one quote

Operational value:

- separates safe lines from blocked ones
- gives operators a real review object
- prevents the UI from treating every line as equally trustworthy

### `quote_events`

Purpose:

- append-only audit log of meaningful state changes.

Required fields:

- `id`
- `quote_id`
- `event_type`
- `actor_type`
- `actor_ref`
- `line_id`
- `payload_json`
- `created_at`

Typical events:

- `quote_created`
- `customer_message_received`
- `line_added`
- `line_updated`
- `line_removed`
- `quote_opened`
- `quote_acceptance_requested`
- `quote_acceptance_blocked`
- `handoff_created`
- `handoff_alert_sent`
- `quote_status_changed`
- `operator_note`
- `operator_claimed`
- `quote_reset`

Operational value:

- operator traceability
- debugging without relying on logs only
- review history of how the quote evolved

### `handoffs`

Purpose:

- operational queue and alert record for accepted quotes.

Required fields:

- `id`
- `quote_id`
- `status`
- `destination_type`
- `destination_ref`
- `claimed_by`
- `claimed_at`
- `contacted_customer_at`
- `resolved_at`
- `outcome_note`
- `last_error`
- `created_at`
- `updated_at`

Statuses:

- `queued`
- `alert_sent`
- `claimed`
- `contacted`
- `resolved`
- `cancelled`

Relationships:

- many handoffs belong to one quote

Operational value:

- turns acceptance into a real queue item
- separates “customer accepted” from “team processed”
- supports admin queue and alert audit

### `unresolved_terms`

Purpose:

- durable review stream for terms that could not be safely resolved.

Required fields:

- `id`
- `tenant_id`
- `quote_id`
- `quote_line_id`
- `raw_text`
- `normalized_text`
- `status`
- `reason`
- `review_status`
- `resolution_note`
- `linked_knowledge_domain`
- `linked_knowledge_key`
- `reviewed_by`
- `reviewed_at`
- `created_at`

Statuses:

- runtime statuses: `ambiguous`, `unresolved`, `blocked_by_missing_info`
- review statuses: `new`, `acknowledged`, `mapped_to_synonym`, `catalog_gap_confirmed`, `ignored`

Operational value:

- lets the team learn from pilot traffic
- makes synonym/catalog improvement concrete
- preserves the current unresolved honesty

### `knowledge_change_audit`

Purpose:

- audit log for business knowledge edits.

Required fields:

- `id`
- `tenant_id`
- `domain`
- `entity_key`
- `action`
- `before_json`
- `after_json`
- `changed_by`
- `change_reason`
- `created_at`

Operational value:

- reviewable business edits
- supports rollback decisions
- makes bot behavior changes explainable

## 5. Human review workflow for Phase 1

### When a quote is open

- The bot parses and resolves items with the current deterministic ferreteria logic.
- Every meaningful change is persisted to the quote store.
- If any line is blocking, quote status becomes `waiting_customer_input`.
- If all current lines are resolved, status remains `open`.

### When a line is unresolved

- The bot must not pretend certainty.
- The line is stored as `ambiguous`, `unresolved`, or `blocked_by_missing_info`.
- The quote is not accept-ready.
- The unresolved term is logged both in the unresolved log flow and in DB review storage.

### When a customer tries to accept

- If any line is blocking, acceptance is rejected.
- The bot answers with clarification-needed wording.
- The quote remains in `waiting_customer_input`.
- No handoff is created.

### When a quote is accepted

- Append `quote_acceptance_requested` event.
- Set quote status to `review_requested`.
- Set `accepted_at`.
- Create one `admin_queue` handoff.
- Attempt one `email` alert handoff if configured.
- Return operationally honest copy:
  - review requested
  - team will validate and follow up
  - not a confirmed sale

### When an operator reviews it

- Operator claims the quote from admin.
- Quote status moves to `under_internal_review`.
- Operator can inspect:
  - line statuses
  - selected products
  - clarification prompts
  - unresolved reasons
  - event trail

### When an operator needs revision

- Operator sets `revision_requested`.
- Operator can leave a note.
- Internal follow-up with the customer remains human-driven in this phase.

### When an operator closes it

- `ready_for_followup` if validated and ready for commercial follow-up
- `closed_completed` if manually completed
- `closed_cancelled` if dropped/cancelled

This is intentionally conservative. Anything more automated belongs to later phases.

## 6. Editable knowledge layer for Phase 1

### Knowledge domains

#### Synonyms

- File: `synonyms.yaml`
- Stores canonical items, aliases, and family hints.
- Used before product search expansion.

#### FAQs

- File: `faqs.yaml`
- Stores `id`, `question`, `answer`, `keywords`, `active`, `tags`.
- Used by deterministic FAQ short-circuiting.

#### Clarification rules

- File: `clarification_rules.yaml`
- Stores clarification prompts, examples, and required dimensions by family/item.

#### Family rules

- File: `family_rules.yaml`
- Stores allowed categories, required dimensions, optional dimensions, and compatibility sensitivity.
- This is included because ferreteria resolution depends on size/material/use ambiguity.

#### Blocked terms

- File: `blocked_terms.yaml`
- Stores phrases that should never auto-resolve.

#### Complementary rules

- File: `complementary_rules.yaml`
- Stores controlled complementary suggestions.

#### Acceptance patterns

- File: `acceptance_patterns.yaml`
- Stores phrase lists for acceptance, reset, merge, and new quote.

### File/storage format

- YAML only
- tenant-scoped under `data/tenants/ferreteria/knowledge/`

### Validation

All knowledge writes must go through:

- [`bot_sales/knowledge/validators.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/validators.py)

Validation rules include:

- required structure present
- no duplicate aliases
- no unknown family references
- no unknown dimensions
- non-empty required phrase lists

### Runtime loading

Runtime reads knowledge through:

- [`bot_sales/knowledge/loader.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/loader.py)

The loader is responsible for:

- file reads
- validation
- cache management
- reload/invalidation after admin save

### Caching

- in-process cache
- file mtime-based invalidation
- admin save invalidates the cache
- FAQ runtime also reloads on mtime change

### Fallback behavior during migration

- if a tenant knowledge file is missing, use fallback defaults from `defaults.py`
- if a new edit is invalid, reject it and keep the last valid runtime state
- the old root `faqs.json` may remain only as a migration fallback

## 7. Minimal admin for Phase 1

The admin must stay intentionally small.

### Pages

#### Accepted quotes queue

Route:

- `GET /ops/ferreteria/quotes`

Shows:

- quotes in `review_requested`, `under_internal_review`, `revision_requested`, `ready_for_followup`
- customer reference
- channel
- blocking flag
- accepted time
- updated time

#### Quote detail view

Route:

- `GET /ops/ferreteria/quotes/<quote_id>`

Shows:

- quote header
- quote lines with confidence/status
- totals
- handoffs
- event history

Actions:

- claim
- update status
- add operator note

#### Unresolved terms review

Route:

- `GET /ops/ferreteria/unresolved-terms`

Shows:

- unresolved/ambiguous/blocked items
- reason
- review status

Actions:

- mark acknowledged
- mark mapped to synonym
- mark catalog gap
- ignore

#### FAQ editor

Route:

- `GET/POST /ops/ferreteria/knowledge/faqs`

#### Synonym editor

Route:

- `GET/POST /ops/ferreteria/knowledge/synonyms`

#### Clarification rule editor

Route:

- `GET/POST /ops/ferreteria/knowledge/clarifications`

### API endpoints

- `GET /api/admin/ferreteria/quotes`
- `GET /api/admin/ferreteria/quotes/<quote_id>`
- `POST /api/admin/ferreteria/quotes/<quote_id>/status`
- `POST /api/admin/ferreteria/quotes/<quote_id>/claim`
- `POST /api/admin/ferreteria/quotes/<quote_id>/note`
- `GET /api/admin/ferreteria/unresolved-terms`
- `POST /api/admin/ferreteria/unresolved-terms/<id>/review`
- `GET /api/admin/ferreteria/knowledge/<domain>`
- `PUT /api/admin/ferreteria/knowledge/<domain>`
- `POST /api/admin/ferreteria/knowledge/reload`

### Templates/pages

Keep simple server-rendered templates:

- `base.html`
- `quotes.html`
- `quote_detail.html`
- `unresolved_terms.html`
- `knowledge_editor.html`

### Operator actions

- claim quote
- update quote status
- add note
- review unresolved term
- edit FAQs
- edit synonyms
- edit clarification rules

No SPA, no CRM shell dependency, no role matrix. That is intentionally out of scope.

## 8. Repository integration plan

### Extend existing modules

- [`bot_sales/bot.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/bot.py)
  - load persisted active quote
  - persist state after meaningful mutations
  - use knowledge loader
  - turn acceptance into review-requested handoff

- [`bot_sales/ferreteria_quote.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/ferreteria_quote.py)
  - read editable knowledge
  - emit statuses aligned with persistence
  - preserve current deterministic routing and formatting

- [`bot_sales/faq.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/faq.py)
  - support tenant YAML FAQ file
  - reload edited FAQ content safely

- [`app/main.py`](/Users/julian/Desktop/Cerrados/Ferreteria/app/main.py)
  - register the ferreteria admin API/UI blueprints

### Add new modules

- [`bot_sales/persistence/quote_store.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/persistence/quote_store.py)
- [`bot_sales/services/quote_service.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/services/quote_service.py)
- [`bot_sales/services/handoff_service.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/services/handoff_service.py)
- [`bot_sales/knowledge/loader.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/loader.py)
- [`bot_sales/knowledge/validators.py`](/Users/julian/Desktop/Cerrados/Ferreteria/bot_sales/knowledge/validators.py)
- [`app/api/ferreteria_admin_routes.py`](/Users/julian/Desktop/Cerrados/Ferreteria/app/api/ferreteria_admin_routes.py)
- [`app/ui/ferreteria_admin_routes.py`](/Users/julian/Desktop/Cerrados/Ferreteria/app/ui/ferreteria_admin_routes.py)

### Current flows that must remain intact

- CLI entrypoint
- WhatsApp bootstrap
- product-first ferreteria pre-route
- deterministic FAQ short-circuit
- unresolved honesty
- unresolved-term logging
- current smoke philosophy

### What should not be touched yet

- `app/bot/*`
- storefront/website
- CRM deal pipeline
- multi-industry abstractions
- phase-2+ quote intelligence work

## 9. Migration plan

### Step 1. Add persistence layer

- Add quote schema to the ferreteria SQLite DB
- Add quote store/service
- No behavior rewrite yet

### Step 2. Dual-state runtime

- Keep in-memory session state
- Rehydrate open quote from DB first
- Persist every meaningful mutation back to DB

### Step 3. Move editable knowledge

- Add tenant knowledge YAML files
- Load them through one loader/validator
- Keep fallback defaults during transition

### Step 4. Replace acceptance semantics

- Stop implying “sale confirmed”
- Create `review_requested` + handoff instead

### Step 5. Add minimal admin

- Queue page
- Quote detail page
- Unresolved terms page
- Knowledge editors

### Compatibility strategy

- preserve current quote formatting as much as possible
- preserve current routing order
- preserve current tests and expand them
- keep unresolved JSONL logging while DB review flow stabilizes

## 10. Testing plan for Phase 1

### Persistence tests

- quote creation persists
- active quote reload survives bot re-instantiation
- additive update persists on the same quote
- reset closes the persisted quote

### Handoff tests

- acceptance creates `review_requested`
- acceptance creates queue handoff
- email handoff is attempted
- acceptance is blocked when pending lines remain

### Knowledge tests

- synonym validation rejects bad payloads
- FAQ edit works without Python changes
- clarification rule validation works
- cache invalidates on save

### Admin tests

- token auth protects endpoints
- queue listing works
- quote detail loads
- unresolved review endpoint updates status
- knowledge update endpoints persist valid changes

### Regression tests

- product-first routing still wins
- deterministic FAQ still short-circuits
- unresolved behavior stays honest
- pack safety stays intact
- current ferreteria setup suite still passes

## 11. Definition of done

Phase 1 is done only if all of the following are true:

- Quotes survive process restart
- Quotes, lines, events, handoffs, unresolved terms, and knowledge audit are stored durably
- Acceptance no longer implies confirmed sale
- Accepted quotes appear in a human review queue
- Operators can inspect quote detail and status
- Operators can review unresolved terms
- FAQs can be edited without touching Python
- Synonyms can be edited without touching Python
- Clarification rules can be edited without touching Python
- Runtime uses tenant knowledge safely
- Product-first ferreteria routing still works
- Deterministic FAQ behavior still works
- Honest unresolved behavior still works
- Existing ferreteria behavioral tests pass
- Phase 1 persistence/admin/handoff tests pass
- Smoke validation passes on the real conversational path
- No phase-2+ functionality was bundled in under Phase 1

Anything beyond this checklist is out of scope for Phase 1.
