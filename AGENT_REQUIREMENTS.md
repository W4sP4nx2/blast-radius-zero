# Agent Requirements and Guardrails

This document defines the acceptance contract for AI behavior in Blast Radius Zero. Models propose plans and code; trusted application code validates, admits, dispatches, observes and cleans up work. Untrusted code executes only inside a sandbox.

The limits below are required defaults. Runtime code enforces them; documentation alone does not prove enforcement. Existing observations and outstanding target-host checks are recorded in [TESTING.md](TESTING.md), [CHECKLIST.md](CHECKLIST.md) and the [local verification report](verification/local-2026-11-04.md).

## 1. Core architectural boundaries

- **Proposal authority only:** models may produce schema-constrained plans, Python source and explanations. They cannot authorize their own execution, approval or infrastructure changes.
- **Structural validation in the control plane:** FastAPI and the coordinator may validate JSON, fields, ownership and policy. They must never execute generated Python as part of validation. Execution belongs exclusively in the sandbox.
- **Administrator-owned infrastructure:** images, mounts, networks, capabilities, resource limits, host commands and cleanup are fixed by trusted configuration. No model or public request can override them.
- **Bounded context:** do not send unrestricted terminal history, full browsing sessions or unlimited images to a model. Treat page text, screenshots, logs and model output as untrusted evidence.
- **Secret separation:** do not pass provider credentials, Redis credentials, host files or the Docker socket into execution sandboxes. Image/runtime environment variables may remain; an empty environment is not the security claim.
- **Independent enforcement:** Python has external networking disabled. Browser operations require approved destinations, Squid and host destination filtering; a page interceptor cannot replace those boundaries.

## 2. Lightweight AI controls and rate limits

Use these rows as direct PR acceptance criteria. Rate limits use fixed-window Redis bucket keys with expiration, not a rolling-window or monetary billing guarantee.

| ID | Control | Required default | Enforcement / acceptance criterion |
| --- | --- | --- | --- |
| A01 | Task starts | 6 per IP per minute | Expiring Redis counter rejects excess admission attempts |
| A02 | Live-AI tasks | 3 per IP per hour | Independent Redis counter; explicit presets bypass inference quota only |
| A03 | Global provider requests | 20 per minute | Global Redis counter covers provider requests across tasks |
| A04 | Concurrent model calls | 2 maximum | Single coordinator model semaphore; demonstrate the bound under concurrent calls |
| A05 | Concurrent sandbox tasks | 2 maximum, including at most 1 browser | Single coordinator task/browser admission; do not multiply limits by adding processes |
| A06 | Waiting queue | 8 tasks maximum | Atomic queue admission rejects overflow with a structured capacity response |
| A07 | Planning output | 1,024 tokens | Provider request ceiling; validate JSON before dispatch |
| A08 | Code generation or repair output | 2,048 tokens | Provider request ceiling; source also satisfies D01 |
| A09 | Summary or vision verdict output | 512 tokens | Provider request ceiling; output is explanatory, not authorization |
| A10 | Recovery allowance | At most 2 additional recovery attempts per task | One shared allowance across provider, schema and eligible code recovery; never reset per stage |
| A11 | Total provider requests | At most 5 per task | Shared task counter counts attempted requests, including model-catalog validation; it is not five calls per role |

Disable automatic HTTP/client-library retries so hidden attempts cannot multiply these limits. The recovery allowance permits an initial attempt plus at most two additional recoveries, subject to the five-request ceiling.

Do not add a lifetime dollar ledger or price reservations. Provider-reported usage is observational; actual charges are monitored through Vultr.

## 3. Planning, validation and repair rules

- Version prompts, schemas and preset plans in Git alongside application code.
- Validate generated JSON against strict Pydantic contracts before dispatch. Structural validity does not establish that generated code is safe.
- The request selects the execution pattern. The code prompt asks for `{"code":"…"}`. The browser prompt asks for `research` or `prepare_form` using the `BrowserPlan` fields. The Python byte bound applies to generated plans and direct submissions. [Prompts](core/brz/ai.py) · [Schemas](core/brz/models.py)
- Treat malformed or truncated output as a failed attempt. Any recovery consumes the same task-level allowances in Section 2.
- Permit code repair only for eligible ordinary diagnostics. The current implementation considers failed live-AI code with `SyntaxError`, `IndentationError` or `NameError` diagnostics; it does not provide a generic retry for every failure.
- Do not automatically repair policy denials, timeout, OOM/resource exhaustion or invalid provider credentials.
- Never let model output, sandbox stdout, screenshots or page content change policy, mint a permit or create a verified containment event. Validator and proxy enforcement events use a separate trusted channel.
- Do not invent missing input data or summarize an article that was not fetched. Identify sample data, headline-only evidence and blocked sources explicitly.

## 4. Circuit breaker and dependency failure

1. Five consecutive provider timeouts or server errors open the provider circuit.
2. While open, pause live inference for 60 seconds and return a reason, retry timing and available preset IDs.
3. After the pause, admit one recovery-probe caller. Success closes the circuit; another provider failure reopens it. Probe requests still consume ordinary request allowances.
4. Respect provider `Retry-After`. Visitor quota exhaustion is not a provider outage and must not open the global circuit.
5. Rejected credentials or unknown configured model IDs disable live inference until configuration is corrected.
6. If Redis or required shared state is unavailable, reject new execution admission. Do not switch to unrestricted local counters.

## 5. Data and sandbox resource boundaries

Use both tables as direct acceptance criteria. A deadline is monitored by the coordinator; verify termination and cleanup on the target host, and test controller/daemon failure recovery separately.

| ID | Input/output | Required limit | Acceptance criterion |
| --- | --- | --- | --- |
| D01 | Python source | 64 KiB, measured as UTF-8 bytes | Reject empty/oversized submissions; do not execute them during validation |
| D02 | CSV upload | 2 MiB | Reject oversized, binary or non-UTF-8 input; require session ownership |
| D03 | Combined stdout/stderr | 1 MiB per task | Bound buffering/events, terminate output floods and render output as text |
| D04 | Artifact total | 8 MiB per task | Reject excess before publication; maintain session-scoped downloads |
| D05 | Individual artifacts | 2 MiB each, at most 16 files | Allow supported regular files only; reject traversal, links and special files |
| D06 | Artifact retention | 15 minutes | Expire blobs and deny subsequent access |
| D07 | User prompt | 4,000 characters | Validate before model dispatch |
| D08 | Structured model user context | 16,000 characters | Bound assembled context; do not append unlimited history |
| D09 | Vision input | 512 KiB screenshot; fixed 1280 × 720 browser viewport | Reject oversized vision input; viewport screenshot is not an unrestricted full-page capture |
| D10 | Public execution/upload request body | 3 MiB | Enforce the body limit for chunked requests as well as declared lengths |
| D11 | Approval lifetime | 5 minutes after preparation | Bind session, destination, field values and form revision; require a new preparation after expiry/change |

| Policy | Python sandbox | Browser sandbox |
| --- | --- | --- |
| External networking | Disabled with `network_mode="none"`; loopback remains | Isolated internal network; approved HTTPS through Squid and host filtering |
| Memory / combined memory+swap | 256 MiB / 256 MiB | 512 MiB / 512 MiB |
| CPU / PIDs | 0.5 CPU / 64 PIDs | 1 CPU / 256 PIDs |
| Execution deadline | 10 seconds | 30 seconds per stage |
| Temporary scratch | 64 MiB tmpfs | 128 MiB tmpfs and private bounded shared memory |
| Identity and root filesystem | Non-root; read-only root; dropped capabilities; no-new-privileges | Same, with Chromium sandbox enabled and the required seccomp profile |
| Lifecycle | Explicit termination/removal and startup reaping | Fresh browser/network per stage; remove browser/proxy/network on every path |

Artifacts are transferred through a fixed container-exec helper and parsed as a bounded archive in memory. They are never extracted to the host filesystem. This does not make their contents trusted.

## 6. Presets and graceful degradation

- Presets are deterministic stored plans labelled `source: "preset"`. They run actual containers and make no inference requests.
- Presets use the same resource, logging, artifact and approval controls as other work. Inference unavailability does not waive sandbox capacity or shared-state requirements.
- When AI is disabled, throttled or unavailable, preserve the visitor's original request and offer explicit preset choices with a structured reason and retry timing where applicable.
- Never silently substitute an unrelated preset, mock result, cached screenshot or invented summary for the requested task.
- Prove zero inference using task-level provider instrumentation, not aggregate billing alone.

## 7. Approval-gated actions

Preparation is not authorization. A first browser fills the project-owned form, captures a screenshot and returns exact values/revision. The control plane stores the session-owned pending action and destroys that browser.

The owning visitor must explicitly approve the displayed destination, values and screenshot within five minutes. A fresh browser revalidates the form. The form service independently checks the payload-bound, short-lived permit and creates one receipt atomically; duplicate submissions return that receipt.

Models cannot approve, mint permits or change approved fields. Vision observations are advisory. Logins, payments and third-party submissions remain outside this version.

## 8. Capability orchestration and handoffs

These are logical capabilities of the existing implementation, not separate deployed agent services. All model modes share one `ModelClient` and task-level allowances under one coordinator.

| Capability / actor | Allowed responsibility | Output / handoff | Authority withheld |
| --- | --- | --- | --- |
| Planner / code generator | Interpret the bounded task and propose Python or a fixed browser operation | `CodePlan` or `BrowserPlan` → deterministic validation | Host execution, Docker policy and arbitrary browser scripts |
| Repair mode | Propose a correction for an eligible failure within the shared allowance | Validated replacement code → a fresh sandbox | Resetting budgets or bypassing policy/resource outcomes |
| Summary mode | Explain supplied executed evidence | Plain text → session-owned result | Inventing results or issuing actions |
| Vision mode | Describe a bounded screenshot for configured live-AI tasks | Advisory observation → result display | Approval, credential access or permission changes |
| API / validators | Check schema, session/CSRF, ownership, quotas and initial destination policy | Admitted task → bounded Redis queue | Executing generated Python |
| Trusted coordinator | Own model dispatch and Docker lifecycle; collect bounded evidence | Sandbox outcome, artifacts and trusted policy events → API/SSE | Accepting model-specified infrastructure flags |
| Fixed browser worker | Research approved pages, prepare a form or execute an approved submission | Screenshot, source receipts and observed form fields | Arbitrary injected scripts, provider keys or self-approval |
| Human and form service | Approve exact prepared values; independently enforce the permit and commit once | Session-bound approval → one trusted receipt | Broad account access or unrelated effects |

Code path: **request → admission → proposal or explicit preset → structural/policy validation → sandbox → bounded evidence → optional explanation**.

Action path: **prepare → screenshot/revision/values → destroy → human approval → fresh browser/revalidation → permit-enforced commit → receipt**.

## 9. Pull-request acceptance for AI orchestration and testing

The [AI orchestration and testing contributor](docs/participants/ai-testing.md) uses Section 2 and Section 5 directly when reviewing agent-related changes.

- [ ] Identify every affected A/D requirement row and the enforcement location.
- [ ] For each changed limit, record tests below, at and above its boundary; include UTF-8 byte size, concurrent calls or expiry where relevant.
- [ ] Demonstrate shared retry/call allowances and zero provider requests for explicit presets; do not infer this from a billing dashboard.
- [ ] Include provider error, dependency loss, ownership and approval regressions when their handoffs change.
- [ ] Preserve explicit termination, bounded transfers and cleanup on success, error, cancellation and restart.
- [ ] Keep host policy in checked-in scripts; never flush Docker-managed chains.
- [ ] Link the command, environment, result and sanitized evidence. Mark blocked/skipped checks explicitly instead of claiming a pass.
- [ ] Run relevant application checks and isolated Linux Docker probes for runtime changes. Update requirements, contributor guardrails and observed results when behavior changes.

This document-only addition does not create new test results. Existing local application and Python-container evidence does not verify the outstanding browser/firewall or Vultr deployment gates.

Docker shares the host kernel. Describe specific tested controls and their limits; do not claim mathematical proof of zero host risk.
