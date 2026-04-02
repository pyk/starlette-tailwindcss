"""Integration test for a missing Tailwind binary path."""

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from starlette_tailwindcss import TailwindCSS

if TYPE_CHECKING:
    from pathlib import Path


def test_binary_path_not_found(tmp_path: Path) -> None:
    """Raise `FileNotFoundError` when the configured binary path is invalid."""
    app = Starlette(debug=True)
    tailwind = TailwindCSS(
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
        bin_path="/usr/local/bin/tailwindcss-random",
    )
    tailwind.setup(app)

    with (
        pytest.raises(
            FileNotFoundError,
            match="Tailwind CSS binary not found",
        ),
        TestClient(app),
    ):
        pass
