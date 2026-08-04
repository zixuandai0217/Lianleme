# Lean Server Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the current React and FastAPI project on `114.55.137.200` with a resource-efficient, restart-safe production setup.

**Architecture:** Nginx serves the Vite production bundle and proxies `/api/` plus `/health` to a loopback-only FastAPI process. FastAPI runs from a Python virtual environment under systemd and uses the project's supported SQLite configuration so the 1.6 GiB server does not need the repository's heavier PostgreSQL, Redis, and MinIO container stack.

**Tech Stack:** Ubuntu 24.04, Nginx, systemd, Python 3.12 virtual environment, FastAPI/Uvicorn, React/Vite

---

### Task 1: Verify the deployment input

**Files:**
- Verify: `web/package.json`
- Verify: `backend/pyproject.toml`
- Verify: `backend/tests/`

**Step 1:** Run `npm ci` in `web/` to install the locked frontend dependencies.

**Step 2:** Run `npm run test:unit -- --run` and require a zero exit status.

**Step 3:** Run `npm run build` and require a zero exit status plus a populated `web/dist/`.

**Step 4:** Run the backend test suite with the locked Python environment and require a zero exit status.

### Task 2: Prepare the clean server

**Files:**
- Create remotely: `/opt/lianleme/`
- Create remotely: `/var/www/lianleme/`

**Step 1:** Install Nginx and Python virtual-environment support from Ubuntu packages.

**Step 2:** Create a 1 GiB swap file because the server has only 1.6 GiB RAM and no existing swap.

**Step 3:** Create application, persistent-data, and static-site directories with restricted ownership.

### Task 3: Publish application artifacts

**Files:**
- Deploy: `backend/app/`
- Deploy: `backend/alembic/`
- Deploy: `backend/pyproject.toml`
- Deploy: `backend/uv.lock`
- Deploy: `web/dist/`
- Create remotely: `/etc/lianleme/lianleme.env`

**Step 1:** Synchronize backend source while excluding local databases, environment files, caches, and virtual environments.

**Step 2:** Synchronize the verified Vite build to `/var/www/lianleme/`.

**Step 3:** Create a server-only environment file with generated JWT and AES secrets, the public-IP CORS origin, and only configured external-provider credentials from the local environment. Keep the application compatibility mode required by the current Web quick-login flow, and block the development administrator login at Nginx.

**Step 4:** Create the virtual environment and install the backend package plus its locked runtime dependencies.

### Task 4: Configure persistent services

**Files:**
- Deploy: `infra/server/lianleme.service` to `/etc/systemd/system/lianleme.service`
- Deploy: `infra/server/nginx-ip.conf` to `/etc/nginx/sites-available/lianleme`
- Link remotely: `/etc/nginx/sites-enabled/lianleme`

**Step 1:** Configure systemd to bind Uvicorn only to `127.0.0.1:8000`, restart on failure, and load the protected environment file.

**Step 2:** Configure Nginx to serve the React bundle with SPA fallback and proxy the API, health endpoint, and streaming responses.

**Step 3:** Validate configuration, start both services, and enable them at boot.

### Task 5: Verify the production result

**Files:**
- Verify remotely: systemd status and journal
- Verify externally: `http://114.55.137.200/`
- Verify externally: `http://114.55.137.200/health`

**Step 1:** Require `systemctl is-active` and `systemctl is-enabled` to succeed for both services.

**Step 2:** Require the loopback backend health endpoint to return the expected JSON payload.

**Step 3:** Require the public health endpoint and React index to return HTTP 200.

**Step 4:** Restart both services and repeat the public checks to prove restart recovery.

**Step 5:** Inspect open ports and confirm Uvicorn is not publicly exposed.

### Task 6: Install the supplied SSH public key

**Files:**
- Read locally: `/Users/edy/Downloads/测试.pem`
- Modify remotely: `/root/.ssh/authorized_keys`

**Step 1:** Restrict the private key to mode `0600` and validate it with `ssh-keygen`.

**Step 2:** Derive the public key locally and append it idempotently to root's authorized keys over the authenticated password connection.

**Step 3:** Require a non-interactive SSH login using only the supplied key to succeed.

### Task 7: Issue a trusted certificate for the public IP

**Files:**
- Create remotely: `/etc/letsencrypt/live/114.55.137.200/`

**Step 1:** Install Certbot 5.4 or newer from the official Snap package.

**Step 2:** Verify that the active Webroot serves an HTTP-01 challenge file from the public Internet.

**Step 3:** Request and validate a staging IP certificate with the `shortlived` profile.

**Step 4:** Remove the staging lineage and request the production IP certificate.

### Task 8: Enable HTTPS and automatic renewal

**Files:**
- Modify: `infra/server/nginx-ip.conf`
- Create: `infra/server/certbot-reload-nginx.sh`
- Deploy remotely: `/etc/nginx/sites-available/lianleme`
- Deploy remotely: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`

**Step 1:** Keep HTTP-01 reachable on port 80 and redirect all other HTTP requests to HTTPS.

**Step 2:** Serve the SPA and API on port 443 with the trusted IP certificate, while explicitly denying common sensitive-file probes.

**Step 3:** Validate Nginx before reload and require external HTTPS, certificate-chain, SPA, health, login, and SSE checks to succeed.

**Step 4:** Install a deploy hook that validates and reloads Nginx after renewal.

**Step 5:** Run a Certbot dry-run renewal and verify the renewal timer is enabled.
