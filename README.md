<h3 align="center">starlette-tailwindcss</h3>

<p align="center">
  Tailwind CSS for Starlette
<p>

<p align="center">
<a href="https://pypi.org/project/starlette-tailwindcss/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/starlette-tailwindcss?style=flat&labelColor=%23000000&color=%23000000"></a> <a href="https://pypi.org/project/starlette-tailwindcss/"><img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/starlette-tailwindcss?style=flat&labelColor=000000&color=000000"></a> <a href="https://pypi.org/project/starlette-tailwindcss/"><img alt="PyPI - License" src="https://img.shields.io/pypi/l/starlette-tailwindcss?labelColor=000&color=000"></a>
</p>

### Overview

`starlette-tailwindcss` is a lightweight utility for
[Starlette](https://starlette.dev/) that builds Tailwind CSS on startup with
optional watch mode during development.

It integrates directly with your Starlette app and provides:

- Builds CSS on startup.
- Automatically rebuilds on changes in watch mode.
- Optional `tailwindcss` CLI binary auto-installation.

### Installation

```shell
uv add starlette-tailwindcss
# or
pip install starlette-tailwindcss
```

### Example

```python
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from starlette_tailwindcss import tailwind

static_dir = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: Starlette):
    async with tailwind(
        watch=app.debug,
        version="v4.2.2",
        input="src/acme/web/style.css",
        output=static_dir / "css" / "output.{build_id}.css",
    ) as assets:
        app.state.tailwind = assets
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
<link
    rel="stylesheet"
    href="{{ url_for('static', path='css/' ~ request.app.state.tailwind.file_name) }}"
/>
```

### How it works

`starlette-tailwindcss` runs the Tailwind CLI alongside your app.

- Builds CSS when the app starts.
- Rebuilds CSS in watch mode during development.
- Stops the process when the app shuts down.

### Usage

Use an existing Tailwind CSS CLI binary:

```python
async with tailwind(
    watch=app.debug,
    bin_path="/usr/local/bin/tailwindcss",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.css",
):
    ...
```

Or let the package download a release automatically:

```python
async with tailwind(
    watch=app.debug,
    version="v4.2.2",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.css",
):
    ...
```

`bin_path` and `version` are mutually exclusive.

For a one-time build step, use `build(...)` instead of `tailwind(...)`:

```python
import asyncio
from pathlib import Path

from starlette_tailwindcss import build

static_dir = Path(__file__).parent / "static"

assets = asyncio.run(
    build(
        version="v4.2.2",
        input="src/acme/web/style.css",
        output=static_dir / "css" / "output.css",
    ),
)
```

If `output` includes `{build_id}`, the startup build writes a unique file name
on each app start. That makes cache pruning straightforward in production:

```python
async with tailwind(
    watch=app.debug,
    version="v4.2.2",
    input="src/acme/web/style.css",
    output=static_dir / "css" / "output.{build_id}.css",
):
    ...
```

### Debug logging

To see Tailwind CSS CLI output:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

### License

MIT
