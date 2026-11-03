# Metrics and Hackathon Alignment

The [official Vultr Agent Rush event page](https://lablab.ai/ai-hackathons/vultr-hackathon) lists **Application of Technology**, **Presentation**, **Business Value**, and **Originality**. It does not publish percentage weights for these categories. The mapping below is our evidence plan, not an organizer scoring formula or a prediction of a score.

## Required challenge evidence

For Blast Radius Zero, the project uses Vultr hosting for the web application and backend, Vultr Serverless Inference for live agent calls, and isolated execution environments that return real output. Presets complement live inference; they do not establish that the live agent path has been demonstrated.

The final submission should link the public repository, working demo URL, architecture/use-case explanation, recorded demo, and an observed containment moment. Check the current organizer instructions before submitting.

## Criterion mapping

| Official criterion | Evidence to present | Measured result | Evidence link |
| --- | --- | --- | --- |
| Application of Technology | Vultr-hosted control plane and dashboard; live Vultr Inference; executed Python/browser tasks with artifacts | Not yet measured | Add deployment, task, and recording links |
| Presentation | Clear dashboard; real streaming output; screenshots; concise approval summary; understandable failures and preset fallback | Not yet measured | Add screenshots and demo timestamps |
| Business Value | A concrete CSV/research workflow; explicit containment boundary; auditable approval before a side effect | Not yet measured | Add user scenario and observed workflow |
| Originality | Dual sandbox policies; packaged proxy plus actual-destination filtering; immutable approval and idempotent receipt | Not yet measured | Add architecture and test evidence |

## Engineering measurements

Record the sample size and environment with latency or resource measurements. Do not report a percentile from one successful task as a stable performance result.

| Metric | Measurement method | Current result |
| --- | --- | --- |
| Successful workflow completion | Passed/attempted representative tasks, separated by code/browser/preset/live AI | Real local CSV HTTP/SSE/artifact smoke passed; live AI/browser pending |
| First-output latency | Admission-to-first SSE output timestamp | First stdout observed while task was running; no latency benchmark |
| End-to-end latency | Admission-to-final task state; report sample size and p50/p95 when meaningful | One local CSV smoke: 3.095 s (n=1); no p50/p95 |
| Containment regression coverage | Passed/attempted checks from `TESTING.md`, with skipped checks listed | 99 application tests and 12 real local Python checks passed; browser/Vultr gates pending |
| Protected-service exposure | Controlled sentinel hit count during negative network tests | Not yet measured |
| Deadline enforcement | Observed container duration and cleanup after timeout | Local Python timeout/cleanup integration check passed; repeat on Vultr |
| Resource enforcement | Effective Docker settings and observed CPU/memory/PID outcomes | Local applied flags, memory/PID/tmp/output tests passed; CPU profile not benchmarked |
| Residual resources | BRZ-labelled containers/networks remaining after completion and restart cleanup | Not yet measured |
| Approval correctness | Unauthorized/expired/tampered attempts rejected; duplicate submissions produce one receipt | Local state/API tests passed; actual browser stages pending |
| Model usage | Provider requests and reported input/output tokens per task | Not yet measured |
| Preset inference use | Provider-client request count for preset tasks | Real CSV preset: 0 provider requests; dispatch/provider-spy tests passed |

## Recommended recording sequence

1. Show the Vultr-hosted dashboard and explain the control-plane/execution boundary.
2. Run CSV analysis and show actual streamed output plus a downloaded artifact.
3. Run the Python network probe and show its observed denial and enforced policy.
4. Run browser research and display its screenshot, source links, and timestamp.
5. Attempt metadata access and show trusted denial evidence, without displaying metadata content.
6. Prepare the demo form, inspect its screenshot and exact fields, approve it, and display one receipt.
7. Show labelled preset availability when live AI is disabled, then close with the shared-kernel limitation.

Keep the walkthrough within the organizer's current recording requirements. Do not call a source-code setting, a mocked provider response, or a prewritten terminal string an observed containment result.

## Claims to avoid

Do not claim mathematical proof of zero risk, “100% secure,” guaranteed scoring, published rubric weights, a fixed dollar-per-task price, or an already deployed/verified service without evidence. The submission should show useful work and tested controls under a stated threat model.

Local evidence and storage-fault limits: [verification/local-2026-11-04.md](verification/local-2026-11-04.md). These are not target-host or official judging scores.
