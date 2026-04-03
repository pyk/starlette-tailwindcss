# Starlette Tailwind CSS

`starlette-tailwindcss` is a lightweight utility for
[Starlette](https://starlette.dev/) that builds Tailwind CSS on startup with
optional watch mode during development.

It integrates directly with your Starlette app and provides:

- Builds CSS on startup.
- Automatically rebuilds on changes in watch mode.
- Optional `tailwindcss` CLI binary auto-installation.
- Fully typed, following Starlette patterns.

## Installation

```shell
uv add starlette-tailwindcss
# or
pip install starlette-tailwindcss
```

## Example

```python
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from starlette_tailwindcss import TailwindCSS

static_dir = Path(__file__).parent / "static"

tailwind = TailwindCSS(
    version="v4.2.2",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.css",
)

@asynccontextmanager
async def lifespan(app: Starlette):
    async with tailwind.build(watch=app.debug):
        yield

routes = [
    Mount("/static", app=StaticFiles(directory=static_dir), name="static"),
]

app = Starlette(
    debug=True,
    routes=routes,
    lifespan=lifespan,
)
```

Use the generated CSS file in your templates:

```html
<link rel="stylesheet" href="{{ url_for('static', path='css/output.css') }}" />
```

## How it works

`starlette-tailwindcss` runs the Tailwind CLI alongside your app.

- Builds CSS when the app starts.
- Rebuilds CSS in watch mode during development.
- Stops the process when the app shuts down.

## Usage

You can use an existing Tailwind CSS CLI binary:

```python
tailwind = TailwindCSS(
    bin_path="/usr/local/bin/tailwindcss",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.css",
)
```

Or let the package download a release automatically:

```python
tailwind = TailwindCSS(
    version="v4.2.2",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.css",
)
```

`bin_path` and `version` are mutually exclusive.

## Debug logging

To see Tailwind CSS CLI output:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

## License

MIT
