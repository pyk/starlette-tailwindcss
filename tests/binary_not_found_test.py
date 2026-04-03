"""Integration test for a missing Tailwind binary path."""

from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from starlette_tailwindcss import TailwindCSS

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import StarletteAppFactory


def test_binary_path_not_found(
    starlette_app_factory: StarletteAppFactory,
    tmp_path: Path,
) -> None:
    """Raise `FileNotFoundError` when the configured binary path is invalid."""
    tailwind = TailwindCSS(
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
        bin_path="/usr/local/bin/tailwindcss-random",
    )

    with (
        pytest.raises(
            FileNotFoundError,
            match="Tailwind CSS binary not found",
        ),
        TestClient(starlette_app_factory(tailwind, debug=True)),
    ):
        pass
