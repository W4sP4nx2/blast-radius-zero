# Validation and Evidence

This file distinguishes **Expected** behavior from **Observed** results. A passing unit test does not establish that containment is active on the target Vultr host. Record the deployed commit, image IDs, host configuration, date, and evidence for release checks.

## Verification status

| Area | Status | Evidence |
| --- | --- | --- |
| Backend application suite | ✅ **Passed (100 tests)** | [Local report, 4 Nov 2026](verification/local-2026-11-04.md#prompt-and-schema-regression) |
| Prompt and plan validation | ✅ **Passed (Local stubs)** | [Verbose test log](verification/ai-focused-2026-11-04.txt) covers malformed and truncated JSON, the UTF-8 boundary, and bounded recovery. Live model output awaits a Vultr run |
| AI orchestration and circuit breaker | ✅ **Passed (21 focused tests with local stubs and doubles)** | [Verbose test log](verification/ai-focused-2026-11-04.txt) covers the two-recovery and five-request limits, circuit opening after five provider failures, immediate second-probe rejection, and preset dispatch without inference |
| Python sandbox containment | ✅ **Passed (12 local Docker checks)** and ✅ **Passed (12 Ubuntu CI Docker checks)** | Docker Desktop Linux/arm64 and GitHub-hosted Ubuntu 24.04 x64, 4 Nov 2026. Vultr results are pending. [Local report](verification/local-2026-11-04.md) · [Ubuntu CI evidence](#ubuntu-ci-containment-evidence) |
| Browser proxy and host firewall | ⚠️ **Pending** | Local Docker storage I/O blocker. Awaiting target VM or CI runner configured for the browser matrix. [Local report](verification/local-2026-11-04.md) |
| Frontend production build and typecheck | Passed locally | [Local report](verification/local-2026-11-04.md); Node 24.22.2 and Linux frontend container |
| Frontend browser contracts | Passed desktop/mobile, SSE handling, escaping, fallback, explicit approval and receipt display | Chromium with intercepted test API fixtures; not containment evidence |
| Vultr deployment and HTTPS | ⚠️ **Pending** | Requires credentials, DNS, and a target VM |
| Live Vultr Inference | ⚠️ **Pending** | Requires a configured inference subscription key and model access |
| GitHub Actions | ✅ **Passed** | 100 application tests, 12 real Python Docker tests, and frontend typecheck/build passed. Browser integration skipped. [Run 41734667690](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41734667690) · [Log excerpt](verification/github-actions-41734667690.txt) · [Screenshot](verification/github-actions-41734667690.jpg) |

Never replace these entries with “passed” based only on source inspection. When updating a row, link a sanitized report or CI run and record its environment and date.

## Functional workflows

| Test | Action | Expected result | Observed | Environment / date / evidence |
| --- | --- | --- | --- | --- |
| Python execution | Run `print('Containment System Active', flush=True)` | Exit succeeds; actual output is returned | Not yet recorded | — |
| CSV analysis | Run the CSV preset with the sample data, then an uploaded CSV | Deterministic statistics and bounded downloadable artifacts | Sample and uploaded input passed local Docker checks. Real sample HTTP smoke downloaded JSON and CSV | [Local report, 4 Nov 2026](verification/local-2026-11-04.md). Repeat on Vultr |
| Live streaming | Print, sleep briefly, and print again | First output arrives before task completion; reconnection does not start another task | Real CSV smoke received stdout while running. SSE replay covered by local API test | [Local report](verification/local-2026-11-04.md), [API tests](backend/tests/test_api.py). Repeat over public HTTPS |
| Browser receipts | Run the Hacker News preset | Actual screenshot, extracted entries, URLs, and timestamps | Not yet recorded | — |
| Allowed research | Visit an administrator-approved HTTPS destination | Browser works through the proxy | Not yet recorded | — |
| Blocked research | Request an unapproved domain | Clear denial; no fabricated source summary | Not yet recorded | — |
| Cancellation | Cancel a running task | Work stops; resources are removed; state becomes cancelled | Not yet recorded | — |
| Artifact retention | Fetch an artifact after retention expires | Artifact is unavailable and storage is reclaimed | Not yet recorded | — |

## Python containment

Exact platform error wording is not an acceptance criterion. Check runtime configuration and the resulting behavior together.

### Ubuntu CI containment evidence

The manually dispatched workflow tested commit `c5264089f801fd8c92fd0f26ee8acbbf844780d8` on Ubuntu 24.04 x64 with Python 3.13.17 on 4 November 2026 (Asia/Bangkok). The `BRZ_INTEGRATION=1` step passed 12 Python checks and skipped the browser integration. [Passing run](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41734667690) · [Backend job](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41734667690/job/126260648362) · [Retained log excerpt](verification/github-actions-41734667690.txt)

| Scenario | Observed on the Ubuntu runner |
| --- | --- |
| T02 · External networking | DNS-backed HTTPS and direct-IP connection tests passed |
| T03 · Deadline | Busy loop timed out and the container was removed |
| T04 · Memory | The 600 MiB allocation probe failed within the limit. The check requires Docker state corroboration if the result is classified as OOM |
| T05 · Secrets and privilege | The host sentinel and provider key were absent. Non-root and `NoNewPrivs` probes passed |
| T06 · Filesystem and scratch | Root write, scratch isolation and tmpfs limit probes passed |
| T07 · PID and output limits | PID limit and output-flood probes passed |

### Detailed scenarios

| Test | Payload / action | Expected result | Observed | Environment / date / evidence |
| --- | --- | --- | --- | --- |
| External DNS/network | `import urllib.request; urllib.request.urlopen('https://example.com', timeout=2)` | Connection fails; inspect confirms networking is `none` | Not yet recorded | — |
| Direct external IP | Attempt a short TCP connection to a controlled external IP | Connection fails without depending on DNS failure | Not yet recorded | — |
| Metadata attempt | Attempt `http://169.254.169.254/v1/identity/token` with a short timeout | No metadata response reaches the task | Not yet recorded | — |
| CPU deadline | `while True: pass` | Explicit kill near the 10-second deadline; container is removed | Not yet recorded | — |
| Memory bound | `b = bytearray(1024 * 1024 * 600)` | Allocation fails or process is OOM-killed within the configured memory limit | Not yet recorded | — |
| OOM classification | Inspect task and container state after a memory probe | OOM is reported only with corroborating `State.OOMKilled`; exit 137 alone is insufficient | Not yet recorded | — |
| Secret hygiene | Place a unique sentinel in the backend environment; read it in the task | Sentinel absent; ordinary image/runtime variables may remain | Not yet recorded | — |
| Read-only filesystem | Write into the image's otherwise user-writable home directory | Write fails because the root filesystem is read-only | Not yet recorded | — |
| Scratch space | Write within `/tmp`, then exceed its capacity | Small write succeeds; size remains bounded | Not yet recorded | — |
| Cross-task reset | Create a distinctive scratch file, then look for it in the next run | File absent | Not yet recorded | — |
| Output flood | Repeatedly print beyond the log allowance | Output-limit outcome; bounded buffering and log storage | Not yet recorded | — |
| Process bound | Spawn beyond the PID allowance | Further creation fails; host remains responsive | Not yet recorded | — |
| Capability inspection | Inspect Docker config and runtime `NoNewPrivs` | Non-root, dropped capabilities, no-new-privileges, resource and filesystem settings are effective | Not yet recorded | — |

For metadata probes, retain denial status or connection failure evidence. Do not print or archive metadata response bodies or credentials if a check unexpectedly reaches the endpoint.

## Browser, proxy, and firewall

The success criterion is that protected sentinel services receive **zero connections**. A printed “BLOCKED” string, proxy-only DNS lookup, or browser interceptor is insufficient proof.

| Test | Action | Expected result | Observed | Environment / date / evidence |
| --- | --- | --- | --- | --- |
| Metadata denial | Navigate to the Vultr metadata endpoint | Trusted policy denial; no metadata response or sentinel hit | Not yet recorded | — |
| Private ranges | Probe private, loopback, link-local, and host addresses | Denied at proxy and/or actual-destination host filtering | Not yet recorded | — |
| Alternate address forms | Probe IPv4-mapped IPv6 and alternate IP representations | No protected connection | Not yet recorded | — |
| Redirect | Allowed page redirects to metadata or a private address | Redirected destination is denied | Not yet recorded | — |
| DNS rebinding | Change an approved test hostname from public to protected addresses, including TTL-zero and mixed answers | Actual protected destination remains unreachable | Not yet recorded | — |
| Direct socket bypass | Connect without using the configured proxy | No direct browser egress | Not yet recorded | — |
| Direct DNS bypass | Query a controlled authoritative DNS server from the browser container | Query does not reach the server | Not yet recorded | — |
| CONNECT port bypass | Request an unapproved destination port | Denied, including arbitrary use of port 8443 | Not yet recorded | — |
| Host public address | Connect to the control-plane host's public IP | Denied except the exact dedicated demo-form listener | Not yet recorded | — |
| Demo listener separation | Use altered Host/SNI values on the form listener | No route to the API, Redis, or administration services | Not yet recorded | — |
| Proxy failure | Stop the proxy during a browser task | Browser fails closed; no alternate egress path | Not yet recorded | — |
| Missing firewall | Remove or alter required BRZ-owned rules in an isolated test environment | Browser admission becomes unavailable | Not yet recorded | — |
| Fake policy output | Make a page or task print a claimed security event | It cannot create a trusted verified policy event | Not yet recorded | — |
| Chromium sandbox | Inspect launch/configuration and run the browser probe | Non-root Chromium sandboxing is active | Not yet recorded | — |

## Approval and session safety

| Test | Action | Expected result | Observed | Environment / date / evidence |
| --- | --- | --- | --- | --- |
| Prepare only | Fill the demo form and capture its screenshot | No submission; first browser is removed | Not yet recorded | — |
| Approval ownership | Approve another session's action | Rejected without revealing its data | Not yet recorded | — |
| CSRF | Omit or alter the CSRF token | Mutation rejected | Not yet recorded | — |
| Expiry | Approve more than five minutes after preparation | Rejected; a new preparation is required | Not yet recorded | — |
| Changed form | Change the form revision before execution | No submission; new approval required | Not yet recorded | — |
| Modified values | Alter values, destination, revision, or payload binding | Permit rejected | Not yet recorded | — |
| Duplicate submission | Send the same approved submission concurrently | One record; the same receipt is returned | Not yet recorded | — |
| Lost response | Lose the browser response after a committed submission | Reconcile the existing receipt; no second submission | Not yet recorded | — |
| Artifact ownership | Fetch another session's artifact | Rejected | Not yet recorded | — |

## AI and shared-state controls

| Test | Action | Expected result | Observed | Environment / date / evidence |
| --- | --- | --- | --- | --- |
| Counter concurrency | Admit concurrent requests at each boundary | Limits hold across requests; counters expire | Not yet recorded | — |
| Queue capacity | Fill both execution slots and the waiting queue | Excess request receives structured capacity rejection | Not yet recorded | — |
| Bounded recovery | Repeatedly return invalid JSON or eligible code errors | At most two additional recoveries and five provider requests | Local provider and runner-double checks passed | [AI tests](backend/tests/test_ai.py), [coordinator tests](backend/tests/test_worker.py), [local report](verification/local-2026-11-04.md) |
| Generated Python source boundary | Return 65,538 UTF-8 bytes, whitespace-only source, then exactly 65,536 bytes | Two rejected plans use the shared recovery allowance. The valid boundary plan is accepted | Passed with a stub provider | [AI test](backend/tests/test_ai.py), [local regression run](verification/local-2026-11-04.md#prompt-and-schema-regression) |
| No policy repair | Return denial, timeout, or OOM | No automatic repair call | Local runner-double checks passed | [Coordinator tests](backend/tests/test_worker.py), [local report](verification/local-2026-11-04.md) |
| Circuit opens | Return five consecutive provider timeouts or server errors | Circuit pauses calls for 60 seconds | Five stubbed 500s opened the circuit; reported TTL was at most 60 seconds | [AI tests](backend/tests/test_ai.py), [local report](verification/local-2026-11-04.md) |
| Circuit recovery | Send concurrent requests when the pause ends | One probe; success closes, failure reopens | Immediate second admission rejected in test; long-running probe overlap after the 30-second lease expires remains unverified | [AI tests](backend/tests/test_ai.py), [local report](verification/local-2026-11-04.md) |
| Provider throttling | Return `429` with `Retry-After` | Retry timing respected without an unbounded retry loop | Stubbed `429` applied cooldown without recording an outage | [AI tests](backend/tests/test_ai.py), [local report](verification/local-2026-11-04.md) |
| Invalid credentials | Return an authentication failure | Live AI disabled until configuration is corrected | Stubbed `401` disabled live AI without retry | [AI tests](backend/tests/test_ai.py), [local report](verification/local-2026-11-04.md) |
| Redis unavailable | Disconnect required shared state | New execution rejected; limits are not bypassed | Not yet recorded | — |
| Explicit fallback | Disable AI and submit a custom request | Structured reason and preset choices; custom prompt is preserved | Not yet recorded | — |
| Zero model calls | Run each preset with provider-client instrumentation | Zero provider requests for that task; real sandbox execution still occurs | Runner-double test passed. Real local CSV smoke recorded `provider_requests=0`. Full preset matrix awaits the target host | [Coordinator tests](backend/tests/test_worker.py), [local report](verification/local-2026-11-04.md) |

Provider dashboards can corroborate usage, but aggregate billing is not sufficient to prove that one task made zero calls. Use task-level request instrumentation or a test provider client.

## Release verification

Run unit/API checks and the frontend production build first. On an isolated Linux Docker host, build the sandbox images, install the checked-in destination policy, run `deploy/preflight.sh`, and execute the containment matrix. Repeat target-host checks after changing Docker, the kernel, firewall policy, images, or deployment configuration.

CI runs application validation and Python Docker containment independently on ephemeral Ubuntu runners. PRs targeting `main` or `master` and pushes to either branch trigger both jobs, including documentation-only changes. The Python Docker job selects the Python containment cases. Any skipped or expected-failure case in either selected pytest suite makes its job fail. The browser marker selects the separate target-host browser check, which needs firewall, DNS, and TLS setup. Live Vultr Inference and public-domain smoke checks also require target-host verification.

### Commands

```bash
# Local application tests; no Docker containment claim.
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -m 'not integration' -q

# Focused provider and coordinator tests. Uses local stubs and doubles.
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_ai.py backend/tests/test_worker.py -v

# Isolated Linux Docker host. This is the Python containment scope used in CI.
docker build -t brz-python-sandbox:local backend/python_sandbox
PYTHONPATH=backend BRZ_INTEGRATION=1 .venv/bin/python -m pytest backend/tests \
  -m 'integration and not browser_integration' --fail-on-skip -v

# Run the browser capture and metadata probes after firewall, DNS and TLS setup.
PYTHONPATH=backend BRZ_INTEGRATION=1 BRZ_BROWSER_INTEGRATION=1 \
  .venv/bin/python -m pytest backend/tests -m browser_integration --fail-on-skip -v
```

The suite is the checked-in automation subset. The full browser DNS-rebinding, controlled-sentinel, proxy-death, host-firewall fault and live-inference matrix above still requires a target-host release session. The integration fixture removes BRZ-labelled resources; never run it alongside production jobs.

For each release retain: commit SHA, command output, relevant image IDs, policy/preflight results, representative task IDs, timing, resource outcome, cleanup evidence, and a sanitized screenshot or recording. Never include `.env`, provider keys, session cookies, approval permits, or metadata tokens in evidence.
