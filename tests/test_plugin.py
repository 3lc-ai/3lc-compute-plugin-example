# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: Apache-2.0
"""Mission Control's tests — no compute service, no Hub, no browser.

Three things the SDK gives a plugin author for free:

- ``tlc_plugin_sdk.harness.PluginHarness`` builds the same Litestar app the worker serves and
  calls it in-process, so every custom route, ``/compute`` and ``/ui`` is one call away;
- a ``JobContext`` with a recording sink drives ``run_job`` and lets a test assert the exact
  ``progress`` / ``metric`` / ``result`` events the Queue & Progress panel will see;
- ``tlc_plugin_sdk.lint.lint_plugin`` checks the fragment against the Hub's styling rules.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from tlc_plugin_sdk import JobContext, JobFailed
from tlc_plugin_sdk.harness import PluginHarness
from tlc_plugin_sdk.lint import lint_plugin

import tlc_plugin_example
from tlc_plugin_example import ExamplePlugin

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "src" / "tlc_plugin_example"


@pytest.fixture(scope="module")
def harness():
    """The plugin's app, loaded from its manifest the way a host would."""
    with PluginHarness.from_manifest(PLUGIN_DIR) as h:
        yield h


def test_compute_is_the_go_no_go_poll(harness: PluginHarness) -> None:
    answer = harness.get("/compute", params={"station": "all"}).json()
    assert answer["verdict"].startswith(("GO", "HOLD"))
    assert set(answer["checks"]) == {"guidance", "telemetry", "life-support", "snack-locker", "coffee-machine"}
    assert answer["received"] == {"station": "all"}


def test_crew_routes_answer_a_collection_a_member_and_a_real_404(harness: PluginHarness) -> None:
    assert harness.post("/crew", json_body={"name": "Sally", "role": "Pilot"}).json()["name"] == "sally"
    names = {member["name"] for member in harness.get("/crew").json()}
    assert {"ada", "grace", "margaret", "sally"} <= names
    missing = harness.get("/crew/elvis")
    assert missing.status_code == 404
    assert "elvis" in missing.json()["error"]


def test_the_mission_patch_is_a_png(harness: PluginHarness) -> None:
    patch = harness.get("/patch.png")
    assert patch.status_code == 200
    assert patch.headers["content-type"].startswith("image/png")
    assert patch.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_cargo_takes_a_raw_body(harness: PluginHarness) -> None:
    answer = harness.post("/cargo", content=b"\x2a" * 4, headers={"content-type": "application/octet-stream"})
    assert answer.json() == {
        "received_bytes": 4,
        "content_type": "application/octet-stream",
        "verdict": "cargo secured",
    }


def test_cargo_manifest_answers_the_hub_result_shape(harness: PluginHarness, tmp_path: Path) -> None:
    manifest = tmp_path / "cargo-manifest.txt"
    manifest.write_text("snacks: 42\n")
    accepted = harness.post("/cargo-manifest", json_body={"path": str(manifest)}).json()
    assert accepted["success"] is True
    assert accepted["details"] == {"path": str(manifest), "size_bytes": manifest.stat().st_size}
    refused = harness.post("/cargo-manifest", json_body={"path": str(tmp_path / "missing.txt")}).json()
    assert refused["success"] is False
    assert "No such file" in refused["message"]


def test_the_fragment_carries_the_shared_clients(harness: PluginHarness) -> None:
    ui = harness.get("/ui").text
    assert 'class="example-mc"' in ui
    assert "_tlcDataSourceHtml" in ui  # injected by get_ui_fragment()
    assert "window.PluginJobs" in ui  # auto-injected by the worker's /ui handler


def _context(
    params: dict[str, Any], tmp_path: Path, cancelled: bool = False
) -> tuple[JobContext, list[dict[str, Any]]]:
    """A JobContext whose events land in a list, as the host's would land on the stream."""
    events: list[dict[str, Any]] = []
    cancel = threading.Event()
    if cancelled:
        cancel.set()
    return JobContext("job-1", params, tmp_path, sink=events.append, cancel_event=cancel), events


def test_run_job_reports_through_the_generic_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tlc_plugin_example, "_TICK_SECONDS", 0)
    ctx, events = _context({"destination": "Mars", "stages": 1}, tmp_path)

    ExamplePlugin().run_job(ctx)

    kinds = [e["event"] for e in events]
    assert kinds.count("result") == 1
    assert next(e for e in events if e["event"] == "result")["run_url"] == "3lc://missions/mars"
    percents = [e["percent"] for e in events if e["event"] == "progress"]
    assert percents[0] == 0 and percents[-1] == 100.0
    assert {e["label"] for e in events if e["event"] == "metric"} == {"altitude_km", "velocity_km_s"}
    telemetry = [e for e in events if e["event"] == "custom"]
    assert telemetry and all(e["name"] == "telemetry" for e in telemetry)


def test_run_job_fails_cleanly_for_an_unknown_destination(tmp_path: Path) -> None:
    ctx, events = _context({"destination": "Sun"}, tmp_path)
    with pytest.raises(JobFailed, match="not on the flight manifest"):
        ExamplePlugin().run_job(ctx)
    assert not [e for e in events if e["event"] == "result"]


def test_a_cancelled_job_unwinds_without_a_result(tmp_path: Path) -> None:
    ctx, events = _context({"destination": "Luna"}, tmp_path, cancelled=True)
    ExamplePlugin().run_job(ctx)
    assert [e["event"] for e in events if e["event"] != "log"] == []
    assert any("halted" in e["message"] for e in events if e["event"] == "log")


def test_the_ui_follows_the_hub_styling_conventions() -> None:
    findings = lint_plugin(PLUGIN_DIR)
    assert not findings, "\n".join(map(str, findings))
