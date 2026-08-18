# Copyright 2026 3LC Inc.
# SPDX-License-Identifier: Apache-2.0
"""Custom HTTP routes for Mission Control — one of every response shape.

A plugin's custom routes are **relative Litestar route handlers** returned by
``ComputePlugin.get_route_handlers()``. They mount under ``/api/plugins/example/``;
the plugin's own router does the matching, validation, body parsing, and content
typing — there is no hand-rolled dispatch. The worker serves them on a Unix socket
and the host reverse-proxies, but nothing here can tell.

Handlers are ``async`` because they only touch memory. If a handler does blocking
work (file/network/SDK/torch), declare it plain ``def`` with ``sync_to_thread=True``
so Litestar runs it in a threadpool, off the event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from litestar import Request, Response, get, post
from litestar.params import FromPath

from tlc_plugin_example.patch import mission_patch_png

if TYPE_CHECKING:
    from litestar.handlers import BaseRouteHandler

# In-memory crew roster so the routes show real request→response behaviour without a
# backing service. (A real plugin talks to tlc / a database / the filesystem here.)
_CREW: dict[str, dict[str, Any]] = {
    "ada": {"name": "ada", "role": "Commander", "callsign": "Countess"},
    "grace": {"name": "grace", "role": "Flight Engineer", "callsign": "Amazing"},
    "margaret": {"name": "margaret", "role": "Guidance Officer", "callsign": "Apollo"},
}


def get_route_handlers() -> list[BaseRouteHandler]:
    """Build the plugin's custom route handlers.

    Returns a **fresh** list each call: Litestar binds an owner to a handler when it
    is registered, so each app that mounts these needs its own instances.
    """

    @get("/crew")
    async def list_crew() -> list[dict[str, Any]]:
        """GET returning a JSON array (a REST collection)."""
        return list(_CREW.values())

    @get("/crew/{name:str}")
    async def get_crew_member(name: FromPath[str]) -> Response[dict[str, Any]]:
        """GET with a path parameter; a real 404 when absent (not a 200 with an error)."""
        member = _CREW.get(name.lower())
        if member is None:
            return Response({"error": f"{name!r} is not on this mission"}, status_code=404)
        return Response(member)

    # status_code=200: Litestar POSTs default to 201; pin 200 if your UI expects it.
    @post("/crew", status_code=200)
    async def add_crew_member(data: dict[str, Any]) -> dict[str, Any]:
        """POST with a parsed JSON body (``data``); echoes the stored member back."""
        name = str(data.get("name") or f"rookie-{len(_CREW)}").lower()
        _CREW[name] = {
            "name": name,
            "role": str(data.get("role", "Payload Specialist")),
            "callsign": str(data.get("callsign", "Rookie")),
        }
        return _CREW[name]

    @get("/patch.png")
    async def patch() -> Response[bytes]:
        """Binary response — the content type is preserved through the worker proxy.

        Listed in ``auth_exempt_paths`` in the manifest so an ``<img>`` (which can't
        send an Authorization header) can load it; validate a signed token in-handler
        if you serve anything private this way.
        """
        return Response(mission_patch_png(), media_type="image/png")

    @post("/cargo", status_code=200)
    async def load_cargo(request: Request[Any, Any, Any]) -> dict[str, Any]:
        """Raw request body — reaches the handler unparsed, with its content type."""
        raw = await request.body()
        return {
            "received_bytes": len(raw),
            "content_type": request.headers.get("content-type", ""),
            "verdict": "cargo secured" if raw else "cargo bay empty",
        }

    # sync_to_thread=True: this handler stats the filesystem, so it runs plain-def in a
    # threadpool instead of blocking the event loop (the rule from the module docstring).
    @post("/cargo-manifest", status_code=200, sync_to_thread=True)
    def inspect_cargo_manifest(data: dict[str, Any]) -> dict[str, Any]:
        """Inspect a file the user picked with the SDK's shared data-source widget.

        Every user-typed path goes through ``normalize_local_path`` at ingress: it
        strips whitespace, expands ``~``, and rejects relative paths (which would
        silently resolve against the plugin venv's CWD, not the user's).
        """
        from pathlib import Path as _Path

        from tlc_plugin_sdk.shared.url_utils import normalize_local_path

        try:
            manifest_path = normalize_local_path(str(data.get("path", "")))
        except ValueError as exc:
            return {"error": str(exc)}
        p = _Path(manifest_path)
        if not p.is_file():
            return {"error": f"No such file on the compute node: {manifest_path}"}
        return {
            "path": manifest_path,
            "size_bytes": p.stat().st_size,
            "verdict": "manifest accepted — cargo cleared for loading",
        }

    return [list_crew, get_crew_member, add_crew_member, patch, load_cargo, inspect_cargo_manifest]
