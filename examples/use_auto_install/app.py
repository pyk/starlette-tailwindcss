"""Example that uses a auto install tailwindcss CLI."""

from __future__ import annotations

import logging
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
tailwind = TailwindCSS(
    version="random-version",
    input=styles,
    output=static_dir / "css" / "output.css",
)


async def homepage(request: Request) -> HTMLResponse:
    """Homepage handler."""
    return templates.TemplateResponse(request, "index.html")


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
    async with tailwind.build(watch=app.debug):
        yield


app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_config=None)  # noqa: S104
