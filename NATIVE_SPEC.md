# Native Provider Integration Specification

## Status and verified boundary

`SANDBOX_RUNTIME=docker` remains the production default and the only execution provider with tested containment behavior. The provider factory now separates the coordinator from that implementation:

```text
Coordinator -> BaseSandboxProvider
               |-> DockerSandboxProvider -> existing SandboxRunner
               `-> NativeSandboxProvider -> fail closed (no execution API)
```

The public [`withnative/native`](https://github.com/withnative/native/blob/94352f9d90e62720e23c66269e2fe663f205e1c7/SELF_HOSTING.md) snapshot at commit `94352f9d90e62720e23c66269e2fe663f205e1c7` provides a Rust `mcp-stdio` binary backed by a local SQLite database. Its documented interface does **not** provide ephemeral Python execution, Playwright execution, container creation, resource quotas, network policy, or a `native run --ephemeral` command. It is AGPL-3.0-only.

For that reason, setting `SANDBOX_RUNTIME=native` reports the worker unready and rejects work. It never executes a host subprocess and never silently falls back to Docker. The Native MCP binary may be installed for future context/audit experiments, but it is not an enforcement boundary.

## Provider contract

`backend/brz/sandbox_provider.py` defines four operations:

- `initialize()` verifies provider prerequisites and returns code/browser readiness.
- `exec_code()` executes bounded Python with optional staged CSV data, streamed events, and cancellation.
- `exec_browser()` executes one fixed browser operation with events and cancellation.
- `teardown()` removes resources owned by the coordinator.

`DockerSandboxProvider` delegates these operations to the existing, independently tested Docker lifecycle. The adapter does not accept task-controlled images, mounts, network settings, resource settings, commands, or cleanup policy.

## Runtime selection

`SANDBOX_RUNTIME` is administrator-only configuration:

| Value | Behavior |
| --- | --- |
| `docker` | Uses the verified Docker implementation. |
| `native` | Fails readiness and returns `infrastructure_error`; nothing executes. |
| Any other value | Configuration startup fails. |

Switching providers must not happen through an API request or model output.

## Required gates before Native execution can be enabled

A future Native execution implementation must satisfy every affected row in `AGENT_REQUIREMENTS.md`, including:

1. **Published execution interface:** an upstream, versioned code and browser API whose semantics are verified against a pinned source or artifact digest.
2. **Independent containment:** non-root identity, read-only root, dropped capabilities, no privilege escalation, syscall policy, fixed images, no host mounts or credentials, and no Docker/host management socket in the guest.
3. **Code networking:** external networking disabled independently of generated-code validation, including DNS and direct-IP probes.
4. **Browser networking:** isolated worker network, approved HTTPS via the packaged proxy, actual-destination host filtering, metadata/private/host denial, and no direct bypass.
5. **Resource bounds:** effective 256 MiB/0.5 CPU/64 PID/10-second code limits and 512 MiB/1 CPU/256 PID/30-second browser limits, measured at the runtime boundary.
6. **Bounded I/O:** 64 KiB source, 2 MiB CSV, 1 MiB combined logs, 8 MiB total artifacts, safe archive handling, and backpressure.
7. **Lifecycle:** explicit termination and purge on success, failure, timeout, output overflow, cancellation, controller restart, and runtime failure.
8. **Evidence:** target-host runtime inspection, cleanup evidence, negative network tests, browser sentinel tests, and retained benchmark samples.

Only after those gates pass may the factory report `ready=true` for Native. No claimed latency improvement can substitute for a failed containment gate.

## Provisioning and IPC

Run `bash scripts/deploy-vultr.sh` on the intended Ubuntu 24.04 x86_64 VM. The script:

- installs Rust through a checksum-verified `rustup-init` and pins Rust 1.98.0;
- checks out a pinned Native commit and builds `mcp-stdio` with `cargo --locked`;
- runs the fixed `engine_info` JSON-RPC probe against a disposable database;
- writes local paths to `/etc/blast-radius-zero/native.env` with mode `0600`;
- opens no Native network port.

Native MCP uses child-process stdio rather than a daemon socket. Do not invent a TCP/Unix daemon binding around it without a separate authenticated protocol and threat review.

## Measurements

`backend/tests/test_native_latency.py` optionally measures cold startup plus an `engine_info` round trip when `BRZ_NATIVE_INTEGRATION=1`. That number is **MCP context-engine startup latency**, not sandbox cold-start latency. There is currently no honest Native-vs-Docker execution comparison because Native does not execute code in the published interface.

Content was rephrased from the linked Native self-hosting documentation for licensing compliance.
