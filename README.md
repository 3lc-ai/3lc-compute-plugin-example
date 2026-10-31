# 3lc-compute-plugin-example — Mission Control 🚀

A runnable tour of everything a [3LC compute service](https://github.com/3lc-ai) plugin
can do, staged as a rocket launch: `run_job(ctx)` jobs with live progress/metrics/telemetry,
a clean failure and abort, custom REST routes (JSON, 404, binary PNG, raw upload, the Hub's
result shape), the `PLUGIN_API`/`TlcData`/`PluginJobs` UI bridge, the shared data-source
picker, lifecycle hooks, quick actions — and a test suite that runs all of it without a
compute service.

This repo is for **reading and running**. To start a plugin of your own, instantiate the
[**plugin template**](https://github.com/3lc-ai/3lc-compute-plugin-template) instead — then
crib from here as you grow. The full contract reference lives in the
[**plugin author guide**](https://3lc-ai.github.io/3lc-compute-plugin-sdk/plugin-guide.html)
(`3lc-compute-plugin-sdk`).

The plugin is `venv`-isolated: the host reads [`plugin.toml`](src/tlc_plugin_example/plugin.toml)
**without importing it**, provisions the plugin its own virtual environment, and runs it
out-of-process behind a reverse proxy. Dependencies live in the plugin's extra in
[`pyproject.toml`](pyproject.toml) and never touch the host venv.

It is built against the SDK's **0.6 line**, the contract the Hub and Compute Service **1.2**
implement (`min_service_version = "1.2.0"` in the manifest).

## Try it in two minutes

```bash
git clone https://github.com/3lc-ai/3lc-compute-plugin-example
# Point a compute service at the src/ folder (repeatable flag, or use the
# TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS env var). TLC_DATA_SOURCE_ROOTS names the folders
# the cargo-manifest picker may browse; without it the picker offers buckets only.
TLC_DATA_SOURCE_ROOTS=~ 3lc-compute --plugin-dir /path/to/3lc-compute-plugin-example/src
```

The service discovers the plugin, provisions it a venv (`uv sync --extra example` against
this repo — first run takes a few seconds), and it appears in the Hub sidebar under
**Examples**. Open **Mission Control**, poll go/no-go, recruit some crew, and launch a mission —
then watch the same job stream into the generic Queue & Progress panel.

No Hub handy? The whole surface also speaks curl (on a keyless dev service; a service under an
API key wants an `Authorization: Bearer …` header on every call but the auth-exempt patch):

```bash
curl http://localhost:5020/api/plugins/manifest/example
curl 'http://localhost:5020/api/plugins/example/compute?station=all'      # go/no-go
curl http://localhost:5020/api/plugins/example/crew                       # custom route
curl http://localhost:5020/api/plugins/example/crew/elvis                 # → 404
curl -o patch.png http://localhost:5020/api/plugins/example/patch.png     # binary route, auth-exempt
curl -X POST http://localhost:5020/api/plugins/example/run \
  -H 'Content-Type: application/json' -d '{"destination": "Mars"}'        # → {job_id, status, namespace}
curl -X POST http://localhost:5020/api/plugins/example/run \
  -H 'Content-Type: application/json' -d '{"destination": "Sun"}'        # a ctx.fail() on the job card
curl http://localhost:5020/api/plugins/jobs                               # the generic job list
```

## What to read, in order

1. [`plugin.toml`](src/tlc_plugin_example/plugin.toml) — every manifest field, annotated: the
   service and Hub floors, `remote_capable`, `data_inputs` / `data_outputs`, `credentials`,
   `node_routes`, `auth_exempt_paths`.
2. [`__init__.py`](src/tlc_plugin_example/__init__.py) — `compute()`, `run_job(ctx)` with
   `ctx.fail()`, `ctx.project_root_url` and `ctx.identity`, the lifecycle hooks.
3. [`routes.py`](src/tlc_plugin_example/routes.py) — custom REST routes, one of every response
   shape, including the Hub's `{success, message, details}` result.
4. [`patch.py`](src/tlc_plugin_example/patch.py) — a generated binary asset (stdlib-only PNG).
5. [`ui.html`](src/tlc_plugin_example/ui.html) — the full `PLUGIN_API` / `PluginJobs` tour:
   the host's `.btn` / `.form-select` classes, scoped `.example-…` styles, `showResult`,
   `job.error`, the data-source picker, a Cancel that works before the first update.
6. [`tests/test_plugin.py`](tests/test_plugin.py) — the routes through
   `tlc_plugin_sdk.harness`, `run_job` through a recording `JobContext`, the fragment through
   `tlc_plugin_sdk.lint`.

## The dev loop

Code edits go live with a reload — no service restart:

```bash
# Reload everything under the plugin dir (re-provisions venvs when deps changed):
curl -X POST http://localhost:5020/api/admin/plugins/dirs/reload \
  -H 'Content-Type: application/json' \
  -d '{"directory": "/path/to/3lc-compute-plugin-example/src"}'
# Or retire just this plugin's worker; the next request cold-starts on the code on disk:
curl -X POST http://localhost:5020/api/admin/plugins/example/worker/stop
```

Test and lint like CI does:

```bash
uv sync --extra example                 # the venv the host would provision, plus pytest
uv run pytest -q                        # harness + JobContext + lint, no service needed
uv run python -m tlc_plugin_sdk.lint src/   # the fragment against the Hub's styling rules
uvx --from 'ruff>=0.15,<0.16' ruff check .
uvx --from 'ruff>=0.15,<0.16' ruff format .
```

To develop against a sibling SDK checkout, override its source **uncommitted**:

```toml
# pyproject.toml [tool.uv.sources]  (local dev only — do not commit)
3lc-compute-plugin-sdk = { path = "../3lc-compute-plugin-sdk", editable = true }
```

### Editor autocomplete for `ui.html`

The fragment talks to the host through `window.PLUGIN_API` / `window.PluginJobs`, and both are
**typed**: the declaration ships inside the pip-installed SDK wheel, and the repo-root
[`jsconfig.json`](jsconfig.json) points TypeScript at it. Run `uv sync` once (creates `.venv/`)
and VS Code autocompletes the whole bridge inside `ui.html` — no node, no build step.

## Install from a catalog

This repo bakes its own shop listing: [`catalog.json`](catalog.json) — a static JSON file
with the plugin's versions, a raw copy of the manifest (so the Hub can render a card and check
compatibility **without downloading anything**), a `latest` tag naming the release to offer,
and an install source pointing back at this repo.

Which catalogs a compute service reads is **configuration**, because a catalog's entries are
trusted install sources (the default install policy, `catalog-only`, installs nothing a catalog
did not list). Name it in the environment the service starts with:

```bash
TLC_COMPUTE_PLUGIN_CATALOG_URLS=https://raw.githubusercontent.com/3lc-ai/3lc-compute-plugin-example/main/catalog.json
```

…or as `compute-service.plugins.catalog-urls` in the service's configuration file (or a
Config Service scope, for a deployment); the Hub's Plugins page lists the catalogs in force
under **Plugin sources**. A change applies at the next catalog read, no restart. **Mission
Control** then shows up as a card; **Add** registers it, and the first visit materializes a
managed venv from the git source.

## License

Apache-2.0 — see [LICENSE](LICENSE).
