"""Command-line launcher for the local e2n web UI."""

from __future__ import annotations

import argparse
import os
import threading
import time
import webbrowser

import uvicorn

from e2n.webui.app import create_app


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for launching the local web server."""
    parser = argparse.ArgumentParser(prog="e2n-ui", description="Run the local e2n web interface")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address for the local web server")
    parser.add_argument("--port", type=int, default=8787, help="Port for the local web server")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for local development")
    parser.add_argument("--open", action="store_true", help="Open the browser automatically after startup")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the local web server."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.open:
        _open_browser_later(args.host, args.port)

    uvicorn.run(
        "e2n.webui.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level=os.environ.get("E2N_UI_LOG_LEVEL", "info"),
    )
    return 0


def _open_browser_later(host: str, port: int) -> None:
    """Open default browser shortly after server startup begins."""

    def _open() -> None:
        time.sleep(0.8)
        webbrowser.open(f"http://{host}:{port}")

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


if __name__ == "__main__":
    raise SystemExit(main())
