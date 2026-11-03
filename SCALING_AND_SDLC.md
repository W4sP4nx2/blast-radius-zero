# Scaling and Agent Development Lifecycle

## Current deployment boundary

This version targets one Vultr VM, one API process, and one execution coordinator. Redis holds task/control state and bounded upload/artifact blobs; live containers, per-run networks, and cleanup remain owned by the execution host.

Process-local semaphores enforce the current concurrency limits only because there is one owner. Copying the worker or increasing process count does not create a global semaphore and would multiply available execution capacity. Execution workers are not fully stateless.

## Future scaling roadmap

The following items are design directions, not deployed capabilities.

| Stage | Required change before scaling | Verification requirement |
| --- | --- | --- |
| Multiple API processes | Preserve shared session/CSRF/admission behavior and keep model dispatch owned by the coordinator | Concurrent global rate, probe, and model-call limits remain effective |
| Multiple execution hosts | Durable queue claims, worker leases, node ownership, per-node quotas, shared admission, and restart recovery | No duplicate execution; lost workers are detected and their resources reconciled |
| Larger artifact volumes | Replace bounded Redis blobs with session-authorized object storage while preserving task ownership | Ownership, retention, quotas, and deletion hold across nodes |
| Highly available state | Evaluate managed Valkey and validate the application's command/transaction assumptions | State recovery and failover do not bypass admission or approvals |
| Load balancing | Add a Vultr Load Balancer in front of API/web services after shared coordination works | SSE reconnects and session ownership behave correctly |
| Orchestrated execution pools | Evaluate separate code/browser pools under an orchestrator with equivalent network and cleanup policy | Every node passes the same containment release gates |
| Central observability | Export sanitized metrics/logs to a monitoring system | No credentials, session tokens, or permits enter logs |

[Vultr Managed Databases for Valkey](https://docs.vultr.com/products/storage/databases/valkey/provisioning) is a Redis-compatible managed service to evaluate for the state tier. [Vultr Object Storage](https://docs.vultr.com/product-overviews/object-storage) is an S3-compatible candidate for shared artifacts. Neither is required or claimed as already configured for this single-node prototype.

Redis clustering is not a drop-in correctness guarantee. Before changing topology, verify atomic operations, key placement, queue ownership, rate limiting, and single-use approvals under failover and concurrent access.

## Agent development lifecycle

### 1. Version the behavior contract

Keep prompts, Pydantic schemas, preset plans, limits, proxy policy, and form revision rules in Git. A prompt or policy change is a behavior change and receives the same review as application code.

### 2. Evaluate planning separately from execution

Use fixed task inputs and stub provider responses to test JSON handling, bounded repairs, unavailable providers, and deterministic preset behavior. Evaluate real model output through the same structural validation and sandbox path used in production.

A structurally valid plan is not proof that the generated task is safe. The execution boundary must remain effective for arbitrary submitted Python and hostile web content.

### 3. Run containment regression checks

CI should run unit/API checks, the frontend build, and fixed Linux Docker integration probes on ephemeral runners. Use synthetic data and no production credentials. Never direct untrusted pull-request code at a production host or its Docker socket.

External-domain and live-inference smoke tests are separate release checks. A passing offline CI run does not establish that DNS, host filtering, Vultr inference access, or HTTPS is configured on the deployed VM.

### 4. Verify the deployment

Run preflight checks after provisioning and after changes to the kernel, Docker, firewall, images, or service configuration. Check actual container settings and runtime behavior. Missing required controls make the corresponding execution mode unavailable.

### 5. Observe and respond

Log task IDs, source, state transitions, duration, outcome, cleanup errors, model-call counts, and provider-reported usage. Keep user output separate from trusted policy events. Redact credentials, session cookies, permits, and metadata bodies.

Use rate limits and the provider circuit breaker for admission and outage recovery. Review actual credit consumption through Vultr; the application does not implement a precise billing ledger.

### 6. Release and record evidence

Record the commit, image IDs, tests executed, skipped checks, deployment environment, and known limitations in the release evidence. Update `TESTING.md` and `METRICS_AND_RUBRICS.md` with observed results only after collecting them.

For a rollback, stop admitting new work, cancel or drain bounded running tasks, deploy the previous known configuration, and rerun preflight before reopening execution. Do not weaken isolation to restore availability.

## Explicit non-goals for this version

Multi-tenant enterprise isolation, high availability, arbitrary website logins, third-party form submissions, payments, distributed execution, and a production monitoring stack are outside this prototype. Docker shares the host kernel; stronger tenant separation would require a separately evaluated execution architecture.
