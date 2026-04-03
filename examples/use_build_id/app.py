"""Example that uses a build id for Tailwind output."""

from __future__ import annotations

import logging
import secrets
import string
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from starlette_tailwindcss import TailwindCSS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request
    from starlette.responses import HTMLResponse

_BUILD_ID_LENGTH = 8
_BUILD_ID_ALPHABET = string.ascii_letters


def generate_build_id(length: int = _BUILD_ID_LENGTH) -> str:
    """Generate a short random identifier for cache-busting CSS filenames."""
    return "".join(secrets.choice(_BUILD_ID_ALPHABET) for _ in range(length))


# Enable debug logging to stderr
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)

templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"
styles = Path(__file__).parent / "globals.css"

templates = Jinja2Templates(directory=templates_dir)


async def homepage(request: Request) -> HTMLResponse:
    """Homepage handler."""
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "css_href": request.url_for(
                "static",
                path=f"css/output.{request.app.state.build_id}.css",
            ),
            "css_path": f"/static/css/output.{request.app.state.build_id}.css",
        },
    )


routes = [
    Mount(
        "/static",
        app=StaticFiles(directory=static_dir),
        name="static",
    ),
    Route("/", homepage),
]


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    """Run Tailwind alongside the Starlette app lifespan."""
    app.state.build_id = generate_build_id()
    tailwind = TailwindCSS(
        version="v4.2.2",
        input=styles,
        output=static_dir / "css" / f"output.{app.state.build_id}.css",
    )
    async with tailwind.build(watch=app.debug):
        yield


app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_config=None)  # noqa: S104
