# Architecture and Trust Boundaries

Blast Radius Zero separates the public application, trusted coordination, and untrusted execution paths so each privilege boundary is visible in the repository and deployment topology.

## Service map

```text
Public                                  Trusted host                         Untrusted

Browser ──HTTPS──► Caddy ──► web ──► core/api ──► Redis
                                      │
                                      └──► core/coordinator ──► container runtime
                                                   │               │
                                                   │               ├──► sandbox/python
                                                   │               └──► sandbox/browser
                                                   │                         │
                                                   └──► Vultr Inference      └──► Squid
                                                        (optional)                 │
                                                                                  └──► allowlisted HTTPS
```

## Repository boundaries

| Directory | Trust level | Responsibilities |
| --- | --- | --- |
| `core/` | Trusted | Session and CSRF enforcement, validation, task admission, model calls, approval state, sandbox lifecycle, artifact checks, and cleanup |
| `sandbox/` | Untrusted execution definitions | Minimal Python image, fixed Playwright runner, Chromium seccomp profile, and runtime-specific build files |
| `web/` | Public application | Dashboard, same-origin API requests, terminal rendering, screenshots, approval UI, and fallback states |
| `deploy/` | Privileged operator policy | Caddy routes, Squid package/config generation, Vultr-host firewall policy, and preflight checks |
| `verification/` | Untrusted historical evidence | Sanitized logs and reports. Evidence describes a specific run and does not configure the system. |

## Control-plane rules

- The API validates requests and stores admitted work. It does not execute submitted Python.
- The coordinator is the only application process with the Docker socket. Treat it as host-privileged.
- Redis is private to the application network. Sandboxes cannot reach it.
- Provider credentials stay in the trusted core environment and are never copied into sandbox environment maps.
- Model output, stdout, screenshots, page content, and generated artifacts are untrusted data.
- Policy decisions and verified events come from trusted enforcement code, not strings printed by a task.

## Python execution boundary

The Python runtime starts non-root with no external network, a read-only root filesystem, dropped capabilities, `no-new-privileges`, bounded tmpfs, 256 MiB memory, 0.5 CPU, 64 PIDs, and a 10-second deadline. The coordinator limits combined logs and artifacts and removes the container on every terminal path.

Docker network mode `none` disables external connectivity but retains loopback. Docker shares the host kernel, so this design reduces blast radius without claiming a mathematical zero-risk boundary.

## Browser execution boundary

The browser accepts fixed JSON operations rather than model-supplied JavaScript. Each stage gets a fresh internal Docker network. Chromium reaches a trusted Squid peer, and host policy filters Squid's actual destination addresses. Browser readiness fails closed if host policy cannot be verified.

A hostname allowlist alone does not prevent DNS rebinding. The host destination policy is an independent required control.

## Side-effect approval

Form preparation stores exact values, destination, revision, and screenshot, then destroys that browser. A five-minute, session-owned approval authorizes a fresh browser to revalidate the form and submit a payload-bound permit. The form service records one idempotent receipt. Vision output cannot grant approval.

## Runtime roadmap

The current runtime is Docker on a dedicated Vultr VM. Native-backed sub-10ms isolation is a roadmap item. Any Native adapter must preserve the existing contract: non-root execution, secret exclusion, bounded resources, network policy, trusted evidence, explicit timeout termination, and cleanup on every path.

See [IMPLEMENTATION.md](../IMPLEMENTATION.md) for field-level contracts and [TESTING.md](../TESTING.md) for observed evidence.
