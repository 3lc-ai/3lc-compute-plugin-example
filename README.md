# 3lc-compute-plugin-example — Mission Control 🚀

A runnable tour of everything a [3LC compute service](https://github.com/3lc-ai) plugin
can do, staged as a rocket launch: `run_job(ctx)` jobs with live progress/metrics/telemetry
and abort, custom REST routes (JSON, 404, binary PNG, raw upload), the
`PLUGIN_API`/`TlcData`/`PluginJobs` UI bridge, lifecycle hooks, and quick actions.

This repo is for **reading and running**. To start a plugin of your own, instantiate the
[**plugin template**](https://github.com/3lc-ai/3lc-compute-plugin-template) instead — then
crib from here as you grow. The full contract reference lives in the
[**plugin author guide**](https://github.com/3lc-ai/3lc-compute-plugin-sdk/blob/main/docs/plugin-guide.md)
(`3lc-compute-plugin-sdk`).

The plugin is `venv`-isolated: the host reads [`plugin.toml`](src/tlc_plugin_example/plugin.toml)
**without importing it**, provisions the plugin its own virtual environment, and runs it
out-of-process behind a reverse proxy. Dependencies live in the plugin's extra in
[`pyproject.toml`](pyproject.toml) and never touch the host venv.

## Try it in two minutes

```bash
git clone https://github.com/3lc-ai/3lc-compute-plugin-example
# Point a compute service at the src/ folder (repeatable flag, or use the
# TLC_COMPUTE_EXTERNAL_PLUGIN_DIRS env var):
3lc-compute --plugin-dir /path/to/3lc-compute-plugin-example/src
```

The service discovers the plugin, provisions it a venv (`uv sync --extra example` against
this repo — first run takes a few seconds), and it appears in the Hub sidebar under
**Examples**. Open **Mission Control**, poll go/no-go, recruit some crew, and launch a mission —
then watch the same job stream into the generic Queue & Progress panel.

No Hub handy? The whole surface also speaks curl:

```bash
curl http://localhost:5020/api/plugins/manifest/example
curl 'http://localhost:5020/api/plugins/example/compute?station=all'      # go/no-go
curl http://localhost:5020/api/plugins/example/crew                       # custom route
curl http://localhost:5020/api/plugins/example/crew/elvis                 # → 404
curl -o patch.png http://localhost:5020/api/plugins/example/patch.png     # binary route
curl -N -X POST http://localhost:5020/api/plugins/example/run \
  -H 'Content-Type: application/json' -d '{"destination": "Mars"}'        # streaming job
```

## What to read, in order

1. [`plugin.toml`](src/tlc_plugin_example/plugin.toml) — every manifest field, annotated.
2. [`__init__.py`](src/tlc_plugin_example/__init__.py) — `compute()`, `run_job(ctx)`, lifecycle hooks.
3. [`routes.py`](src/tlc_plugin_example/routes.py) — custom REST routes, one of every response shape.
4. [`patch.py`](src/tlc_plugin_example/patch.py) — a generated binary asset (stdlib-only PNG).
5. [`ui.html`](src/tlc_plugin_example/ui.html) — the full `PLUGIN_API` / `PluginJobs` tour.

## The dev loop

Code edits go live with a reload — no service restart:

```bash
# Reload everything under the plugin dir (re-provisions venvs when deps changed):
curl -X POST http://localhost:5020/api/admin/plugins/dirs/reload \
  -H 'Content-Type: application/json' \
  -d '{"directory": "/path/to/3lc-compute-plugin-example/src"}'
```

Lint like CI does (standalone — no deps to resolve):

```bash
uvx --from 'ruff>=0.15,<0.16' ruff check .
uvx --from 'ruff>=0.15,<0.16' ruff format .
```

To develop against a sibling SDK checkout, override its source **uncommitted**:

```toml
# pyproject.toml [tool.uv.sources]  (local dev only — do not commit)
3lc-compute-plugin-sdk = { path = "../3lc-plugin-sdk", editable = true }
```

### Editor autocomplete for `ui.html`

The fragment talks to the host through `window.PLUGIN_API` / `window.PluginJobs`, and both are
**typed**: the declaration ships inside the pip-installed SDK wheel, and the repo-root
[`jsconfig.json`](jsconfig.json) points TypeScript at it. Run `uv sync` once (creates `.venv/`)
and VS Code autocompletes the whole bridge inside `ui.html` — no node, no build step.

## Install from the catalog

This repo bakes its own shop listing: [`catalog.json`](catalog.json) — a static JSON file
with the plugin's versions, raw manifest (so the Hub can render a card and check compatibility
**without downloading anything**), and an install source pointing back at this repo. Add it to
a running service (persisted across restarts):

```bash
curl -X POST http://localhost:5020/api/admin/plugins/catalogs \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://raw.githubusercontent.com/3lc-ai/3lc-compute-plugin-example/main/catalog.json", "persist": true}'
```

…or paste that URL into the Hub's Plugins page. **Mission Control** shows up as an installable
card; installing materializes a managed venv from the git source and registers the plugin live.

## License

Apache-2.0 — see [LICENSE](LICENSE).
