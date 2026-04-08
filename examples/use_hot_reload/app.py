"""Example Starlette application with hot reload and Tailwind CSS."""

from __future__ import annotations

import logging
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette_hot_reload import hot_reload

from starlette_tailwindcss import tailwind

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

example_dir = Path(__file__).parent
templates_dir = example_dir / "templates"
static_dir = example_dir / "static"
styles = example_dir / "globals.css"

templates = Jinja2Templates(directory=templates_dir)


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
    """Run hot reload and Tailwind alongside the Starlette app lifespan."""
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(
            hot_reload(app=app, watch_dirs=[example_dir]),
        )
        assets = await stack.enter_async_context(
            tailwind(
                watch=app.debug,
                version="v4.2.2",
                input=styles,
                output=static_dir / "css" / "output.{build_id}.css",
            ),
        )
        app.state.tailwind = assets
        yield


app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_config=None)  # noqa: S104
