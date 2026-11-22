# Hosting on Heroku + Vercel

> **Audience** — An operator deploying a public instance.
> **See also** — [Operations](../operations.md) · [MCP](../mcp.md) · [Data policy](../data-policy.md)
> **Status** — This is the deployment runbook. The repository changes it depends on are committed; the cloud resources are **not** created by the repository.

This runbook hosts the Next.js web app on **Vercel Hobby** and the FastAPI
service, mounted MCP adapter, and PostgreSQL/PostGIS on **Heroku**. Ingest
stays on GitHub Actions. It fits the GitHub Student Developer Pack's $13/month
Heroku credit: one Basic dyno (~$7) plus Heroku Postgres Essential-0 (~$5).
Vercel Hobby is free but **non-commercial**; move to Pro if the project ceases
to be a personal/open project.

```text
Vercel Hobby (free)
  web  ──HTTPS──▶  api.philfacilities.org (Heroku Basic dyno)
                    ├─ FastAPI /v1, /docs, /healthz
                    └─ mounted read-only MCP at /mcp
                    Heroku Postgres Essential-0 + PostGIS
GitHub Actions (free): source checks, approved refresh, discovery probes
Namecheap/Name.com: domain + first-year TLS
New Relic (Student Pack, free): monitoring
```

## 1. Repository prerequisites

Three files make this repository deployable with Heroku's Python buildpack:

- `.python-version` — Heroku's uv support requires it (`3.14` matches CI).
- `Procfile` — binds Heroku's `$PORT`; the API's `__main__.py` otherwise
  hardcodes 8000:
  ```text
  web: uvicorn philfacilities_api.main:app --host 0.0.0.0 --port $PORT
  ```
- `bin/post_compile` — the buildpack runs `uv sync --locked --no-default-groups`
  at the workspace root, which does not install uv **workspace members**. The
  API and MCP packages live in members, so the hook runs
  `uv sync --locked --all-packages --no-default-groups`.

The MCP adapter is mounted into the API app (see [MCP](../mcp.md) §3), so no
second dyno is needed. It still calls the public API over HTTP and holds no
database credentials.

The deployed app uses the `heroku-26` stack. Set it once with
`heroku stack:set heroku-26 -a <app>`; a stack change requires a redeploy before
it takes effect.

## 2. Heroku API, database, and MCP

Replace `<api-app>` with your app name and `<domain>` with your API hostname.

```bash
heroku login
heroku create <api-app> --region us
heroku git:remote -a <api-app>
heroku addons:create heroku-postgresql:essential-0 -a <api-app>
heroku pg:psql -a <api-app> -c 'CREATE EXTENSION IF NOT EXISTS postgis'
heroku pg:psql -a <api-app> -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm'
```

Heroku supplies `DATABASE_URL` as `postgres://…`, but Alembic and the apps need
`postgresql+psycopg://…`. Convert it and set the config vars:

```bash
DB_URL=$(heroku config:get DATABASE_URL -a <api-app> \
  | sed -E 's#^postgres(ql)?://#postgresql+psycopg://#')
heroku config:set \
  PHILFACILITIES_DATABASE_URL="$DB_URL" \
  PHILFACILITIES_ENV=production \
  PHILFACILITIES_CORS_ORIGINS="https://<web-domain>" \
  PHILFACILITIES_API_BASE_URL="https://<api-domain>" \
  PHILFACILITIES_MCP_ALLOWED_HOSTS="<api-domain>,<api-domain>:*" \
  PHILFACILITIES_MCP_ALLOWED_ORIGINS="https://<web-domain>" \
  PHILFACILITIES_MCP_FORWARDED_ALLOW_IPS="127.0.0.1" \
  -a <api-app>
```

`PHILFACILITIES_API_BASE_URL` is the MCP adapter's upstream API origin. Using
the public origin keeps one round trip through the Heroku router and preserves
the "client of the public API" boundary. Host/Origin validation is always on;
a host not in `PHILFACILITIES_MCP_ALLOWED_HOSTS` gets `421 Misdirected Request`.

Deploy and migrate:

```bash
git push heroku main
heroku run -a <api-app> \
  'DATABASE_URL="$PHILFACILITIES_DATABASE_URL" alembic -c apps/api/alembic.ini upgrade head'
curl -s https://<api-domain>/healthz
```

## 3. Load data with GitHub Actions

Never run ingest on the Heroku dyno: its filesystem is ephemeral. The workflow
in `.github/workflows/source-checks.yml` is already wired.

1. GitHub repo → **Settings → Secrets and variables → Actions → New repository
   secret** → `PHILFACILITIES_DATABASE_URL` = the same converted URL.
2. **Actions → Source monitoring → Run workflow** → tick **"Also refresh
   rights-cleared sources"**. This runs `scripts/refresh_approved_sources.sh`
   (PSGC, population, PhilHealth, NHFR, OSM health/education) idempotently
   through the publication gate.
3. Confirm with `curl -s https://<api-domain>/v1/statistics`.

The daily/weekly/monthly schedules then keep data fresh at no cost. To
preserve raw artifacts as [Ingestion](../ingestion.md) §5 requires, also add
`PHILFACILITIES_S3_*` secrets **and** add them to the workflow's `env:` block
(the workflow currently forwards only the database URL and alert webhook).

## 4. Vercel web app

Import the same GitHub repo. Configure:

| Setting | Value |
|---|---|
| Framework | Next.js (auto-detected) |
| Root Directory | **repository root** (not `apps/web`; pnpm needs the workspace files) |
| Build Command | `pnpm --filter @philfacilities/web build` |
| Output Directory | `apps/web/.next` |
| Install Command | `pnpm install --frozen-lockfile` |

Environment variables (set for **Production** and, if used, **Preview**):

```text
NEXT_PUBLIC_API_URL=https://<api-domain>
API_BASE_URL=https://<api-domain>
NEXT_PUBLIC_SITE_URL=https://<web-domain>
```

`NEXT_PUBLIC_*` values are inlined at build time, so they must exist **before**
the build and require a redeploy to change. Add a licensed basemap before
launch (see [ADR 0006](../decisions/0006-basemap-provider.md)):

```text
NEXT_PUBLIC_MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png
NEXT_PUBLIC_MAP_TILE_ATTRIBUTION=© Example Maps
NEXT_PUBLIC_MAP_TILE_MAXZOOM=20
```

## 5. Domains, TLS, and CORS

- **Web:** Vercel → Project → Settings → Domains → add `<web-domain>`; add the
  DNS records it gives you at the registrar. TLS is automatic.
- **API:** `heroku domains:add <api-domain> -a <api-app>` and
  `heroku certs:auto:enable -a <api-app>`; add the CNAME at the registrar.
- **CORS last:** `PHILFACILITIES_CORS_ORIGINS` is a comma-separated **exact**
  list (`config.py` does no wildcard matching). Include the apex and `www`
  web origins. Vercel preview URLs are not covered; add them explicitly or use
  previews only for UI work that does not call the API.
- The web CSP is generated per request in `apps/web/src/proxy.ts` from
  `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_MAP_TILE_URL`; verify with
  `curl -sI https://<web-domain> | grep -i content-security-policy`.

## 6. Verify end to end

```bash
curl -s https://<api-domain>/healthz                       # database: ok
curl -s https://<api-domain>/v1/statistics | jq
curl -s https://<api-domain>/mcp/readyz                    # mounted MCP readiness
curl -sI https://<web-domain> | grep -i content-security-policy
```

Then open the web app: the directory should list published facilities and the
map should load. Check the browser console for CSP or CORS errors.

## 7. Credit management

- Unused monthly credit **expires**; there is no rollover. Aim to use $12–13/mo.
- You need a card on file. It is charged only for usage above $13/mo.
- Paid **third-party** add-ons are not covered by the credit. Use the free
  New Relic Student Pack offer for monitoring; keep ingest on GitHub Actions.
- Check **Dashboard → Account → Billing → Current Usage** weekly and confirm
  the $13 credit line on each invoice.
- `heroku pg:info -a <api-app>` watches Essential-0's 1 GB limit. Upgrading to
  Essential-1 adds ~$4/mo beyond the credit.
- Set a reminder for month 22–23 of the 24-month program: after that, ~$12/mo
  goes to the card unless you migrate.

## 8. Known deviations from the operating guide

Record these in any launch review:

1. **Database roles.** `docs/operations.md` §4 asks for separate migration,
   ingest, and read-only API roles. Heroku Postgres Essential plans expose only
   the `owner` credential, so the API uses it. Separate roles require a
   production-tier plan (Standard-0, ~$50/mo).
2. **Raw store.** GitHub Actions writes raw releases to the runner's ephemeral
   `var/raw`; add S3-compatible storage as described in §3 before launch.
3. **`/mcp` rate limiting.** The API's per-IP limiter already wraps the mounted
   MCP endpoint, but a hosted MCP aggregates callers under one IP. An edge
   limit in front of `/mcp` is still a launch gate (see [MCP](../mcp.md) §7).

## 9. Live deployment values

| Item | Value |
|---|---|
| Heroku app | `philfacilities-api` (region `us`, stack `heroku-26`) |
| API URL | `https://philfacilities-api-f4c4b7a4d35d.herokuapp.com` |
| Vercel project | `philfacilities-web` (Git-connected to this repository) |
| Web URL | `https://philfacilities-web.vercel.app` |
| Vercel function region | `iad1` (project default) |

Both services deploy **only from GitHub `main`**: Vercel through its Git
integration (project Root Directory `apps/web`), and Heroku through
[`.github/workflows/deploy-heroku.yml`](../../.github/workflows/deploy-heroku.yml).
Never run `vercel deploy` or `git push heroku` from a workstation with a large
local `.venv`: the CLI uploads source files and can exhaust memory. The
`HEROKU_API_KEY` repository secret expires 2026-12-22 and must be rotated.

Verified 2026-11-22: `/healthz` and `/mcp/readyz` return `ok`, the Vercel page
renders with the nonce CSP, and `/v1/statistics` reports 229 274 published
facilities. The initial `Source monitoring` run published the approved sources
but exited non-zero: several PhilHealth loaders hit `ForeignKeyViolation` or
duplicate `release_facility_snapshot` errors, and one due-source check could not
reach Geofabrik. Those are data/ingestion signals, not deployment failures;
investigate before treating the load as complete.

### Free-tier quota constraint (important)

`heroku-postgresql:essential-0` is capped at **1 GB total** (including indexes
and TOAST). The first GitHub ingest run pushed the database to 1.31 GB and Heroku
flagged it as above limits. A full ingest writes ~4.5 GB of provenance
(assertions, source records, raw payloads), so it can never run on this plan.
The hosted database is therefore a **read-only public projection**, not an
ingestion target. The GitHub secret `PHILFACILITIES_DATABASE_URL` stays removed
so the scheduled `Source monitoring` workflow cannot refill the hosted database.

#### How updates reach Heroku

1. **Ingest locally.** Run the normal ingest CLI against the authoritative
   database on your machine. All releases, assertions, internal rows and raw
   payloads stay there.
2. **Build the projection.** `just publish` copies only public facilities,
   current locations, profiles, global lookups and a slim source-evidence layer
   into a scratch database, drops unused indexes, refreshes
   `stats.api_field_coverage`, vacuums, and writes a dump plus manifest under
   `var/publish/`. It never connects to Heroku.
3. **Deploy.** `scripts/publish_deploy.sh` uploads the dump and manifest as a
   GitHub release and triggers
   [`.github/workflows/publish-heroku.yml`](../../.github/workflows/publish-heroku.yml).
   The workflow verifies the checksum and migration revision, restores the
   projection, and runs `scripts/verify_public_projection.py` against the live
   API. If verification fails, re-run the workflow with the previous release tag.

The projection contains **229,274 public facilities** and their current
locations, profiles, slug aliases, functions/roles/services/contacts, agencies,
datasets, releases, population observations and geo lookups. It keeps slim
`source.records` (no raw payload) and `source.facility_source_links` (no evidence)
so detail pages and the publication gate work — the earlier 722 MB copy omitted
those tables and every facility detail request returned 404. It excludes
`attribute_assertions`, fusions, snapshots, change history, quality issues,
internal rows and non-current locations.

A local probe measured **~835 MB** after compaction; the first hosted publish
measured **842 MB**, leaving ~180 MB of headroom. Heroku's dashboard `Data Size`
metric lags behind the actual size; verify with
`SELECT pg_database_size(current_database())` in a one-off dyno rather than
trusting `heroku pg:info` immediately after a restore.

This is a deliberate no-cost trade-off: directory, map, detail, profiles,
sources metadata, statistics and downloads work; field-level assertions remain
in the authoritative local database only.

#### First hosted publish (verified 2026-11-22)

The projection was built from the authoritative local database with
`just publish` (199 MB dump, 229,274 public facilities, 720,104 slim records,
585,356 links), published as GitHub release
[`public-20261122`](https://github.com/marrrkkk/philfacilities/releases/tag/public-20261122),
and installed by
[workflow run 45036469147](https://github.com/marrrkkk/philfacilities/actions/runs/45036469147).
The workflow verified the checksum and the `0026_api_field_coverage_mv`
revision, restored with the PostgreSQL 18 client, and passed the API check.
Live verification: `/healthz`, `/v1/statistics`, a facility detail by id and
slug, `/v1/facilities/{id}?include=sources` (source_count 4), `/v1/fields` and
`/mcp/readyz` all returned 200; `/v1/statistics` reports 229,274; the web
detail page renders the facility name. A Heroku backup (`b001`) was captured
before the restore as a rollback point.
