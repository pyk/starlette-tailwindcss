"""Integration test for Tailwind shutdown when composed with hot reload."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _write_fake_tailwind_binary(path: Path) -> None:
    """Create a tiny CLI shim that builds once and then idles in watch mode."""
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import pathlib
            import signal
            import sys
            import time


            def main() -> int:
                args = sys.argv[1:]
                output = pathlib.Path(args[args.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("/* fake tailwind */\\n", encoding="utf-8")
                if "--watch" not in args:
                    return 0

                signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
                while True:
                    time.sleep(0.1)


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_server_script(
    path: Path,
    bin_path: Path,
    static_dir: Path,
    styles: Path,
) -> None:
    """Create a small Uvicorn server that composes hot reload with Tailwind."""
    path.write_text(
        textwrap.dedent(
            f"""\
            from __future__ import annotations

            import logging
            import sys
            from contextlib import AsyncExitStack, asynccontextmanager
            from pathlib import Path
            from typing import TYPE_CHECKING

            import uvicorn
            from starlette.applications import Starlette
            from starlette.responses import HTMLResponse
            from starlette.routing import Route
            from starlette_tailwindcss import tailwind
            from starlette_hot_reload import hot_reload

            if TYPE_CHECKING:
                from collections.abc import AsyncIterator
                from starlette.requests import Request

            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                stream=sys.stderr,
            )

            example_dir = Path({str(path.parent)!r})
            static_dir = Path({str(static_dir)!r})
            styles = Path({str(styles)!r})
            bin_path = Path({str(bin_path)!r})


            async def homepage(_request: Request) -> HTMLResponse:
                return HTMLResponse("<!doctype html><title>ok</title>")


            @asynccontextmanager
            async def lifespan(app: Starlette) -> AsyncIterator[None]:
                async with AsyncExitStack() as stack:
                    await stack.enter_async_context(
                        hot_reload(app=app, watch_dirs=[example_dir]),
                    )
                    await stack.enter_async_context(
                        tailwind(
                            watch=app.debug,
                            bin_path=bin_path,
                            input=styles,
                            output=static_dir / "css" / "output.css",
                        ),
                    )
                    yield


            app = Starlette(
                debug=True,
                routes=[Route("/", homepage)],
                lifespan=lifespan,
            )


            if __name__ == "__main__":
                uvicorn.run(
                    app,
                    host="127.0.0.1",
                    port=int(sys.argv[1]),
                    log_config=None,
                )
            """
        ),
        encoding="utf-8",
    )


def test_tailwind_shutdown_runs_with_hot_reload(tmp_path: Path) -> None:
    """Tailwind should stop its watch process when composed with hot reload."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    fake_bin = tmp_path / "tailwindcss"
    static_dir = tmp_path / "static"
    styles = tmp_path / "globals.css"
    server = tmp_path / "server.py"

    static_dir.joinpath("css").mkdir(parents=True, exist_ok=True)
    styles.write_text('@import "tailwindcss";\n', encoding="utf-8")
    _write_fake_tailwind_binary(fake_bin)
    _write_server_script(server, fake_bin, static_dir, styles)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "src"),
            str(ROOT / "external" / "pyk" / "starlette-hot-reload" / "src"),
        ],
    )

    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, str(server), str(port)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + 10.0
        url = f"http://127.0.0.1:{port}/"
        with httpx.Client(timeout=1.0) as client:
            while True:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    break
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.RemoteProtocolError,
                ):
                    if time.monotonic() >= deadline:
                        msg = "server did not start within 10 seconds"
                        raise TimeoutError(msg) from None
                    time.sleep(0.1)

        proc.send_signal(signal.SIGINT)
        output, _ = proc.communicate(timeout=10)

        if "stop watch pid=" not in output:
            msg = f"missing Tailwind shutdown log:\n{output}"
            raise AssertionError(msg)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
