# Setup and Operation

## Supported target

The containment deployment targets a dedicated Ubuntu 24.04 x86_64 Vultr Cloud Compute VM with Docker Engine 28+ and the Docker Compose plugin. Configure DNS A records for the application and demo-form domains to the VM's public IPv4 address.

Allow inbound TCP 80, 443, and 8443 in the Vultr firewall. Restrict SSH to administrator source addresses. Do not expose Redis, the FastAPI port, the Next.js port, or Squid publicly.

## Configuration

From the repository root:

```bash
cp .env.example .env
chmod 600 .env
```

Set these values in `.env`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_DOMAIN` | Yes | Public dashboard hostname |
| `DEMO_DOMAIN` | Yes | Dedicated demo-form hostname |
| `ACME_EMAIL` | Yes for public TLS | ACME registration contact |
| `DEMO_IP` | Yes for browser mode | Public VM address used by destination policy |
| `EGRESS_DNS` | Yes for browser mode | Resolver allowed by host policy |
| `BROWSER_DOMAINS` | Yes for browser mode | Comma-separated approved HTTPS hostnames |
| `AI_ENABLED` | No | Defaults to `false` |
| `VULTR_API_KEY` | Only for live AI | Vultr Inference subscription key |
| `VULTR_TEXT_MODEL` | Only for live AI | Accessible text model ID |
| `VULTR_VISION_MODEL` | For vision checks | Accessible vision-capable model ID |
| `NATIVE_API_KEY` | No | Reserved for a future Native adapter; unused today |

Never place real values in `.env.example`. Keep `.env` readable only by the deployment operator.

## Build and start

```bash
docker compose --profile images build
sudo ./deploy/install-firewall.sh --demo-ip YOUR_VM_PUBLIC_IP --dns 1.1.1.1
docker compose up -d
./deploy/preflight.sh
```

Read `deploy/install-firewall.sh` before running it. It changes BRZ-owned host firewall chains. Use the VM's real public IPv4 address; never copy a documentation address into production.

Open `https://APP_DOMAIN` after Caddy obtains certificates. The isolated demo form listens at `https://DEMO_DOMAIN:8443`.

## Local core development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r core/requirements-dev.txt
PYTHONPATH=core .venv/bin/python -m pytest core/tests -m 'not integration' --fail-on-skip
```

For interactive local work, start Redis, set `REDIS_URL` and `APP_ORIGIN=http://localhost:3000`, then run the API and coordinator as separate processes. Local execution does not prove target-host firewall policy.

## Local web development

```bash
cd web
npm ci
npm run typecheck
npm run build
npm run dev
```

The development server binds to loopback. Configure the same-origin API route as described by the existing Next.js configuration.

## Verification

Before changing deployment status or making containment claims:

1. Run the core application suite.
2. Run the web typecheck and production build.
3. Build all sandbox images.
4. Install host policy on an isolated Linux Docker host.
5. Run `deploy/preflight.sh`.
6. Execute the containment matrix in [TESTING.md](../TESTING.md).
7. Retain a sanitized report that identifies the host, runtime versions, date, command, outcome, skips, and unverified areas.

Do not treat source inspection, Compose validation, or a Docker CLI without a responsive daemon as runtime containment evidence.

## Secret response

If a credential appears in a commit or CI log:

1. Revoke and rotate it immediately.
2. Remove it from current files and logs.
3. Review the full Git object history with a secret scanner.
4. Rewrite history with a reviewed `git filter-repo` rule if exposure must be removed.
5. Force-update only after coordinating with every contributor; all old clones remain sensitive.

History rewriting is intentionally not part of bootstrap because it is destructive and requires explicit owner approval.
