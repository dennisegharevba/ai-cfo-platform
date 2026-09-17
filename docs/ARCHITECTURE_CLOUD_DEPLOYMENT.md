# Cloud deployment — running this platform from anywhere

## Before you start: what actually changes

Running this on a cloud server instead of your own PC means your real
credentials (Alpaca, FRED, Telegram, etc.) live on a machine you don't
physically control the way you control your own laptop. That's a real
security decision, not just a convenience upgrade — treat the server
with the same care you'd treat your own machine, and read the
"Securing the dashboard" section below before exposing anything to the
public internet.

## What's been built for this

- `Dockerfile` — packages the whole app into a portable container image
- `.dockerignore` — makes sure `.env` (real secrets) is NEVER baked into
  the image; secrets are injected at container *runtime* instead (see
  below for why that distinction matters)
- `docker-compose.yml` — runs the dashboard (and, optionally, the
  continuous risk monitor) as managed services

**Honest limitation**: none of this has been build-tested — there's no
Docker available in the environment these were written in, so this
hasn't been run end-to-end the way the Alpaca connector eventually was.
Treat it the way the Alpaca connector was treated before its first real
test: plausible, carefully written, but genuinely unverified until you
run it for real.

## Choosing a provider (pricing as of mid-2026, verify current prices before buying)

For what this needs — one small server running a lightweight dashboard
and maybe one background Python loop — the cheapest realistic tier is
plenty. A few real options:

| Provider | Entry price | Notes |
|---|---|---|
| **Oracle Cloud "Always Free"** | **$0/mo, forever** — not a trial or credit | Genuinely permanent, and far more powerful than this project needs (up to 4 ARM cores, 24GB RAM, 200GB storage). Two real caveats: it's ARM architecture, not x86 (Docker's official `python` images support ARM64 automatically, so the existing `Dockerfile` should work unmodified — but this hasn't been verified, same honest limitation as the rest of this guide); and the free ARM instance can be genuinely hard to provision in some regions due to high demand ("out of capacity" errors are commonly reported). Requires a credit card for identity verification at signup, but you are not charged for staying within the free limits. No uptime SLA — a real trade-off for $0. |
| **DigitalOcean** | ~$5-6/mo for 1GB RAM (their absolute cheapest $4/mo tier has only 512MB, likely too tight for Docker + Streamlit comfortably) | Not free, but new accounts commonly get a signup credit worth several months of running time. Recommended if Oracle's free tier proves hard to provision — cleanest beginner experience, excellent documentation |
| **Linode (Akamai)** | ~$5/mo for 1GB RAM | Very similar to DigitalOcean in price and simplicity |
| **Hetzner** | Noticeably cheaper at comparable specs (roughly a third of DigitalOcean's price at the same RAM tier) | Worth considering once you're comfortable with the setup and want to optimize cost; EU-centric data centers, slightly less beginner-oriented |

**Recommendation**: try Oracle Cloud's Always Free tier first if you want genuinely free, permanent hosting — it's real, not a trial, and this project barely uses a fraction of what it offers. If provisioning the free ARM instance proves difficult (a known, common issue), fall back to DigitalOcean — the signup credit alone likely covers your first several months for a few dollars a month after that.

## Step-by-step

### 1. Create the server
Sign up, create a "Droplet" (DigitalOcean's term) or equivalent — pick
Ubuntu (a recent LTS version), the smallest 1GB RAM tier, and a data
center region near you.

### 2. Connect and install Docker
```bash
ssh root@your_server_ip
curl -fsSL https://get.docker.com | sh
apt install docker-compose-plugin -y
```

### 3. Get the code onto the server
Simplest approach — zip your local project folder (excluding `.env` and
`.git`) and transfer it:
```powershell
# From your Windows machine, in the project folder:
Compress-Archive -Path * -DestinationPath ai-cfo-platform.zip -Force
scp ai-cfo-platform.zip root@your_server_ip:/root/
```
Then on the server:
```bash
apt install unzip -y
unzip ai-cfo-platform.zip -d ai-cfo-platform
cd ai-cfo-platform
```

### 4. Set up `.env` — ON THE SERVER, never committed or transferred insecurely
```bash
nano .env
```
Paste in the same credentials from your local `.env` (FRED, EIA, SEC,
Telegram, Alpaca). This file stays on the server only — it's excluded
from the Docker image by `.dockerignore`, and should never be copied
into any git repository if you set one up later.

### 5. Run it
```bash
docker compose up -d --build
```
Check it's running:
```bash
docker compose ps
docker compose logs -f dashboard
```

### 6. Visit it
`http://your_server_ip:8501` — but see the next section before doing
this for real.

## Securing the dashboard — read this before exposing port 8501 publicly

As shipped, `docker-compose.yml` exposes the dashboard on port 8501
with **no authentication at all**. Once your Alpaca credentials are
set, that dashboard shows real account equity and positions. Anyone who
finds that URL — and on the open internet, automated scanners find open
ports constantly — could view your real (paper, for now) account data.

**Minimum recommended step**: restrict the firewall so port 8501 is
only reachable from your own IP address, not the whole internet:
```bash
ufw allow from YOUR_HOME_IP to any port 8501
ufw allow 22
ufw enable
```
(Find your current IP by searching "what is my IP" from your own
device — it can change if your home internet doesn't have a static IP,
in which case you'd need to update this rule when it does.)

**Better step, if you want real from-anywhere access**: put a reverse
proxy in front of the dashboard with real authentication and HTTPS.
[Caddy](https://caddyserver.com) is a genuinely simple option for
this — a few lines of config handle automatic HTTPS and basic auth
without the complexity of nginx. This is a real, separate piece of
work — ask if you want help setting it up once the basic deployment is
running.

## The risk monitor — commented out by default, on purpose

`docker-compose.yml` includes a `risk-monitor` service, commented out.
It's read-only (see `docs/ARCHITECTURE_RISK_MONITORING.md` — nothing it
does can place an order), but running it continuously means real
Telegram alerts firing unattended if `TELEGRAM_*` is configured.
Uncomment it once you've watched the dashboard run correctly for a
while and are ready for genuinely unattended operation.

## Updating the deployment later

When new code is delivered as a zip (the same way it has been all
session): transfer the new files the same way as step 3, then:
```bash
docker compose up -d --build
```
This rebuilds the image with the new code and restarts the services —
`.env` on the server is untouched, so credentials don't need re-entering.

## What this does NOT include

- No automated backups of the SQLite report-history database — data
  written inside the container's filesystem is lost if the container
  is removed and rebuilt (not restarted — `docker compose restart`
  preserves it; a full rebuild does not, without adding a persistent
  volume, which wasn't set up here to keep this first version simple)
- No monitoring/alerting on the SERVER itself (disk space, uptime,
  whether Docker crashed) — worth adding if this becomes long-running
  infrastructure you depend on
- No automated deployment pipeline — every update is a manual transfer
  and rebuild, as described above
