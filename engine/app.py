"""computah-engine: executes device commands.

Each command is a self-contained module in the ``commands`` package, registered
by name (e.g. "turn-on-led") and reached at its own path (POST
/commands/turn-on-led). New commands are added modularly — drop a new file in
``commands/`` and it's available automatically; no changes here.

The speech-to-command parsing happens upstream (either the moonshine container, or multimodal llm),
which decides *which* command to call. This engine just executes a named
command. Matching is exact (no LLM) — fast, but the caller must use the exact
command name.

Endpoints:
    POST /commands/<name>   Run command <name>; JSON body is passed as params.
    GET  /commands          List available command names.
    GET  /health            -> {"status": "ok"}
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from commands import COMMANDS, load_commands

PORT = int(os.environ.get("PORT", "9000"))
# Base path under which commands are exposed: /commands/<name>.
COMMANDS_PREFIX = os.environ.get("COMMANDS_PREFIX", "/commands").rstrip("/")


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return self.path.split("?", 1)[0].rstrip("/")

    def do_GET(self) -> None:
        path = self._path()
        if path in ("", "/health"):
            self._reply(200, {"status": "ok"})
        elif path == COMMANDS_PREFIX:
            self._reply(200, {"commands": sorted(COMMANDS)})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self._path()
        if not path.startswith(COMMANDS_PREFIX + "/"):
            self._reply(404, {"error": "not found", "commands": sorted(COMMANDS)})
            return

        name = path[len(COMMANDS_PREFIX) + 1:]
        handler = COMMANDS.get(name)
        if handler is None:
            self._reply(
                404,
                {"error": f"unknown command: {name!r}", "commands": sorted(COMMANDS)},
            )
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            params = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._reply(400, {"error": "invalid json"})
            return

        try:
            result = handler(params)
        except Exception as exc:  # noqa: BLE001 - report handler failures cleanly
            self._reply(500, {"command": name, "status": "error", "error": str(exc)})
            return

        self._reply(200, result if isinstance(result, dict) else {"status": "ok"})

    def log_message(self, *args) -> None:
        # Silence the default per-request access log; commands print their own.
        pass


def main() -> None:
    commands = load_commands()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(
        f"computah-engine listening on :{PORT} "
        f"(POST {COMMANDS_PREFIX}/<name>) — commands: {sorted(commands) or 'none'}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
