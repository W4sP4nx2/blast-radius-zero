# Implementation Guide

This guide describes the application's intended enforcement points and operating contract. Runtime verification is recorded separately in [TESTING.md](TESTING.md). Configuration alone is not evidence that a control is active on the deployed host.

## Service ownership

| Service | Responsibilities | Privilege boundary |
| --- | --- | --- |
| Next.js | Dashboard and same-origin API routing | No Docker access or provider credentials in browser code |
| FastAPI | Session/CSRF checks, input validation, admission, task/event access | Trusted control plane |
| Coordinator | Bounded model calls, consume admitted tasks, select the administrator-configured sandbox provider, collect artifacts | Sole application Docker-socket owner while Docker is selected |
| Sandbox provider | Fixed `initialize`, code, browser, and teardown contract; Docker is the only ready implementation | Never accepts model/task-controlled infrastructure settings |
| Audit SQLite | Append-only trusted stage and final-outcome records on a worker-only volume | Not exposed to sandboxes or public API clients |
| Redis | Task/session state, counters, approvals, receipts, bounded upload/artifact blobs | Private service; no sandbox access |
| Squid | Administrator allowlist and forward-proxy access control | Trusted per-run browser peer |
| Demo form | Independently validate submission permits and create idempotent receipts | Dedicated HTTPS listener; no control-plane routes |
| Caddy | HTTPS and fixed application/form routing | Only intended public entry points |

One coordinator owns the two-model-call semaphore and the two-task execution limit, including at most one browser stage. A Redis ownership lease rejects a second coordinator. Do not increase worker counts without implementing distributed execution admission.

`SANDBOX_RUNTIME` is administrator configuration. `docker` delegates through `DockerSandboxProvider` to the existing lifecycle below. `native` deliberately reports unready because the published Native MCP interface cannot enforce these execution controls. It never falls back to a host subprocess. [NATIVE_SPEC.md](NATIVE_SPEC.md) records the exact status and promotion gates.

Redis is a bounded prototype blob/state store. Uploads and artifacts expire after 15 minutes, and admission must reject pressure rather than evict approval/counter state or allow unbounded memory growth. Provider secrets are administrator configuration and are never exposed through public health or task responses.

## API and data flow

1. `GET /api/session` establishes an anonymous cookie session and returns `csrf_token`.
2. Mutating requests supply `X-CSRF-Token`. Public deployments use HTTPS cookies; task access is scoped to the originating session.
3. `GET /api/presets` returns preset metadata. `POST /api/uploads` accepts a bounded CSV and returns `upload_id`.
4. `POST /api/execute` validates a discriminated `code`, `task`, or `preset` request and admits it only within rate, queue, dependency, and storage limits.
5. The API returns `202 {"task_id":"..."}`. The coordinator performs real execution outside the API request handler.
6. `GET /api/tasks/{id}` returns task state; `/events` streams bounded SSE events with replay identifiers. Reconnecting observes the task rather than submitting it again.
7. Cancellation and artifact download remain session-scoped. Form submission requires the separate approval endpoint.

Code requests contain only source and an optional owned upload. Natural-language requests contain a `code` or `browser` pattern, a prompt, and an optional upload. Presets reference a known plan ID. No input contract accepts Docker flags, image names, host paths, or arbitrary network policy.

Task provenance distinguishes custom code, live-AI planning, and presets. Results distinguish success, ordinary failure, policy denial, timeout, OOM, cancellation, output limit, and infrastructure error. A task printing “BLOCKED” cannot create a verified security event.

## Python container lifecycle

The coordinator uses a trusted image containing Python 3.13 and a non-root sandbox user. It supplies input as bounded data and does not mount a host working directory.

| Parameter | Policy |
| --- | --- |
| Network | `network_mode="none"` |
| Memory / combined memory+swap | 256 MiB / 256 MiB |
| CPU | `nano_cpus=500000000` |
| PIDs | 64 |
| Root filesystem | Read-only |
| Scratch | 64 MiB `/tmp` tmpfs |
| User | Non-root UID/GID |
| Capabilities | Drop all |
| Privilege escalation | `no-new-privileges` |
| Seccomp | Docker default |
| Host resources | No bind mounts, Docker socket, devices, or published ports |
| SDK proxy injection | `use_config_proxy=False` |
| Execution deadline | 10 seconds |

Create/start a detached bounded container and execute the submitted program with Docker exec. A short-lived base process keeps tmpfs available for artifact collection after the program exits. Stream bounded output and monitor a monotonic deadline and cancellation. On deadline, explicitly kill the container; an SDK HTTP timeout is not an execution kill switch. Collect exit state and files before removal, then remove in `finally`. Use labels to identify resources for startup/recovery cleanup. The deadline depends on the coordinator and Docker daemon remaining responsive; restart cleanup is a separate recovery control.

`State.OOMKilled` corroborates an OOM classification. Exit status 137 alone does not distinguish OOM from another forced kill. A `MemoryError` may be an ordinary allocation failure rather than a kernel OOM event.

No host environment is copied into the task. Trusted image/runtime defaults remain, so secret-hygiene tests use a host sentinel rather than requiring an empty environment. Network mode `none` disables external connectivity while retaining loopback.

The source ceiling is 64 KiB, CSV upload ceiling 2 MiB, combined log ceiling 1 MiB, and artifact ceiling 8 MiB per task. Bound both runtime/log storage and host-side buffering. Reject non-regular files, traversal, symlinks, oversized content, and unsupported artifacts before publication.

## Browser and Squid boundary

The browser image installs matching Playwright package/browser versions. A fixed worker accepts JSON operations for research, form preparation, approved submission, and trusted probes; it does not execute model-supplied Python or JavaScript.

Browser stages run non-root with Chromium sandboxing enabled, the required seccomp profile, dropped capabilities, private shared memory, read-only root storage, bounded scratch, 512 MiB RAM, 1 CPU, 256 PIDs, and a 30-second stage deadline.

Each stage receives an isolated internal Docker network. Only its trusted proxy is a peer. The browser addresses that proxy by a fixed internal address and has no external DNS forwarding, direct internet route, host networking, or network-administration capability. IPv6 egress is blocked for this version.

### Packaged forward proxy

Squid is packaged from the distribution rather than implemented as a custom proxy. Replace its distribution access rules with a project policy; do not append restrictive rules below a broad existing allow rule.

- Accept only the expected internal worker source.
- Require exact administrator-approved destination names and permitted HTTPS CONNECT ports.
- Deny local/private/link-local/host destinations, cache-manager access, and everything not explicitly allowed.
- Permit the demo form only as its exact hostname/IP and port-8443 combination.
- Disable caching and bound connection/header timing and connection counts.
- Publish no proxy port to the internet.

The hostname allowlist is an additional constraint, not proof of the eventual socket destination. A resolver directive or a `$host` regular expression does not establish DNS-rebinding protection. Standard HTTPS CONNECT also does not expose encrypted HTTP methods to the proxy; approved side effects are enforced by the action engine and project-owned form endpoint.

### Actual-destination host filtering

`deploy/install-firewall.sh` creates only BRZ-owned policy chains and the dedicated proxy-egress bridge. With Docker's iptables integration, forwarding checks are inserted through `DOCKER-USER`; separate INPUT checks protect host-directed traffic.

The proxy's actual egress policy allows only the configured DNS resolver on TCP/UDP 53, ordinary public TCP 443 destinations, and the exact demo-form destination. Protected ranges and all other host access are rejected. The demo listener exception is narrow and must never become a general safe-port exception. Filter proxy IPv6 egress as well as IPv4 paths.

Match the dedicated egress interface/source so unrelated Docker traffic is not affected. Apply destination protections before broad established-connection acceptance, and install policy before creating proxy containers. Do not flush or replace Docker-managed chains.

Browser readiness checks inspect actual host policy through a trusted probe and run runtime checks; a caller-set readiness token is insufficient. Missing policy or a dead proxy makes browser work unavailable. Controlled negative tests must show zero hits on protected sentinel services.

Trusted proxy/policy events provide containment evidence. Page output and browser-reported error messages remain untrusted. Capture denials without retrieving or logging metadata content.

## Approval and receipt protocol

The project-owned demo form has two user fields, `title` and `message`, and a semantic revision covering its fields, method, destination, and disclosure. Its disclosure states that it creates a demo receipt only; it does not send email or make purchases.

1. **Prepare:** the browser loads the fixed demo destination, validates its form revision, fills values, and captures a screenshot. The control plane stores an immutable session-owned action. The browser is removed.
2. **Review:** the dashboard shows the actual screenshot alongside trusted exact field values and destination. Approval expires five minutes after preparation, including queue time.
3. **Approve:** the owning session supplies CSRF-protected approval. The control plane atomically claims the pending action and issues a short-lived permit bound to its payload/revision.
4. **Recreate:** a new browser reloads the fixed form, checks its revision/method/action, and fills stored values. Any mismatch prevents submission and requires new preparation.
5. **Enforce:** the form endpoint independently checks the permit, expiry, approved values, and current revision. An atomic operation records one receipt for the action.
6. **Reconcile:** a duplicate or lost response returns the same receipt. Do not automatically create another action or regenerate the approved values.

The dedicated form HTTPS listener serves no API/admin virtual hosts. Different Host/SNI values must not allow a CONNECT tunnel to reach the control plane. The sandbox receives only the narrowly scoped approved-action permit, never general provider or host credentials.

## Model calls and fallback

Live tasks use Vultr Inference with administrator-configured accessible text/vision model IDs. Keep prompts and schemas versioned, validate generated JSON, and limit supplied context and screenshot dimensions.

The controls in [AGENTS.md](AGENTS.md) apply to every provider request, including recovery and verification. Disable client-library automatic retries. Invalid JSON consumes a recovery attempt; policy/resource denials are not automatically repaired.

The provider circuit is separate from visitor admission. Five consecutive provider timeouts/server errors open it for 60 seconds, after which one probe is allowed. A successful probe closes it; failure reopens it. Respect provider throttling and disable inference after invalid credentials.

When inference is unavailable, return a structured reason, retry timing, and available preset IDs. Keep the visitor's original prompt visible. A selected preset runs real containers, real logs, and real screenshots with `source: "preset"` and no model call. Capacity, storage, and approval requirements still apply.

## Deployment configuration and preflight

`.env.example` is the configuration reference. Set the application domain/origin, dedicated demo domain and public IP, approved browser domains, DNS resolver, and—when enabled—Vultr Inference credentials and model IDs. Store secrets only in the private deployment environment.

The deployment sequence is documented in [README.md](README.md). `deploy/preflight.sh` must run against the actual target after images, host policy, and services are installed. Check container identity, no-new-privileges, seccomp, memory/CPU/PIDs, read-only root, scratch limits, Chromium sandboxing, host filtering, network denial, and cleanup.

Health output must report unready dependencies without exposing secrets or internal management endpoints. A missing containment prerequisite disables the affected mode; do not fall back to host execution, relaxed browser networking, or unrestricted rate counters.

## Known limits

The single coordinator is node-affine, and process-local limits are not distributed coordination. Docker and Chromium still depend on host-kernel/runtime security. Browser automation is bounded and allowlisted, not a general authenticated web agent. Account logins, purchases, third-party submissions, high availability, and enterprise tenancy guarantees are outside this release.
