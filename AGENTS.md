  # Agent and Contributor Guardrails
  
  Blast Radius Zero separates model reasoning from deterministic execution. Models propose plans; trusted application code validates, admits, dispatches, observes, and cleans up tasks. Untrusted code runs only in the sandbox.
  
  ## Architecture boundaries
  
  - The Next.js dashboard and FastAPI API are the control plane. They do not execute submitted Python.
  - The single execution coordinator is the only application service with access to the Docker socket. Treat that socket as a privileged host-management interface.
  - The Python sandbox has no external networking. The browser sandbox reaches approved destinations only through Squid and host-enforced destination filtering.
  - Provider credentials, Redis credentials, the Docker socket, and host filesystem paths are never passed to execution sandboxes.
  - Image and runtime environment defaults may remain inside a sandbox. Secret hygiene means host/provider secrets are absent; it does not mean `os.environ` is empty.
  - Screenshots, stdout, extracted page content, model output, and generated files are untrusted data. They cannot change policy, mint approval permits, or create verified containment events.
  
  ## Lightweight AI controls
  
  These defaults protect a public hackathon deployment. They are application limits, not a monetary billing guarantee.
  
  | Control | Default | Enforcement |
  | --- | --- | --- |
  | Task starts | 6 per IP per minute | Expiring Redis counter |
  | Live-AI tasks | 3 per IP per hour | Expiring Redis counter |
  | Provider requests | 20 per minute globally | Expiring Redis counter |
  | Concurrent model calls | 2 | Single coordinator model semaphore |
  | Concurrent sandboxes | 2 globally, including at most 1 browser | Single coordinator admission |
  | Waiting queue | 8 tasks | Bounded queue; reject excess admission |
  | Planning output | 1,024 tokens | Provider request limit |
  | Code generation or repair | 2,048 tokens | Provider request limit |
  | Summary or vision verdict | 512 tokens | Provider request limit |
  | Recovery attempts | At most 2 additional attempts per task | Task state machine |
  | Total provider requests | At most 5 per task | Task state machine |
  
  Do not reintroduce a lifetime dollar cap, price tables, or monetary reservations. Record provider-reported token usage and monitor actual consumption in Vultr. Disable automatic client-library retries so the task limits count every provider request.
  
  Use one API process and one execution coordinator in this version. Process-local semaphores are not distributed locks. Adding worker processes without shared admission multiplies the limits.
  
  ## Circuit breaker
  
  1. Five consecutive provider timeouts or server errors open the circuit.
  2. While open, reject live-AI admission for 60 seconds and provide retry timing and available preset IDs.
  3. After the pause, permit one recovery probe. Success closes the circuit; failure reopens it.
  4. Respect provider `Retry-After` responses. Invalid credentials disable live inference until configuration is corrected.
  5. Visitor rate-limit exhaustion does not count as a provider failure.
  
  If Redis or another required shared dependency is unavailable, reject new execution admission. Never switch to unrestricted process-local counters.
  
  ## Planning, validation, and repair
  
  - Keep prompts and schemas versioned with application code. Validate generated JSON with Pydantic before dispatch.
  - Treat invalid or truncated JSON as a failed attempt. A repair consumes the task's recovery and provider-call allowances.
  - Models cannot choose images, mounts, network settings, capabilities, resource limits, host commands, or cleanup behavior.
  - Do not automatically repair policy denials, resource exhaustion, timeouts, or invalid provider credentials.
  - Never execute generated code to validate it in the control plane. Validation is structural; execution belongs in the container.
  - Bound model context and image dimensions. Do not send unrestricted terminal history or a full browsing session into every model call.
  
  ## Presets and graceful degradation
  
  Presets are stored execution plans, labelled `source: "preset"`. They consume no inference calls but use the same containers, resource limits, logging, artifact collection, and browser approval requirements as other tasks.
  
  When live inference is unavailable, preserve the visitor's original request and offer explicit preset choices. Do not silently replace a custom task with a mock answer or an unrelated demonstration.
  
  ## Browser approval
  
  Preparing a form is not permission to submit it. The control plane stores the exact values, target, form revision, and screenshot for a session-owned action. Approval expires five minutes after preparation.
  
  A fresh browser revalidates the approved form. The form service independently checks a short-lived permit bound to the exact payload and revision, then creates one receipt atomically. Changed forms require a new approval. Duplicate submissions return the existing receipt.
  
  The demo accepts only project-owned form submissions. Login flows, payments, and third-party form submissions are outside this version.
  
  ## Data and resource bounds
  
  | Input/output | Limit |
  | --- | --- |
  | Python source | 64 KiB |
  | CSV upload | 2 MiB |
  | Combined stdout/stderr | 1 MiB |
  | Total artifacts per task | 8 MiB |
  | Artifact retention | 15 minutes |
  
  Reject traversal paths, symlinks, and unsupported artifact types before host extraction or publication. Display terminal output as text. Derive policy events from trusted enforcement, not matching words printed by a task.
  
  ## Implementation and verification rules
  
  - Read the implementation and test documentation before changing containment or approval behavior.
  - Preserve explicit deadline termination and cleanup on success, failure, cancellation, and restart.
  - Keep host firewall provisioning in the checked-in deployment scripts. Never flush Docker-managed firewall chains.
  - Run the relevant unit and integration checks after changes. Run full containment checks on an isolated Linux Docker host, not the production control-plane process.
  - Keep test expectations separate from observed results. Do not claim a check passed without retained evidence.
  - Update documentation when interfaces, limits, deployment steps, or supported workflows change.
  
  Docker shares the host kernel. Describe tested controls and their limitations; do not claim mathematical proof of zero host risk.

  ## Agent capability orchestration and acceptance
  
  [AGENT_REQUIREMENTS.md](AGENT_REQUIREMENTS.md) defines the agent behavior contract and capability handoffs. Use its Section 2 controls and Section 5 data/resource bounds directly as PR acceptance criteria.
  
  - Planner/code generation, repair, summary and vision are logical ModelClient modes sharing the same task allowances; do not invent separate deployed agents or reset budgets between modes.
  - The API admits session-owned work; deterministic validators approve its structure and policy; only the single trusted coordinator manages Docker execution and cleanup.
  - Route code through proposal/validation/sandbox/evidence. Route actions through preparation/screenshot/destruction/human approval/fresh-browser revalidation/permit-enforced commit. Vision is advisory and cannot approve.
  - The AI orchestration/testing contributor must identify affected A/D requirement rows and attach boundary, concurrency, expiry and failure evidence as applicable. Link blocked or skipped browser/Vultr checks rather than claiming they passed.
