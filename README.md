# Blast Radius Zero

**Containment-first agentic execution on Vultr.** Run useful Python tasks and bounded browser workflows, inspect real logs and artifacts, and approve a form submission before it creates a demo receipt.

The project separates a trusted control plane from short-lived execution containers. Models propose work; deterministic code enforces networking, resource limits, deadlines, approval, and cleanup. Presets use stored plans and the same execution path without making model calls.

> Deployment status: setup and target-host verification are pending. See [TESTING.md](TESTING.md) for recorded checks and [TEAM.md](TEAM.md) for contributor attribution.

## What the app does

- **Code:** run custom Python, analyze a CSV, stream output, and download bounded generated artifacts.
- **Browser:** capture approved public websites, return screenshots and source receipts, and visibly deny protected destinations.
- **Human approval:** prepare a project-owned form, inspect its screenshot and exact values, then approve one submission within five minutes.
- **Graceful degradation:** when inference is disabled, throttled, or unavailable, preserve the task and offer explicitly labelled zero-token presets.

This is a hackathon prototype with a stated security boundary. Docker shares the host kernel; these controls are not a mathematical proof of zero host risk or a substitute for a security review.

## Architecture on Vultr

```text
                         Vultr Cloud Compute: dedicated Ubuntu VM
 Internet ── HTTPS ──> Caddy ──> Next.js dashboard
                         │
                         └────> FastAPI control plane
                                      │
                                   Redis
                            tasks, limits, approvals,
                            bounded uploads/artifacts
                                      │
                             Trusted coordinator ──────> Vultr Inference
                             (Docker socket owner)
                                  /       \
                   Python sandbox         Browser sandbox
                   external network off   isolated internal network
                   256 MiB / 0.5 CPU                │
                   10-second deadline            Squid
                                                 │
                                    actual-destination host filtering
                                          /               \
                                  approved HTTPS       demo form only
                                  public websites      dedicated :8443
```

The [official Blast Radius Zero challenge](https://lablab.ai/ai-hackathons/vultr-hackathon) requires a Vultr-hosted web application and backend, Vultr Serverless Inference for agent calls, real isolated execution, and verifiable output. The Docker Engine is software running on Vultr Compute, not a separate Vultr-managed sandbox service.

### Execution walkthrough

1. **Admit.** FastAPI checks the session, CSRF token, request schema, and Redis quotas before enqueueing work. It accepts up to 2 MiB of UTF-8 CSV and rejects NUL bytes. New execution admission requires Redis.
2. **Propose and validate.** The request selects Code or Browser. For live AI, the coordinator's versioned prompts ask Vultr Inference for a `CodePlan` containing only Python source or a `BrowserPlan` for one of the fixed operations. Pydantic rejects malformed output, unexpected fields, and blank or oversized Python before dispatch. The source limit is 65,536 UTF-8 bytes. Invalid plans can use the shared recovery allowance.
3. **Execute and observe.** Only the coordinator has Docker access. It supplies the container settings and collects up to 1 MiB of combined logs and 8 MiB of artifacts per task. It checks artifact archives in memory and removes execution resources. The dashboard receives events through SSE. Python's external network restriction is enforced by Docker. Browser egress uses an exact Squid allowlist and independent host rules for actual destinations.
4. **Authorize effects.** Form preparation captures the values, revision, and screenshot, then destroys the browser. Approval by the owning session authorizes a fresh browser to revalidate and submit. The form service checks the payload-bound permit and creates one receipt atomically. Repeated submissions return the recorded receipt.

The code prompt uses standard-library `csv` and the staged path `/tmp/input.csv`. Prompt instructions guide the model. Schema validation, quotas, networking, and approval run in trusted code. See [AGENT_REQUIREMENTS.md](AGENT_REQUIREMENTS.md) for the contracts and [CHECKLIST.md](CHECKLIST.md#4-main-storyboard--2-minutes-30-seconds) for the 2:30 recording sequence.

### Execution policies

| Control | Python | Browser |
| --- | --- | --- |
| Network | `network_mode="none"`; no external networking | Internal-only browser network; Squid allowlist plus host destination filtering |
| Memory | 256 MiB; no additional swap allowance | 512 MiB |
| CPU / PID limit | 0.5 CPU / 64 PIDs | 1 CPU / 256 PIDs |
| Deadline | 10 seconds | 30 seconds per stage |
| Identity | Non-root; dropped capabilities; no-new-privileges | Non-root; Chromium sandbox; dropped capabilities |
| Filesystem | Read-only root with bounded scratch storage | Read-only root with bounded scratch and private shared memory |
| Lifecycle | Explicit kill at deadline; removal in `finally` | Fresh container/network per stage; cleanup on every path |

No sandbox receives host/provider API credentials or the Docker socket. Image/runtime environment defaults remain. Network mode `none` retains loopback; it disables external connectivity rather than every possible socket operation.

## Target-host quick start

Full containment is targeted at a dedicated **Ubuntu 24.04 Linux host with Docker Engine and the Docker Compose plugin**. Configure public DNS names for the application and demo form to the VM's public IPv4 address. Allow HTTPS ports 443 and 8443, plus port 80 for certificate issuance, through the Vultr firewall. Restrict SSH to your administration source.

Run from the repository root. Read the scripts before applying host policy; they alter BRZ-owned firewall chains and leave Docker-managed chains intact.

```bash
cp .env.example .env
chmod 600 .env
# Edit .env: APP_DOMAIN, DEMO_DOMAIN, DEMO_IP, and approved BROWSER_DOMAINS.
# For live AI, set AI_ENABLED=true, VULTR_API_KEY, and the text/vision model IDs.

docker compose --profile images build

# Replace this documentation address with your VM's actual public IPv4.
sudo ./deploy/install-firewall.sh --demo-ip 203.0.113.10 --dns 1.1.1.1

docker compose up -d
./deploy/preflight.sh
```

Open `https://YOUR_APP_DOMAIN` after Caddy has obtained certificates and preflight succeeds. The dedicated demo listener is `https://YOUR_DEMO_DOMAIN:8443`. Do not use the documentation IP in a live configuration.

The default configuration keeps AI disabled. Presets still execute real work when required runtime dependencies are ready. Live judging evidence must also demonstrate the configured Vultr Inference path. `VULTR_API_KEY` means the Inference subscription key here, not a general cloud-management key. Use model IDs your subscription actually exposes, including a vision-capable model for screenshot verification.

The commands above are the deployment procedure; target-host execution and outcomes are recorded in [TESTING.md](TESTING.md). A Docker CLI installation without a running daemon is insufficient. Browser execution remains unavailable if the host destination policy cannot be verified.

### Local development checks

Backend checks use Python 3.13 (pinned in `.python-version`) and [uv](https://docs.astral.sh/uv/). `pyproject.toml` declares the pinned direct dependencies and `uv.lock` pins the full transitive set; the backend image, CI and local environments all install from that lockfile.

```bash
uv venv                # creates .venv in the repository root
uv sync --locked       # installs runtime + dev groups exactly as locked
uv run pytest backend/tests -m 'not integration'
```

To change a dependency, edit its pin in `pyproject.toml`, run `uv lock`, and commit both files. `--locked` makes CI and the image build fail when they disagree.

Frontend checks:

```bash
cd frontend
npm ci
npm run build
```

For interactive development, run Redis, set `REDIS_URL` and `APP_ORIGIN=http://localhost:3000`, start the backend from `backend/` using `uv run uvicorn main:app --host 127.0.0.1 --port 8000`, and run `npm run dev` from `frontend/`. The coordinator is a separate process (`uv run python -m brz.worker` from `backend/`). Full browser containment requires the supported Linux host policy; do not weaken it to make a local preview work.

## Known Local Constraints

The local browser proxy build stopped with Docker storage I/O errors when the host had about 191 MiB free. All 100 application tests passed, including the 21 AI and coordinator tests captured in the focused rerun. Twelve real Python Docker checks passed locally and on Ubuntu CI. Full browser containment and live Vultr Inference remain pending on the target host. [Focused test output](verification/ai-focused-2026-11-04.txt) · [Verification status](TESTING.md#verification-status) · [Passing GitHub Actions run](https://github.com/W4sP4nx2/blast-radius-zero/actions/runs/41736343238)

GitHub Actions installs from `uv.lock` and runs application tests, frontend typecheck and build, a backend image build with an import smoke check, and real Python Docker containment on every PR targeting `main` or `master` and on pushes to either branch, including documentation-only changes. A skip or expected failure among selected pytest cases fails the check. Browser containment and live inference are verified separately on the target Vultr host. [Workflow](.github/workflows/ci.yml) · [Release verification](TESTING.md#release-verification)

## Lightweight inference controls

There is no lifetime dollar ledger. The public demo uses expiring request counters, model-output ceilings, two concurrent model calls, at most two recovery attempts, and at most five provider requests per task. Five consecutive provider timeouts/server errors open a 60-second circuit breaker. [AGENTS.md](AGENTS.md) contains the complete limits.

The application exposes provider-reported usage for visibility. Monitor actual credit consumption through Vultr. Presets are labelled `source: "preset"`, use zero provider requests, and retain sandbox capacity and approval requirements.

## API shape

`GET /api/session` establishes the anonymous session and returns a CSRF token. Send that token as `X-CSRF-Token` for mutations. Tasks, uploads, approvals, and artifacts belong to that session.

`POST /api/execute` accepts one of:

```json
{"kind":"code","code_payload":"print('Containment System Active', flush=True)"}
```

```json
{"kind":"task","pattern":"browser","prompt":"Capture the top three Hacker News headlines with receipts"}
```

```json
{"kind":"preset","preset_id":"<id returned by GET /api/presets>"}
```

The response is `202` with a `task_id`. Fetch status at `/api/tasks/{id}` and real SSE events at `/api/tasks/{id}/events`. CSV uploads use `/api/uploads`; task cancellation, artifact downloads, and session-bound approval have dedicated endpoints. See [IMPLEMENTATION.md](IMPLEMENTATION.md) for the workflow and contracts.

## Demonstration sequence

[60-second verification walkthrough](https://github.com/W4sP4nx2/blast-radius-zero/releases/download/verification-2026-11-04/brz-verification-60s.mp4) shows the retained local and Ubuntu CI results. Record the target-host demonstration below after deployment.

1. Run CSV analysis and show logs arriving before completion plus a generated artifact.
2. Attempt an external Python request and show the observed denial under network mode `none`.
3. Capture Hacker News and display real screenshot evidence and source links. Headline-only evidence is labelled; linked article text is not invented.
4. Attempt Vultr metadata access and display trusted denial evidence without showing metadata content.
5. Prepare the demo form, inspect the fields and screenshot, approve, and show one receipt.
6. Disable live inference and run a clearly labelled preset to show graceful degradation.

## Repository guide

| Location | Purpose |
| --- | --- |
| `backend/brz/` | API, task state, AI controls, trusted coordinator, sandbox lifecycle, demo form |
| `backend/python_sandbox/` | Minimal non-root Python execution image |
| `backend/browser_sandbox/` | Fixed Playwright operations and browser image |
| `frontend/` | Next.js dashboard, terminal, screenshots, approvals |
| `compose.yaml`, `deploy/` | Service deployment, Squid/Caddy configuration, host policy, preflight |
| [AGENTS.md](AGENTS.md) | Contributor boundaries and AI controls |
| [AGENT_REQUIREMENTS.md](AGENT_REQUIREMENTS.md) | Agent capabilities, orchestration handoffs and PR acceptance limits |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Interfaces and containment implementation |
| [TESTING.md](TESTING.md) | Expected behavior and observed evidence |
| [TEAM.md](TEAM.md) | Participant roles and contribution templates |
| [METRICS_AND_RUBRICS.md](METRICS_AND_RUBRICS.md) | Official judging criteria mapped to evidence |
| [SCALING_AND_SDLC.md](SCALING_AND_SDLC.md) | Current deployment boundary and future work |
| [CHECKLIST.md](CHECKLIST.md) | Missing work, corrected claims, test gates and two recording storyboards |
| [Local verification](verification/local-2026-11-04.md) | Actual local checks and explicitly unverified target controls |

Account logins, payments, third-party form submissions, distributed execution, and enterprise tenancy guarantees are outside this version.
