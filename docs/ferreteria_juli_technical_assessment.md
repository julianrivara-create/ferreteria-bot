# Technical Assessment: "Ferretería Juli" Bot

Date: 2026-03-17  
Repository assessed: `/Users/julian/Desktop/Cerrados/Ferreteria`

Important naming note: the requested bot name in this document is **"Ferretería Juli"**, but the current repository runtime, tenant files, branding, and README still identify the business as **"Ferreteria Central"**. No rename has been applied yet. This document reflects the implementation as it exists today.

## 1. Bot purpose and business goal

The current bot is a ferretería-oriented sales and quoting assistant designed to operate primarily through:

- CLI (`bot_cli.py`)
- WhatsApp (`whatsapp_server.py`)

Its intended business goal is to help a customer describe what they need for a home, maintenance, or construction task and then:

- identify relevant products from the catalog,
- build a preliminary quote,
- ask clarifying questions when required,
- optionally suggest related items,
- and hand the accepted quote to the internal team for follow-up.

In implementation reality, the bot is currently strongest at:

- simple product lookup,
- category browsing,
- FAQ answering,
- narrow multi-item preliminary quotes,
- and controlled multi-turn clarification for a small catalog.

It is not yet a full operational quoting platform for dense, real-world ferretería material lists.

## 2. Current architecture

### Active runtime architecture

The active bot runtime is driven by the `bot_sales` package, not by the larger `app/` web platform.

Main runtime path:

1. Tenant resolution via `bot_sales/runtime.py`
2. Bot instantiation through the tenant manager
3. Message orchestration in `bot_sales/bot.py`
4. Business operations in `bot_sales/core/business_logic.py`
5. Catalog persistence in `bot_sales/core/database.py`
6. Ferretería-specific quote routing and formatting in `bot_sales/ferreteria_quote.py`
7. Optional LLM/function-calling via `bot_sales/core/chatgpt.py`

### Entry points

- `bot_cli.py`: thin wrapper over `bot_sales.connectors.cli.main`
- `whatsapp_server.py`: boots the runtime tenant and starts the WhatsApp webhook server

### Runtime tenancy

The runtime defaults to tenant slug `ferreteria` in `bot_sales/runtime.py`.  
Selection logic:

- explicit tenant argument if provided,
- otherwise `BOT_TENANT_ID`,
- otherwise tenant slug `ferreteria`,
- otherwise the default tenant from `tenants.yaml`.

This means the project is **ferretería-first**, but not fully hard-locked to a single tenant.

### Architectural reality

This repository still contains a broader inherited platform:

- `app/` Flask + CRM + admin routes + sheet sync services
- `website/` storefront/frontend code
- legacy multi-industry and multi-tenant support

Those layers are still present in the repository, but they are **not** the main path used to evaluate the current Ferreteria bot. The active ferretería evaluation path is the CLI/WhatsApp runtime in `bot_sales/`.

## 3. Project structure and key files

### Runtime and orchestration

- `bot_cli.py`: CLI launcher
- `whatsapp_server.py`: WhatsApp launcher
- `bot_sales/runtime.py`: runtime tenant selection
- `bot_sales/bot.py`: main orchestrator and session state owner

### Ferretería-specific quoting logic

- `bot_sales/ferreteria_quote.py`: parsing, resolution, quote state helpers, formatting, acceptance handling
- `bot_sales/ferreteria_unresolved_log.py`: JSONL unresolved-term logger

### Knowledge and business data

- `tenants.yaml`: tenant index
- `data/tenants/ferreteria/profile.yaml`: tenant profile and business metadata
- `data/tenants/ferreteria/branding.json`: branding metadata
- `data/tenants/ferreteria/policies.md`: sales and operating policies
- `data/tenants/ferreteria/catalog.csv`: seed catalog
- `faqs.json`: FAQ knowledge base

### Business and persistence layer

- `bot_sales/core/database.py`: SQLite schema, CSV catalog loading, stock lookup
- `bot_sales/core/business_logic.py`: callable functions used by routing and LLM tool calls
- `bot_sales/faq.py`: keyword-based FAQ handler

### Prompt and instruction layer

- `bot_sales/core/tenant_config.py`: tenant prompt renderer
- `bot_sales/data/prompts/template_v2.j2`: primary dynamic prompt template
- `bot_sales/core/chatgpt.py`: static fallback prompt builder and function schema definitions

### Validation and review tooling

- `scripts/validate_tenant.py`: tenant structure validation
- `scripts/smoke_ferreteria.py`: live-path smoke checks
- `scripts/review_unresolved.py`: unresolved-term summary report
- `tests/test_ferreteria_setup.py`: focused ferretería behavior tests

### Inherited but adjacent infrastructure

- `app/`: admin APIs, CRM, public routes, stock sheet sync, catalog service
- `website/`: storefront/frontend assets

These are relevant for future evolution, but they are not the current bot’s primary runtime path.

## 4. Response generation flow

### High-level flow

The main live flow is implemented in `SalesBot.process_message()` in `bot_sales/bot.py`.

For the ferretería runtime, the effective order is:

1. Initialize or load in-memory session/context
2. Track analytics for the message
3. Run **ferretería pre-routing**
4. If not handled there, fall back to generic sales-planning logic
5. If still unresolved, use ChatGPT/function-calling

### Ferretería pre-routing

This is the most important part of the current bot behavior. For `tenant_id == "ferreteria"` or `industry == "ferreteria"`, `bot_sales/bot.py` routes the message through a product-first path before the inherited planning layer can ask generic qualification questions.

The pre-route currently handles:

- FAQ detection
- quote acceptance
- quote reset
- merge-vs-replace decisions for new items while a quote is open
- clarification of pending quote items
- remove/replace/add operations on quote items
- new multi-item quote requests
- single-item product requests
- broad project requests such as "presupuesto para un baño"

### Item parsing and resolution

`bot_sales/ferreteria_quote.py` is the main ferretería quote engine. It:

- normalizes accents and spelling variants,
- expands synonyms,
- parses simple multi-item lists,
- extracts quantity when possible,
- resolves products using `BusinessLogic.buscar_stock()`,
- re-scores candidates with stricter ferretería rules,
- and formats a quote response.

### Product resolution mechanics

The live resolver is a two-stage system:

1. `BusinessLogic.buscar_stock()` performs a flexible match over SQLite stock rows.
2. `ferreteria_quote.resolve_quote_item()` applies stricter ferretería-specific scoring:
   - significant token overlap,
   - category-family compatibility,
   - pack/unit safety,
   - ambiguity handling,
   - clarification prompts.

### Quote state

Quote state lives in memory inside `SalesBot.sessions[session_id]`.

Current session keys include:

- `active_quote`
- `quote_state`
- `pending_decision`
- `pending_clarification_target`
- `sales_intelligence_v1`

This is a pragmatic implementation for CLI and single-process runtime, but it is not persistent or distributed.

### LLM usage

If ferretería pre-routing does not fully handle the message, the bot can fall back to:

- the legacy sales-planning flow (`SalesFlowManager`)
- then ChatGPT-style function calling through `bot_sales/core/chatgpt.py`

In practice, the current ferretería experience relies mostly on deterministic Python routing rather than on free-form LLM reasoning.

## 5. Current system prompts and instruction layers

There are several instruction layers active or potentially active:

### Layer 1: tenant-derived prompt

`bot_sales/core/tenant_config.py` renders the main prompt using:

- business name
- store description
- tone
- visible categories
- policies markdown

Template file:

- `bot_sales/data/prompts/template_v2.j2`

This prompt is written in Spanish and still carries a strongly sales-oriented posture. It includes rules about:

- anti-hallucination,
- formatting,
- reservation flow,
- FAQ behavior,
- cross-sell,
- comparison handling,
- and required data collection.

### Layer 2: policy injection

The full contents of `data/tenants/ferreteria/policies.md` are injected into the prompt at render time.

### Layer 3: deterministic ferretería pre-routing

This is effectively stronger than the prompt for many messages. The pre-route in `bot_sales/bot.py` short-circuits the LLM path for FAQ, quoting, clarification, additive updates, and quote acceptance handling.

### Layer 4: legacy planning layer

The inherited `SalesFlowManager` still exists and can still act on messages that are not intercepted by the ferretería pre-route.

### Layer 5: function schemas

`bot_sales/core/chatgpt.py` defines callable tool schemas such as:

- `buscar_stock`
- `buscar_alternativas`
- `buscar_por_categoria`
- `crear_reserva`
- `confirmar_venta`
- `consultar_faq`
- `obtener_recomendaciones`
- `obtener_cross_sell_offer`
- `obtener_upselling`

### Layer 6: mock-mode heuristics

If `OPENAI_API_KEY` is missing or invalid, `ChatGPTClient` enters mock mode. In that case, responses are generated by handwritten heuristics in `bot_sales/core/chatgpt.py`.

### Practical conclusion

The current bot is **not prompt-led in the usual “LLM app” sense**. It is primarily:

- tenant-configured,
- policy-informed,
- and behaviorally constrained by explicit Python routing.

That is good for predictability, but it means knowledge and behavior changes still require technical edits in several places.

## 6. Knowledge sources

### 6.1 Catalog

Current primary product knowledge source:

- `data/tenants/ferreteria/catalog.csv`

The CSV is loaded into SQLite by `bot_sales/core/database.py` on startup.

Current catalog characteristics:

- small prototype-scale catalog
- approximately 17 SKUs
- categories include tools, fasteners, paint, plumbing, safety
- extra attributes stored in `attributes_json` and exposed as top-level fields

Important behavior:

- when stock is empty, the CSV fully seeds the DB
- when stock already exists, missing SKUs are merged via `INSERT OR IGNORE`
- existing rows are not fully re-synced from the CSV, so catalog edits are not a full bidirectional knowledge management system

### 6.2 FAQs

FAQ source:

- `faqs.json`

Access path:

- `bot_sales/faq.py`
- `BusinessLogic.consultar_faq()`

Mechanism:

- direct keyword matching
- no embeddings
- no semantic retrieval

This is efficient and cheap, but brittle when phrasing diverges from keyword lists.

### 6.3 Policies and rules

Policy source:

- `data/tenants/ferreteria/policies.md`

These rules exist in two forms:

1. injected into the system prompt
2. partially duplicated or approximated in Python logic

This creates some drift risk.

### 6.4 Hardcoded ferretería logic

The current bot depends heavily on hardcoded business logic in `bot_sales/ferreteria_quote.py`, including:

- synonym map
- spelling normalization
- category aliases
- ambiguity rules
- pack detection
- acceptance phrase detection
- merge/replace answer detection
- complementary suggestion rules

This is the main behavior engine for the current pilot shape.

### 6.5 Database

Primary runtime persistence:

- SQLite file defined by tenant profile, currently `data/ferreteria.db`

Tables include:

- `stock`
- `holds`
- `sales`
- `leads`
- `customers`
- analytics tables created by `bot_sales/analytics.py`

### 6.6 RAG and embeddings

There is **no active RAG pipeline or vector retrieval layer** in the current ferretería runtime path.

There are no active embeddings in the quote flow. The live bot does not use a vector store to retrieve catalog or FAQ content.

### 6.7 Inherited external knowledge paths

The repository contains adjacent infrastructure in `app/`:

- `app/services/catalog_service.py`
- `app/services/stock_sheet_sync.py`
- admin/public routes

This suggests a future path toward Google Sheets-backed catalog administration, but that is **not currently wired into the active `bot_sales` ferretería runtime**.

## 7. Testing, logs, and observability

### Automated tests

Current targeted test suite:

- `tests/test_ferreteria_setup.py`

Current observed result:

- `45 passed in 1.39s`

These tests cover:

- runtime tenant resolution
- profile loading
- FAQ routing
- product-first behavior
- simple quote generation
- pack/presentation safeguards
- broad project requests
- synonym handling
- clarification continuation
- unresolved item honesty
- additive quote changes
- FAQ during an open quote
- acceptance blocking when unresolved items remain
- merge-vs-replace and pending-decision behavior
- unresolved-term logging

This is much stronger than the earlier state of the project, but it is still a focused behavioral suite, not a full production confidence harness.

### Smoke testing

Current smoke script:

- `scripts/smoke_ferreteria.py`

Observed result:

- passed successfully

The smoke script exercises the live path and checks:

- greeting
- product/category-first routing
- FAQ routing
- structured multi-item quoting
- broad project guidance
- additive updates
- reset
- acceptance messaging
- parser safety
- pack semantics

### Tenant validation

Current tenant validation:

- `scripts/validate_tenant.py --slug ferreteria`

Observed result:

- passed successfully

This validates file presence, path consistency, profile structure, phone format, and basic catalog header shape. It is a configuration validation tool, not a behavioral test.

### Runtime observability

Current observability is lightweight and local:

- SQLite analytics tables via `bot_sales/analytics.py`
- text/JSON rotating logs via `bot_sales/core/logger.py`
- unresolved-term JSONL via `data/tenants/ferreteria/unresolved_terms.jsonl`
- unresolved-term summary via `scripts/review_unresolved.py`

Observed unresolved-term report:

- 92 logged events
- 82 unresolved
- 10 ambiguous
- top repeated terms include `mecha`, `taco fisher`, `electrovalvula`, `sellador`

### Observability limitations

- no centralized dashboard
- no structured quote audit trail
- no confidence metric per line item exposed to users or staff
- no persistent session timeline outside current process memory
- legacy `data/events.log` still contains older platform noise and is not a clean ferretería-specific signal source

## 8. Known issues and limitations

### Repository and naming issues

- The bot is requested here as "Ferretería Juli", but tenant/profile/branding/README still say "Ferreteria Central".
- The repository still contains a large inherited platform surface that is not clearly separated from the active runtime.

### Catalog and quoting scope

- The catalog is still small for a real ferretería pilot.
- Variant density is low, which hides future ambiguity problems.
- Many real construction/material requests will still miss the catalog.

### Matching and alternatives

- Product matching is stricter than before, but still built on a loose underlying DB matcher.
- Alternative selection is still basic. Example: after resolving `Mecha Madera 8mm`, the bot may present `Mecha Metal 10mm` as an alternative, which is same-family but not necessarily appropriate.

### Session and state handling

- Quote state is in-memory only.
- The bot can now ask whether to merge or replace when a new request arrives during an open quote.
- This is an improvement, but it also means the bot remains sensitive to session sequencing and process lifetime.

### Acceptance and downstream operations

- The bot can generate an acceptance-style reply for a quote.
- This is still mostly a conversational handoff, not a fully proven operational order-processing workflow.
- `confirmar_venta()` still contains demo-style artifacts such as emailing `cliente@demo.com`.
- `agregar_producto_extra()` is still inconsistent with the current sales schema.

### Admin and non-technical editability

- Knowledge updates are split across CSV, JSON, Markdown, YAML, and Python files.
- The live bot does not yet expose a non-technical editing layer for synonyms, prompt behavior, ambiguity rules, or acceptance flow.

### WhatsApp path

- WhatsApp bootstrap exists and looks runnable.
- It is less validated than CLI.
- Meta webhook verification still includes hardcoded defaults in the connector path.

## 9. Real examples of successful and failed interactions

The following examples were observed through live runtime calls to `bot.process_message()` in the ferretería tenant.

### Successful: simple multi-item quote

User:

`Quiero 2 siliconas y 3 teflones`

Observed behavior:

- The bot generated a structured preliminary quote.
- It selected `Silicona Neutra Transparente 280ml`.
- It selected `Cinta Teflon 12mm x 10m`.
- It calculated subtotals and a preliminary total.

Observed output summary:

- 2 silicona -> subtotal `$13.800`
- 3 teflon -> subtotal `$5.400`
- total preliminary -> `$19.200`

Assessment:

- This is a successful narrow-case quote flow.

### Successful: synonym resolution + clarification continuation

User:

1. `Necesito taco fisher y mecha`  
2. `Mecha de 8 mm para madera`

Observed behavior:

- `Taco fisher` resolved to `Tarugos Nylon N8 x50`.
- The bot flagged pack presentation instead of silently assuming unit semantics.
- `Mecha` stayed pending and asked for size/material.
- The follow-up updated the open quote and resolved the line to `Mecha Madera 8mm`.

Assessment:

- This is one of the strongest current multi-turn behaviors in the bot.

### Successful: broad request safely redirected

User:

`Pasame presupuesto para un baño`

Observed behavior:

- The bot did not invent products.
- It asked for materials or rubros such as pipes, fittings, sealants, fixtures, paint, tools, and electricity.

Assessment:

- This is a safe fallback, but not yet a complete quote builder for job-level requests.

### Successful: FAQ during active quote context

User:

`Hacen factura A?`

Observed behavior:

- The bot answered directly from FAQ content.
- It did so without falling into generic qualification questions.

Assessment:

- FAQ routing is simple but effective.

### Partial success: product browsing

User:

`Busco un taladro`

Observed behavior:

- The bot returned a category-style list under `Herramientas Electricas`.
- The list included:
  - `Taladro Percutor 13mm`
  - `Amoladora Angular 4 1-2 850W`
  - `Atornillador Inalambrico 12V`

Assessment:

- This is usable browsing behavior.
- It is not a precise single-item resolver yet.

### Failed / limited: unknown item

User:

`Necesito electroválvula industrial 3/4`

Observed behavior:

- The bot created a preliminary quote line in unresolved state.
- It explicitly said it could not find a clear match.
- It asked for more detail.

Assessment:

- This is a good failure mode because it is honest.
- It also confirms the catalog is far from complete for industrial/plumbing coverage.

### Failed / limited: quote-state interruption during new request

User:

1. `Quiero 2 siliconas y 3 teflones`  
2. `Necesito taco fisher y mecha`

Observed behavior:

- The bot did not immediately merge the new request.
- It asked:
  - whether to add the new items to the current quote
  - or start a new one

Assessment:

- This is structurally correct and safer than silent overwrite.
- It is still a sign that the quote state machine is becoming more complex and will need clearer operational UX for real pilot use.

## 10. Pending decisions / open technical questions

1. **Business identity**
   - Is the final deployed business name "Ferretería Juli" or "Ferreteria Central"?
   - This needs alignment across `tenants.yaml`, `profile.yaml`, `branding.json`, `README.md`, and any admin/runtime surfaces.

2. **Runtime boundary**
   - Should the `app/` admin/CRM stack become the official management layer for this bot, or remain separate?
   - Right now there are two adjacent architectures in one repo.

3. **Knowledge editing model**
   - Should synonyms, ambiguity rules, and complementary rules remain in Python?
   - Or should they move to editable configuration files or an admin UI?

4. **Catalog ownership**
   - Is the CSV the long-term source of truth?
   - Or is the future source of truth Google Sheets, CRM tables, or a database-backed catalog editor?

5. **Acceptance semantics**
   - When the bot says a quote is accepted, what should happen technically?
   - Create a lead?
   - Create a quote record?
   - Notify internal staff?
   - Reserve stock?

6. **Human handoff target**
   - What is the actual internal processing channel after acceptance?
   - WhatsApp team inbox?
   - CRM deal?
   - email?
   - manual copy/paste?

7. **Confidence visibility**
   - Should line-item confidence be shown internally, externally, or both?
   - This matters for safe pilot expansion.

8. **Persistence model**
   - Is in-memory session state acceptable for the next pilot phase?
   - Or do quotes need durable storage and recovery across restarts/channels?

---

# Gap Analysis

## What is missing for this bot to become trainable/editable by non-technical users

The current bot is still engineering-operated rather than business-operated.

Non-technical training/editing is blocked by the following realities:

- synonyms live in Python (`bot_sales/ferreteria_quote.py`)
- ambiguity rules live in Python
- complementary suggestion rules live in Python
- acceptance phrases live in Python
- routing rules live in `bot_sales/bot.py`
- prompt template is in Jinja + Markdown-style instructions
- catalog is stored in CSV and then loaded into SQLite
- FAQs are in JSON
- policies are in Markdown

This means a non-technical operator would currently need developer help to change:

- what the bot recognizes,
- how it clarifies,
- what it suggests,
- how it labels uncertainty,
- and how it reacts to many user phrasings.

### Minimum missing capabilities

To make the bot editable by non-technical users, it would need:

- a catalog editor or spreadsheet sync officially wired to runtime
- an FAQ editor
- a synonym/alias editor
- a clarification-rule editor
- a preview/test console that shows how a change affects live quote behavior
- versioning and rollback for business edits

## What would be needed to support a teaching/admin interface

A realistic teaching/admin interface would need at least these domains:

### 1. Catalog management

- add/edit/deactivate SKU
- define sell unit and pack unit separately
- define variant dimensions explicitly: size, material, use, finish, brand
- define substitute relationships and compatibility constraints

### 2. Language and synonym management

- add term -> canonical item mapping
- see unresolved-term frequency from `unresolved_terms.jsonl`
- approve new synonyms from pilot traffic
- define blocked or misleading terms

### 3. Clarification design

- define what missing information is required for each item family
- define which follow-up question should be asked first
- define when the bot should stop guessing and escalate

### 4. Quote review and handoff

- inspect quote state
- see which lines are high confidence vs partial vs unresolved
- create a human review task from accepted or blocked quotes

### 5. Safe test harness

- run a scenario and compare before/after behavior
- keep gold test cases for pilot-critical phrasing

The repository contains some adjacent building blocks in `app/`:

- admin routes
- catalog service
- stock sheet sync
- CRM models and UI

But those are not currently the governing layer for the active Ferreteria runtime.

## What parts are too coupled

### 1. Quote behavior and business language

`bot_sales/ferreteria_quote.py` currently couples:

- parsing,
- matching strategy,
- quote state mutation,
- clarification behavior,
- complementary logic,
- acceptance behavior,
- and response formatting.

This is efficient for shipping, but it makes safe incremental change harder.

### 2. Knowledge and behavior

Knowledge is split across:

- CSV
- JSON
- Markdown
- YAML
- SQLite
- Python constants and regexes

That makes it difficult to know what the real source of truth is for any given behavior.

### 3. Runtime routing and session state

`bot_sales/bot.py` owns:

- tenant behavior checks,
- quote-state machine,
- FAQ routing,
- project request fallback,
- merge/replace handling,
- clarification targeting,
- and the gateway to LLM function calling.

This is workable now, but it centralizes too many responsibilities.

### 4. Repository scope

The repository still mixes:

- current active Ferreteria runtime,
- broader inherited sales-bot platform,
- admin/CRM stack,
- website/storefront code,
- multi-industry experimentation.

That makes external review, onboarding, and safe ownership transfer harder than it needs to be.

## What should remain as-is

Some current design choices are good and should be preserved:

### Product-first ferretería pre-route

This is the right direction. It materially improved the bot by preventing the generic planning layer from hijacking basic product requests.

### Deterministic FAQ handling

The keyword FAQ path is simple, cheap, and predictable. It should stay, even if it later gains better matching.

### Unresolved-term logging

The new JSONL unresolved review loop is small and very practical. It is a good pilot-facing mechanism and should remain.

### CSV -> SQLite seed model

For a small pilot, this is fine. The issue is not the existence of CSV; the issue is that it is not yet embedded in a clear admin workflow.

### Focused behavioral tests

The current ferretería-specific tests are a strong asset. They should remain the backbone of safe iteration.

## Logical roadmap

### V1: Safe controlled quoting core

Goal: make the current bot safe enough for a controlled, human-reviewed pilot.

Focus:

- stabilize quote-state transitions
- define explicit quote line confidence states
- improve line-item targeting and clarification continuation
- strengthen product resolution for current catalog families
- formalize acceptance as "human review requested", not "order operationally confirmed"
- persist quotes and handoff records

Outcome:

- reliable preliminary quote bot for a limited catalog and supervised internal team

### V2: Business-editable operations layer

Goal: allow non-technical staff to maintain most of the bot’s practical knowledge.

Focus:

- move synonyms and clarification rules out of Python into editable config or admin-backed storage
- connect unresolved-term review into an approval workflow
- make catalog updates manageable through sheet/admin tooling
- add internal quote review and confidence visibility

Outcome:

- operators can teach and maintain the bot without code changes for most day-to-day improvements

### V3: Multi-business productization

Goal: make the ferretería implementation a reusable pattern for other businesses.

Focus:

- separate business-agnostic core from industry packs
- standardize knowledge contracts across catalog, FAQ, policies, and clarification rules
- formalize channel adapters and handoff integrations
- define admin UX for tenant setup, training, and validation

Outcome:

- the system becomes a configurable quoting platform, not just a ferretería bot

## Bottom-line assessment

This bot is already more than a demo shell. It has a real ferretería runtime, a real tenant profile, a real quote state machine, targeted validations, and concrete evidence of useful product-first behavior.

At the same time, it is still a **developer-operated prototype**, not yet a business-operated quoting system. The most important architectural gap is not "more AI"; it is the lack of a clean boundary between:

- editable business knowledge,
- deterministic quote logic,
- and operational handoff.

That boundary will determine whether this project becomes maintainable and teachable, or remains a code-managed pilot bot.
