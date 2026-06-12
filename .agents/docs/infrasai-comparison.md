# Our System vs. InfrasAI — Gap Analysis & Learning Roadmap

**Purpose**: Track how close this learning project is to InfrasAI's production product, as a checklist of what to build next.
**Last updated**: 2026-06-12
**Reference**: [infrasai.io](https://www.infrasai.io/) · [/partners](https://www.infrasai.io/partners) · [/resources](https://www.infrasai.io/resources)

---

## TL;DR

We have built a **faithful replica of InfrasAI's agent pipeline** (the six agents: Extract → Interpret → Map → Build → Test → Support). That is the *factory*. InfrasAI's actual *product* is the **abstraction layer + SDK** that sits on top of that factory and serves hundreds of carriers and distributors through one clean data model.

**We built the map. They built the highway on top of the map.**

Completion estimate: **~40% of the conceptual product, ~15% of the production product.**

---

## How To Read This Doc

Each section is one capability area. Inside:
- **What InfrasAI does** — their behavior (from public site + inference)
- **What we have** — current state in our codebase
- **Checklist** — concrete items to build, `[ ]` unchecked = missing
- **Effort** — rough size (S / M / L / XL)

Then at the bottom: a **prioritized roadmap table** answering "what to learn/build next, in order."

---

## 1. The Agent Pipeline (Extract → Interpret → Map → Build → Test)

This is the part we have built well. Documented for completeness.

**What InfrasAI does**: Six modular AI agents process raw requirements in any format and produce system-ready workflows.

**What we have**: All six agents implemented (`backend/app/agents/`), orchestrated by LangGraph with human-in-the-loop gates.

**Checklist**:
- [x] Extract agent (deterministic lxml XML parsing)
- [x] Interpret agent (LLM domain enrichment)
- [x] Map agent (LLM schema matching + confidence scoring)
- [x] Build agent (transform spec compilation)
- [x] Test agent (JSON Schema QA validation)
- [x] Support agent (RAG + tool-use Q&A)
- [x] LangGraph orchestration with checkpointing
- [x] Human review gates (4 interrupts)
- [x] Audit trail (AuditEvent / ReviewAction / LLMCall)
- [x] Confidence scoring (heuristic + LLM composite)

**Status: COMPLETE.** This is our strength. Everything below is what's missing.

---

## 2. The Abstraction Layer / Single Data Model ⭐ THEIR CORE MOAT

**What InfrasAI does**: "InfrasAI removes all complexity – all carrier logic, mapping, workflows." Every partner sees ONE clean, normalized data model regardless of which carrier is behind it. This is the heart of their value — it collapses the N×M integration matrix (N carriers × M distributors) into N+M.

**What we have**: Nothing. Each run maps ONE source XML to ONE target schema. No concept of a canonical model that many carriers map into and many consumers read from.

**Why it matters**: This is the single most important difference. The AI pipeline is increasingly commodity; the abstraction layer is the actual business.

**Checklist**:
- [ ] Define a **Canonical Data Model** (CDM) — one normalized schema all carriers map into (e.g. canonical `Policy`, `Party`, `Coverage` entities)
- [ ] Carrier mappings target the CDM, not a per-distributor schema
- [ ] Distributor "views" project FROM the CDM to each distributor's required shape
- [ ] Decouple `TargetSchema` into two layers: `CanonicalModel` + `DistributorView`
- [ ] Mapping reuse — once Carrier A → CDM is built, it serves ALL distributors
- [ ] Versioning of the CDM independent of carrier/distributor schemas

**Effort: XL** (this is an architecture change, not a feature)

---

## 3. Many-to-One / Fan-Out Architecture

**What InfrasAI does**: Hundreds of carriers normalize into one interface; hundreds of distributors consume it. Add a new distributor → it instantly works with every existing carrier (no per-carrier rebuild).

**What we have**: 1 source → 1 target per run. No fan-out. Adding a new consumer means re-running everything.

**Checklist**:
- [ ] Data model supports many `CarrierBinding` rows per `CanonicalModel`
- [ ] Data model supports many `DistributorView` rows per `CanonicalModel`
- [ ] A single completed carrier mapping is reusable across N distributors without re-running the LLM
- [ ] "Add distributor" flow that requires zero carrier-side work
- [ ] Run/job model that separates "carrier onboarding" from "distributor consumption"

**Effort: L** (depends on #2 being done first)

---

## 4. SDK / Partner Integration Layer

**What InfrasAI does**: "100% free SDK and UI libraries." Partners embed digital experiences in ~10–15 lines of code. Headless workflows exposed through `pageRules` / `pageRuleGroup` components. The SDK hides all carrier logic.

**What we have**: A REST API (`routers/`) and a React review UI. No published SDK, no embeddable components, no headless workflow runtime for third parties.

**Checklist**:
- [ ] Define a stable public API contract (versioned, documented — OpenAPI)
- [ ] Generate a typed client SDK (TypeScript at minimum)
- [ ] Headless workflow runtime — execute a workflow without our UI
- [ ] Embeddable UI components (the `pageRules` / `pageRuleGroup` equivalent)
- [ ] "10 lines of code" quickstart — partner integrates without knowing internals
- [ ] Auth / API keys / partner tenancy for SDK consumers

**Effort: L**

---

## 5. Natural-Language Rule Editing (Support Copilot)

**What InfrasAI does**: Business teams "update rules in natural language, preview impacts, and redeploy in minutes." Support Copilot works "in English and in code." Non-engineers maintain the system.

**What we have**: `support.py` answers questions and proposes SINGLE-field `EditIntent`s queued for human approve/reject. It cannot author whole rules, preview impact, or redeploy.

**Checklist**:
- [ ] NL → rule authoring (not just single-field edits — whole transform/mapping rules)
- [ ] Impact preview ("if I change this rule, here's what breaks / re-maps")
- [ ] Redeploy loop — approved NL change re-runs affected mappings automatically
- [ ] Rule versioning + rollback
- [ ] Diff view (before/after rule state) for business users

**Effort: M** (builds on existing support agent + needs a rule engine — see #7)

---

## 6. Multi-Format Document Ingestion

**What InfrasAI does**: Ingests Excel, PDF, "PDF tags," ACORD models, XML. Document-AI upstream (OCR, layout parsing, table extraction).

**What we have**: Clean ACORD XML only (`extract.py` is pure lxml). No PDF, no Excel, no OCR.

**Checklist**:
- [ ] PDF text extraction (e.g. `pdfplumber` / `unstructured`)
- [ ] PDF layout / table extraction (forms, tagged PDFs)
- [ ] Excel / CSV ingestion → field extraction
- [ ] OCR for scanned documents
- [ ] Format router — detect input type, dispatch to correct extractor
- [ ] Normalize all formats into the same `ExtractedField` shape

**Effort: L**

---

## 7. Transform / Rule Expressiveness

**What InfrasAI does**: "Converting complex business logic into system-ready processes." Real carrier rules: conditionals, lookups, multi-field math, date math, code-table translation.

**What we have**: `_TRANSFORMS` = 5 string ops (`to_number`, `to_date_iso`, `uppercase`, `lowercase`, `trim`). No conditionals, no multi-field, no lookups.

**Checklist**:
- [ ] Conditional transforms (`if source X == Y then Z`)
- [ ] Multi-field transforms (combine FirstName + LastName → FullName)
- [ ] Code-table lookups (ACORD `tc="2"` → "WholeLife")
- [ ] Date math / format conversion beyond passthrough
- [ ] A safe expression DSL or sandboxed evaluator (NOT `eval()` — security)
- [ ] Default values / fallbacks for missing fields
- [ ] Validation rules separate from transform rules

**Effort: M–L**

---

## 8. Multi-Tenancy & Compliance

**What InfrasAI does**: SOC 2 Type 2. Real multi-tenant isolation. Serves regulated carriers (Guardian, Transamerica).

**What we have**: Models have `tenant_id` columns but no migration wires them up (deferred Alembic gap). No tenant isolation enforced. Audit model exists but not operationalized.

**Checklist**:
- [ ] Wire `tenant_id` into a real Alembic migration
- [ ] Enforce tenant isolation at the query layer (row-level)
- [ ] **PII handling — mask SSN / DOB before they reach LLM prompts** ⚠️ (current real gap)
- [ ] Encryption at rest for sensitive fields
- [ ] Audit log retention + export for compliance
- [ ] Role-based access control (reviewer vs. admin vs. partner)

**Effort: M** (PII masking alone is S and should be done first — it's a correctness bug)

---

## 9. Eval / Regression at Scale

**What InfrasAI does**: Implied — at hundreds of carriers, they must regression-test mappings when prompts or schemas change.

**What we have**: `eval/golden/` with 14 fixtures + a precision/recall runner. Good seed, small scale.

**Checklist**:
- [x] Golden fixture harness (source + expected mappings)
- [x] Precision / recall / confidence calibration metrics
- [ ] Regression gate — "did this prompt change break existing mappings?"
- [ ] Per-carrier eval suites (not one global set)
- [ ] Schema-drift detection — alert when a carrier changes a field
- [ ] CI integration — eval runs on every prompt/schema change
- [ ] Scale fixtures from 14 → hundreds

**Effort: M**

---

## Summary Scorecard

| # | Capability | Have | Missing | Effort |
|---|---|---|---|---|
| 1 | Agent pipeline | ✅ Full | — | done |
| 2 | **Abstraction layer / CDM** | ❌ None | Everything | XL |
| 3 | Many-to-one fan-out | ❌ None | Everything | L |
| 4 | SDK / partner layer | ⚠️ REST only | SDK, headless, embed | L |
| 5 | NL rule editing | ⚠️ Single-field | Authoring, preview, redeploy | M |
| 6 | Multi-format ingest | ❌ XML only | PDF, Excel, OCR | L |
| 7 | Transform expressiveness | ⚠️ 5 ops | Conditionals, lookups, DSL | M–L |
| 8 | Multi-tenancy / compliance | ⚠️ Partial | Isolation, PII masking | M |
| 9 | Eval at scale | ⚠️ Seed | Regression, drift, CI | M |

---

## What To Build Next — Prioritized Learning Roadmap

**Your question: SDK layer or many-to-one first?**

**Answer: Many-to-one (via the Canonical Data Model) first.** Reason: the SDK is a *delivery mechanism* for the clean data model. If there is no canonical model underneath, the SDK has nothing clean to expose — you'd just be wrapping the existing 1-to-1 pipeline. The abstraction layer is the foundation everything else (SDK, fan-out, NL rules) sits on. Build the thing being abstracted before building the abstraction's API.

### Recommended Build Order

| Order | Build | Why this order | What you'll learn | Effort |
|---|---|---|---|---|
| **0** | **PII masking** (#8 partial) | It's a correctness/security bug, not a feature. Do it before anything touches real data. | Data classification, prompt-safety, field redaction | S |
| **1** | **Canonical Data Model** (#2) | The foundation. Everything InfrasAI does sits on "one clean model." Without it, fan-out and SDK are impossible. | Schema design, normalization, the N×M→N+M insight — **the core moat** | XL |
| **2** | **Many-to-one fan-out** (#3) | Once a CDM exists, make one carrier mapping serve many distributors. This is where the value compounds. | Reuse architecture, projection/view patterns | L |
| **3** | **Transform DSL** (#7) | Real carrier logic needs more than 5 string ops. Needed before NL rule editing is meaningful. | Expression engines, safe evaluation (no `eval`), rule modeling | M–L |
| **4** | **NL rule editing** (#5) | Now that rules are expressive (DSL), let business users author them in English. | LLM → structured DSL, impact analysis, redeploy loops | M |
| **5** | **SDK / partner layer** (#4) | Now there IS a clean model worth exposing. Wrap it in an SDK. | API design, client codegen, headless runtimes, embeddable UI | L |
| **6** | **Multi-format ingest** (#6) | Broaden inputs once the core is solid. | Document AI, OCR, layout parsing | L |
| **7** | **Eval at scale** (#9) | Continuous — grow alongside everything above. | Regression testing, drift detection, CI for LLM systems | M |

### The One Insight To Internalize First

The **N×M → N+M collapse** is the whole game.

- Without abstraction: N carriers × M distributors = N×M integrations to build and maintain.
- With a canonical model: each carrier maps to the CDM once (N), each distributor reads from the CDM once (M) = N+M.

At 100 carriers × 100 distributors: **10,000 integrations → 200**. That 50× reduction is InfrasAI's entire pitch. Build the Canonical Data Model and you've built the thing that makes that math work. Everything else is delivery.

### Concrete First Step (Milestone "CDM-1")

1. Pick 2 carrier formats you already have (`acord_life_sample.xml`, `acord_pc_real_sample.xml`).
2. Design ONE canonical model that both map into (canonical `Policy` + `Party` + `Coverage`).
3. Change the map agent target from `target_distributor_a.json` to the CDM.
4. Add a projection step: CDM → `target_distributor_a.json` AND CDM → `target_distributor_b.json` from the SAME mapped run.
5. Prove: one carrier run now serves two distributors with no extra LLM calls.

That milestone alone teaches you 80% of what makes InfrasAI's architecture different from a plain LLM pipeline.
