# Readiness, Claims, Tests, and Demo Storyboards

Audit date: **4 November 2026**. This compares the supplied checklist with the repository and observed local checks. A configuration file is not proof of a running deployment. “Not evidenced” means no access or retained result was available here; it does not assert that your cloud account has no resources.

## 1. What exists and what is missing

| Area | Current evidence | Missing before submission | Priority |
| --- | --- | --- | --- |
| Repository | Application source, dependency locks, architecture, requirements, and contributor docs published | Published at [W4sP4nx2/blast-radius-zero](https://github.com/W4sP4nx2/blast-radius-zero) | Done |
| Vultr VM | Ubuntu/Linux deployment configuration is checked in | VM access, actual instance details, Docker daemon and built images on that VM | P0 |
| HTTPS | Caddy config separates app 443 and demo-form 8443 | Real DNS records, reachable public URL, valid certificates, Vultr firewall verification | P0 |
| Redis | Bounded state/blob storage, counters, approval transactions; local tests use fakeredis | Real Redis/HTTP smoke passed locally; target persistence/restart and memory-pressure checks remain | P0 |
| Python containment | 12 real Python Docker checks passed locally and on Ubuntu CI | Repeat and retain evidence on Vultr, including host fault recovery | P0 |
| Browser containment | Packaged Squid, isolated networks, host forwarding/INPUT rules, IPv6 denial, live rule verifier and Chromium launch probe | Proxy build blocked by local Docker storage I/O fault; build browser/proxy images on healthy Linux, install/verify rules and run bypass/sentinel tests | P0 |
| AI | Vultr adapter, catalog validation, bounded calls/retries, rate limits and circuit breaker; provider behavior tested with stubs | Inference subscription key and model IDs, live text/vision run, provider-reported usage evidence | P0 |
| Approval | Session/CSRF, immutable field/revision/destination binding, expiring permit and idempotent receipt; local tests pass | Real two-browser-stage demonstration through dedicated HTTPS listener | P0 |
| Dashboard | Next.js build/typecheck and desktop/mobile UI contract checks pass | Public deployment smoke test with real logs, screenshots, artifacts and receipts | P0 |
| CI | [GitHub Actions run #5 passed](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41736343238) with 100 application tests, 12 Python Docker checks, and frontend build/typecheck. Zero skips in the selected suites | Browser and host-policy release checks are separate | Done |
| Team | W4sP4n (@W4sP4nx2) confirmed as sole contributor across four roles | Link published commits to the role pages | P1 |
| Submission | Architecture, rubric mapping, test matrix, and a [60-second verification walkthrough](https://github.com/W4sP4nx2/blast-radius-zero/releases/download/verification-2026-11-04/brz-verification-60s.mp4) | Public Vultr URL, target-host demo recording, cover image, final project description/tags and completed LabLab submission | P1 |
| Scaling | Future design documented | Distributed workers, managed Valkey, shared object storage and centralized monitoring are future work, not MVP release gates | Future |

Local results and environment are recorded in [verification/local-2026-11-04.md](verification/local-2026-11-04.md). Full runtime matrix: [TESTING.md](TESTING.md).

Agent behavior and capability handoffs are defined in [AGENT_REQUIREMENTS.md](AGENT_REQUIREMENTS.md). Its [Section 2 controls](AGENT_REQUIREMENTS.md#2-lightweight-ai-controls-and-rate-limits) and [Section 5 data/resource bounds](AGENT_REQUIREMENTS.md#5-data-and-sandbox-resource-boundaries) are direct acceptance criteria for AI orchestration and testing pull requests; changing documentation does not mark pending runtime checks as passed.

Local storage blocker: Docker hit filesystem I/O errors while building the proxy at about 191 MiB host free space. Task-generated dependencies/build output were cleaned; the temporary Redis removal timed out. See the verification report for cleanup details.

## 2. Claims that need correction or evidence

| Supplied claim | Accurate statement | Evidence required |
| --- | --- | --- |
| “Mathematically provable zero host risk” / “strictest possible containment” | A containment-first Docker prototype with explicit controls and shared-kernel limitations | Threat model plus measured tests; no absolute guarantee |
| `network_mode="none"` blocks every socket | It disables external container networking; loopback remains | Inspect NetworkMode and test DNS plus direct-IP connections |
| `environment={}` strips the entire environment | Host/provider secrets are not copied; image/runtime defaults remain, and SDK proxy injection is disabled | Unique host sentinel absent inside the container |
| `timeout=10` is a Docker SDK hard-kill argument | The coordinator monitors a deadline and explicitly kills/removes the container | Duration, outcome, cleanup; separately test coordinator/daemon failure recovery |
| `remove=True` is a finally guarantee | Explicit removal is performed in a `finally` path and abandoned resources are reaped | No labelled resources after success, failure, cancellation and restart |
| A `256m` RAM limit alone means no swap | Memory and combined memory/swap limits must both be 256 MiB | Applied HostConfig plus host cgroup/swap capability checks |
| Exit 137 proves OOM | Use corroborating `State.OOMKilled`; allocation errors can fail without it | Container state and task classification |
| An `/etc/passwd` write error proves read-only root | Non-root permissions alone can deny it; test an otherwise user-writable home directory | EROFS/read-only failure on that directory |
| `$host` regex plus an Nginx DNS resolver prevents rebinding | Host strings do not establish actual-destination safety; Squid is backed by independent packet filtering | Protected sentinel receives zero connections under rebinding/mixed answers |
| Metadata is only `169.254.169.254` | Block protected address ranges, aliases, redirects, alternate forms and host interfaces | Browser proxy and direct-bypass tests |
| `/latest/meta-data/` is the Vultr endpoint | The demo targets `/v1/identity/token`; metadata may expose an identity token, not necessarily a stored API key | Trusted denial event without collecting response bodies |
| A printed “BLOCKED” message proves containment | Verified events originate from the trusted validator or proxy enforcement channel | Spoofed stdout/page content cannot create verified policy events |
| A dashboard with zero new tokens proves one preset used no AI | Aggregate billing is only corroboration; instrument the task's provider requests | `provider_requests=0` and a provider-client spy that is never called |
| A system prompt guarantees valid JSON or prevents network attempts | Pydantic validates the selected plan schema and Python byte limit. Docker enforces Python's external network boundary | Reject malformed, blank and oversized generated plans; check live model output separately |
| Redis state makes workers stateless | Live containers, networks and cleanup remain node-owned | Future distributed ownership/leases before adding coordinators |
| Judging weights are 30/30/25/15 | Published criteria are Application of Technology, Presentation, Business Value and Originality, without published weights | [Official event page](https://lablab.ai/ai-hackathons/vultr-hackathon) |

## 3. Testing scenarios and acceptance gates

| ID | Scenario | Expected observation | Current evidence / next step |
| --- | --- | --- | --- |
| T01 | CSV preset, sample then uploaded CSV | Correct statistics, progress before completion, downloadable JSON/CSV | Real sample/uploaded CSV container checks and HTTP/SSE/artifact smoke passed locally; repeat on Vultr |
| T02 | Python HTTPS and direct-IP connection | Both fail under inspected network mode `none` | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T03 | Infinite loop | Timeout outcome near 10s; container removed | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T04 | 600 MiB allocation | Allocation failure or corroborated OOM; bounded host allocation | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T05 | Host-secret sentinel and privilege probe | Sentinel/key absent, non-root UID, NoNewPrivs=1 | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T06 | Rootfs write, temporary write/reset and tmpfs overflow | Rootfs denied; scratch works, is bounded and does not persist | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T07 | Fork/PID and output flood | PID creation or output stops within configured limits; cleanup completes | Passed locally and in [Ubuntu CI](TESTING.md#ubuntu-ci-containment-evidence). Repeat on Vultr |
| T08 | HN research | Three actual headline entries, absolute source URLs, timestamped screenshot evidence; no invented article text | UI evidence components tested; real browser test pending Linux setup |
| T09 | Vultr metadata | Trusted proxy denial; zero metadata body/screenshot publication | Probe supplied; pending target host |
| T10 | Private addresses, host IP, wrong ports, direct sockets/DNS | No protected or direct-egress connection | Target-host release matrix; controlled sentinel evidence required |
| T11 | Redirects, mixed A/AAAA, TTL-zero rebinding | Packet filtering prevents actual protected-destination connections | Controlled DNS/sentinel environment still required |
| T12 | Proxy death or missing/changed firewall | Browser fails closed; no alternate route | Implementation present; fault injection pending Linux host |
| T13 | Approval omitted, expired, cross-session, changed revision/fields | Rejected; no demo record | Local state/API tests pass; real browser flow pending |
| T14 | Concurrent approval/submission and lost browser reply | One queued submission and one trusted receipt; safe replay/reconciliation | Local tests pass; browser fault/restart evidence pending |
| T15 | Limits, malformed plans and provider failures | Correct rejection, at most two recoveries/five calls, circuit pause and single probe | Local counter/provider-stub tests pass |
| T16 | AI disabled; choose a preset | Original prompt preserved, reason shown, real preset dispatch with zero model calls | Local API/dispatch/UI checks passed. Real local CSV smoke recorded zero requests; repeat on Vultr |
| T17 | SSE, downloads, CSRF, escaping and responsive layout | Logs treated as text, session-owned files/actions, no mobile overflow | Local API and Chromium UI checks pass; real deployment stream timing pending |
| T18 | Worker restart, daemon failure, storage pressure, orphan cleanup | No new admission without required state; resources reconciled; no secret output | Some application failure paths tested; full host fault matrix pending |

Do not mark T02–T12 as passed from reading Docker flags. Before publishing the demo, retain deployed commit/image IDs, sanitized logs, runtime inspection, and actual target-host outcomes.

## 4. Main storyboard — 2 minutes 30 seconds

Record this only after the target-host gates pass. The times are a recording plan, not measured execution latency. If a genuine live model call takes longer, adjust the edit transparently rather than substituting output.

| Time | On screen / action | Narration | Evidence to retain |
| --- | --- | --- | --- |
| 0:00–0:12 | Public HTTPS URL, dashboard and compact Vultr architecture | “Vultr Inference proposes work. The coordinator validates the plan and owns every container.” | Actual URL and deployed revision |
| 0:12–0:39 | Ask AI to analyze an uploaded CSV, then show progress and download the result | “The model proposes Python. The sandbox runs it and streams these results.” | Model ID/reported usage, task ID, real logs and generated file |
| 0:39–0:50 | Run the Python network-denial preset and show the connection failure | “The same Python sandbox has no external network access.” | Inspected network mode and real failed request |
| 0:50–1:05 | Run HN capture and open its screenshot and source receipts | “The browser can reach approved websites. It captured these headlines and links.” | Actual screenshot, source URLs and capture/task timestamps |
| 1:05–1:25 | Run metadata-denial preset; keep trusted policy event visible | “A browser request to cloud metadata is denied outside the page. A page cannot grant itself network permission.” | Proxy-enforced denial and zero protected-sentinel hits; never show metadata bodies |
| 1:25–1:50 | Prepare demo form; show exact destination, fields, revision and screenshot before approval | “Preparation creates no record. The browser is destroyed while I review this exact action.” | Pending action and cleanup evidence; no receipt before approval |
| 1:50–2:10 | Click approval; show a fresh browser and trusted receipt | “The form service accepts only this approved payload. Replays return the same receipt.” | One action ID and one receipt; demonstrate project-owned demo effect only |
| 2:10–2:25 | With AI deliberately disabled in operator configuration, show structured unavailability then run CSV preset | “Inference can be unavailable. Explicit presets still execute real work and make no model calls.” | Clearly labelled preset, zero provider requests, actual container output |
| 2:25–2:30 | Return to repository and test matrix | “The policies, test evidence and limitations are published for review.” | Public repository and observed-results table |

Keep the inference-disable configuration change outside public controls. If filmed as a separate cut, label it; do not present test fixtures or cached screenshots as live execution.

## 5. Containment-only storyboard — 60 seconds

| Time | Shot | Proof point |
| --- | --- | --- |
| 0:00–0:10 | Successful CSV execution and artifact | Useful work still succeeds |
| 0:10–0:25 | External Python request fails; show applied network policy | Offline Python has no external networking |
| 0:25–0:40 | Browser metadata preset displays a trusted denial | Internet-capable browser still cannot reach metadata |
| 0:40–0:55 | Pending form, explicit approval, one receipt | Preparation is separate from authorization and commit |
| 0:55–1:00 | Observed test table and limitations | Evidence supports specific controls, not an absolute security guarantee |

This short security clip supplements the main submission. It does not replace proof of the required live Vultr Inference workflow.

## 6. Remaining execution order

1. Configure actual domain/VM/inference values in the ignored, permission-restricted `.env`; do not commit credentials.
2. Build the application and all sandbox images on the target Linux VM.
3. Install the checked-in host policy, start services, obtain HTTPS certificates, and pass `deploy/preflight.sh`.
4. Run the real Docker suite and the browser/sentinel fault matrix. Fix failures without weakening policy.
5. Retain sanitized evidence and update TESTING/METRICS; publish the repository and live URL.
6. Record the chosen storyboard with real results and complete the official submission.

## 7. Submission wording

> Twelve real Python Docker containment checks passed both locally and on Ubuntu GitHub Actions. The application suite passed 100 tests, including AI orchestration with a stub provider. A real local CSV preset streamed output, produced downloadable artifacts, and made zero provider requests. Local Docker storage I/O errors blocked the browser proxy build. The browser containment matrix and live Vultr Inference still require target-host verification.

Supplement the deployed demo with [GitHub Actions run #5](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41736343238) and the [60-second verification walkthrough MP4](https://github.com/W4sP4nx2/blast-radius-zero/releases/download/verification-2026-11-04/brz-verification-60s.mp4). The walkthrough shows retained evidence from the earlier CI run. Record the deployed app and live inference for the official submission.
