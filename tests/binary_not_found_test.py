"""Integration test for a missing Tailwind binary path."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from starlette_tailwindcss import TailwindCSS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


def test_binary_path_not_found(tmp_path: Path) -> None:
    """Raise `FileNotFoundError` when the configured binary path is invalid."""
    tailwind = TailwindCSS(
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
        bin_path="/usr/local/bin/tailwindcss-random",
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with tailwind.build(watch=app.debug):
            yield

    app = Starlette(debug=True, lifespan=lifespan)

    with (
        pytest.raises(
            FileNotFoundError,
            match="Tailwind CSS binary not found",
        ),
        TestClient(app),
    ):
        pass
