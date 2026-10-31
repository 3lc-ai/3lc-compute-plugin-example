# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: Apache-2.0
"""Mission Control — the example plugin: every contract surface, staged as a rocket launch.

Where the plugin template (``3lc-compute-plugin-template``) is the skeleton you instantiate,
this one is the tour you take. It exercises the whole ``ComputePlugin`` contract with a
working (if slightly silly) implementation:

- ``compute(params)`` — the go/no-go systems poll (``GET /api/plugins/example/compute``);
- ``run_job(ctx)`` — the launch sequence: countdown, staged burns, live ``progress`` /
  ``metric`` / ``log`` into the generic Queue & Progress panel, plugin-private
  ``ctx.emit("telemetry", …)`` events for this plugin's own UI, a clean user-facing failure
  via ``ctx.fail()``, and a cooperative abort via ``ctx.cancelled``;
- ``get_route_handlers()`` — custom REST routes (crew manifest CRUD, a generated
  mission-patch PNG, a raw-bytes cargo upload, a cargo-manifest inspection fed by the
  SDK's shared data-source picker) — see ``routes.py``;
- ``get_ui_fragment()`` — a fragment that drives all of the above through
  ``window.PLUGIN_API`` and ``window.PluginJobs``;
- ``initialise_runtime`` / ``shutdown_runtime`` — the optional lifecycle hooks.

``ComputePlugin`` is the base for anything that runs jobs. Its parent ``HubPlugin`` (UI
fragment, ``compute``, routes, shutdown) is for a plugin with no jobs at all, and
``InfrastructurePlugin`` is for a provider that creates nodes; all three come from
``tlc_plugin_sdk``.

The host reads this plugin's metadata from ``plugin.toml`` without importing it, then
launches it in a worker subprocess inside its own provisioned venv and reverse-proxies
``/api/plugins/example/…`` to it. Nothing in this package knows or cares that it runs
out-of-process — the tests in ``tests/`` run the very same app in-process through
``tlc_plugin_sdk.harness``.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tlc_plugin_sdk import ComputePlugin

from tlc_plugin_example import routes as _routes

if TYPE_CHECKING:
    from tlc_plugin_sdk.job_context import JobContext

logger = logging.getLogger(__name__)

_UI = Path(__file__).resolve().parent / "ui.html"

_SYSTEMS = ("guidance", "telemetry", "life-support", "snack-locker", "coffee-machine")
_DESTINATIONS = ("Luna", "Mars", "Europa", "Titan")
_TICKS_PER_STAGE = 5
_TICK_SECONDS = 0.4


class ExamplePlugin(ComputePlugin):
    """Behavior only — metadata comes from ``plugin.toml``."""

    # Display identity stamped onto the instance by the host from the manifest.
    id: str
    name: str
    icon: str

    def initialise_runtime(self) -> None:
        """Optional: set up runtime resources once (models, stores). Runs in the worker."""
        logger.info("mission control online: all consoles manned")

    def shutdown_runtime(self) -> None:
        """Optional: tear down runtime resources. Must be safe if never initialised."""
        logger.info("mission control: lights out")

    def get_ui_fragment(self) -> str:
        """Serve the fragment at ``GET /api/plugins/example/ui``.

        ``inject_scripts`` splices an SDK client script into the fragment right after its
        first ``<script>``: here the data-source picker (``_tlcDataSourceHtml`` /
        ``_tlcBindDataSource`` / ``_tlcGetDataSourceValue``) for choosing files and folders
        the run target can read. The job-tracker client (``window.PluginJobs``) needs no
        injection: the worker's ``/ui`` handler adds it to every fragment.
        """
        from tlc_plugin_sdk.shared.data_source_ui import data_source_ui_script
        from tlc_plugin_sdk.shared.ui_inject import inject_scripts

        return inject_scripts(_UI.read_text(encoding="utf-8"), data_source_ui_script())

    def compute(self, params: dict[str, Any]) -> dict[str, Any]:
        """The go/no-go poll — synchronous request/response at ``GET …/compute``.

        Seeded by the query params, so re-polling with the same params is deterministic
        and changing them re-rolls the board. (Your real plugin does real work here.)
        """
        rng = random.Random(repr(sorted(params.items())))
        checks = dict.fromkeys(_SYSTEMS, "go")
        holdout = rng.choice(_SYSTEMS)
        if rng.random() < 0.3:
            checks[holdout] = "no-go (still brewing)" if holdout == "coffee-machine" else "hold"
        all_go = all(v == "go" for v in checks.values())
        return {
            "verdict": "GO for launch" if all_go else f"HOLD — {holdout} is not ready",
            "checks": checks,
            "received": params,
        }

    def get_route_handlers(self) -> list[Any]:
        """Custom REST routes, served under ``/api/plugins/example/`` — see ``routes.py``.

        The SDK's shared data-source routes (``/browse`` + ``/upload-temp``) ride along:
        they are what the data-source picker in the fragment talks to. ``/browse`` lists
        only the folders the host's operator offers (``TLC_DATA_SOURCE_ROOTS``).
        """
        from tlc_plugin_sdk.shared.data_source_routes import data_source_route_handlers

        return [*_routes.get_route_handlers(), *data_source_route_handlers()]

    def run_job(self, ctx: JobContext) -> None:
        """The launch sequence — a long job at ``POST …/run`` (fire-and-return).

        Everything goes through ``ctx``: ``progress``/``metric``/``log``/``result`` feed
        the generic Queue & Progress panel (the frontend renders them with zero knowledge
        of this plugin); ``emit`` sends plugin-private telemetry that only this plugin's
        own ``ui.html`` listens for. Cancellation is cooperative — poll ``ctx.cancelled``
        at every checkpoint and unwind cleanly. Bad input is ``ctx.fail(message)``: the
        job card shows the sentence as it is, with no ``TypeError:``-style prefix.
        """
        destination = str(ctx.params.get("destination", "Luna"))
        if destination not in _DESTINATIONS:
            ctx.fail(f"{destination!r} is not on the flight manifest — pick one of {', '.join(_DESTINATIONS)}")
        stages = max(1, min(int(ctx.params.get("stages", 3)), 5))
        rng = random.Random(destination)

        # What the host stamped on the job: the project root a plugin that creates tables or runs
        # passes to the core library as ``root_url``, and who the job runs for (every field None
        # on a keyless local host). Mission Control creates nothing, so it only logs them.
        flight_plan = ctx.project_root_url or "(this worker's default root)"
        crew = ctx.identity.user_id or "anonymous"
        ctx.log(f"mission to {destination}: pre-flight complete, {stages}-stage vehicle on the pad")
        ctx.log(f"flight plan filed under {flight_plan} for {crew}")
        for t in (3, 2, 1):
            if ctx.cancelled:
                ctx.log("countdown halted — crew back to the ready room")
                return
            ctx.progress(percent=0, label=f"T-minus {t}")
            time.sleep(_TICK_SECONDS)
        ctx.log("liftoff! we have liftoff")

        total_ticks = stages * _TICKS_PER_STAGE
        altitude_km = 0.0
        velocity_kms = 0.0
        for tick in range(1, total_ticks + 1):
            if ctx.cancelled:
                ctx.log(f"ABORT at {altitude_km:.0f} km — engines safed, capsule descending on chutes")
                return
            time.sleep(_TICK_SECONDS)
            stage = (tick - 1) // _TICKS_PER_STAGE + 1
            velocity_kms += rng.uniform(0.4, 0.9) * stage
            altitude_km += velocity_kms * 8
            ctx.progress(percent=100.0 * tick / total_ticks, label=f"stage {stage}/{stages} burn")
            ctx.metric("altitude_km", round(altitude_km))
            ctx.metric("velocity_km_s", round(velocity_kms, 1))
            # Plugin-private event for this plugin's own UI (the generic panel ignores it).
            ctx.emit("telemetry", {"stage": stage, "altitude_km": altitude_km, "velocity_kms": velocity_kms})
            if tick % _TICKS_PER_STAGE == 0 and stage < stages:
                ctx.log(f"stage {stage} separation confirmed")

        # The canonical artifact link — a real plugin points this at the run or table it made
        # (written under ctx.project_root_url), and the Queue's Open button opens it.
        ctx.result(f"3lc://missions/{destination.lower()}")
        ctx.log(f"{destination} orbit achieved — mission complete, splashdown when ready")
