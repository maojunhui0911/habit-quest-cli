"""Local web server for the Habit Quest dungeon dashboard.

The server shares the very same JSON save file as the CLI, so quests claimed
in the browser show up in the terminal and vice versa.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import habit_quest as hq

WEB_ROOT = Path(__file__).resolve().parent / "web"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; font-src 'self'; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
    ),
}


class QuestRequestHandler(BaseHTTPRequestHandler):
    """Tiny JSON API plus the static dashboard files."""

    state_path: Path = hq.default_state_file()
    state_lock = threading.Lock()
    server_version = "HabitQuest/2.0"
    protocol_version = "HTTP/1.1"
    verbose = False

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if self.verbose:
            super().log_message(fmt, *args)

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, message: str, status: int) -> None:
        self._json({"ok": False, "error": message}, status=status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > 1_000_000:
            raise ValueError("Request body is too large.")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _text_field(self, payload: dict, name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise ValueError(f"'{name}' must be a string.")
        return value

    # -- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json({"ok": True, "version": hq.STATE_VERSION})
            return
        if path == "/api/state":
            with self.state_lock:
                state = hq.load_state(self.state_path)
                payload = self._dashboard(hq.build_dashboard(state))
            self._json(payload)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            payload = self._read_json()
        except ValueError as error:
            self._error(str(error), HTTPStatus.BAD_REQUEST)
            return

        try:
            if path == "/api/complete":
                result = self._complete(payload)
                self._json({"ok": True, "result": result})
            elif path == "/api/add":
                dashboard = self._add(payload)
                self._json({"ok": True, "dashboard": dashboard})
            elif path == "/api/remove":
                dashboard = self._remove(payload)
                self._json({"ok": True, "dashboard": dashboard})
            elif path == "/api/undo":
                entry, dashboard = self._undo()
                self._json({"ok": True, "undone": entry, "dashboard": dashboard})
            elif path == "/api/rename":
                dashboard = self._rename(payload)
                self._json({"ok": True, "dashboard": dashboard})
            elif path == "/api/demo":
                dashboard = self._demo()
                self._json({"ok": True, "dashboard": dashboard})
            else:
                self._error("Unknown API route.", HTTPStatus.NOT_FOUND)
        except KeyError as error:
            self._error(error.args[0] if error.args else "Not found.", HTTPStatus.NOT_FOUND)
        except hq.AlreadyDoneToday as error:
            self._error(str(error), HTTPStatus.CONFLICT)
        except ValueError as error:
            self._error(str(error), HTTPStatus.BAD_REQUEST)
        except Exception:  # pragma: no cover - defensive, surfaced in the terminal
            import traceback

            traceback.print_exc()
            self._error("The dungeon gate failed unexpectedly.", HTTPStatus.INTERNAL_SERVER_ERROR)

    # -- mutations --------------------------------------------------------

    def _mutate(self, action):
        """Load, mutate and save inside the state lock, then return payload."""

        with self.state_lock:
            state = hq.load_state(self.state_path)
            result = action(state)
            hq.save_state(state, self.state_path)
            dashboard = hq.build_dashboard(state)
        return result, dashboard

    def _complete(self, payload: dict) -> dict:
        name = self._text_field(payload, "habit")

        def action(state: dict):
            return hq.complete_habit(state, name)

        result, dashboard = self._mutate(action)
        response = result.to_dict()
        response["dashboard"] = self._dashboard(dashboard)
        return response

    def _add(self, payload: dict) -> dict:
        name = self._text_field(payload, "name")
        try:
            xp = int(payload.get("xp", 20))
        except (TypeError, ValueError) as error:
            raise ValueError("'xp' must be a number.") from error

        def action(state: dict):
            hq.add_habit(state, name, xp)

        return self._dashboard(self._mutate(action)[1])

    def _remove(self, payload: dict) -> dict:
        name = self._text_field(payload, "habit")
        return self._dashboard(
            self._mutate(lambda state: hq.remove_habit(state, name))[1]
        )

    def _undo(self) -> tuple[dict, dict]:
        entry, dashboard = self._mutate(hq.undo_last)
        return (
            {
                "habit": entry.get("habit"),
                "date": entry.get("date"),
                "xp": entry.get("xp", 0),
            },
            self._dashboard(dashboard),
        )

    def _rename(self, payload: dict) -> dict:
        name = self._text_field(payload, "name")
        return self._dashboard(
            self._mutate(lambda state: hq.rename_hero(state, name))[1]
        )

    def _demo(self) -> dict:
        def action(state: dict):
            if state["habits"]:
                raise ValueError("This adventure already has quests.")
            hq.seed_demo(state)

        return self._dashboard(self._mutate(action)[1])

    def _dashboard(self, payload: dict) -> dict:
        payload["state_path"] = str(self.state_path)
        return payload

    # -- static files -----------------------------------------------------

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()
        if target != WEB_ROOT and WEB_ROOT not in target.parents:
            self._error("Not found.", HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._error("Not found.", HTTPStatus.NOT_FOUND)
            return
        try:
            body = target.read_bytes()
        except OSError:
            self._error("Not found.", HTTPStatus.NOT_FOUND)
            return
        content_type = MIME_TYPES.get(
            target.suffix.lower(), "application/octet-stream"
        )
        self._headers(HTTPStatus.OK, content_type, len(body))
        self.wfile.write(body)


def create_server(
    state_path: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> ThreadingHTTPServer:
    """Create (but do not start) a configured dashboard server."""

    path = Path(state_path).expanduser() if state_path else hq.default_state_file()
    handler = type(
        "BoundQuestRequestHandler",
        (QuestRequestHandler,),
        {"state_path": path, "state_lock": threading.Lock()},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def run_server(
    state_path: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
) -> None:
    path = Path(state_path).expanduser() if state_path else hq.default_state_file()
    server = create_server(path, host=host, port=port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"
    print("Habit Quest - web dungeon")
    print(f"  Dashboard: {url}")
    print(f"  Save file: {path}")
    print("  Press Ctrl+C to close the gate.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nThe dungeon gate closes. Your progress is saved.")
    finally:
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the Habit Quest dashboard.")
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true")
    cli_args = parser.parse_args()
    run_server(cli_args.state, cli_args.host, cli_args.port, cli_args.open)
