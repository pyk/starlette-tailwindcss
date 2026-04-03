"""Integration test for a failed Tailwind auto-install."""

from contextlib import asynccontextmanager
from email.message import Message
from typing import TYPE_CHECKING
from urllib.error import HTTPError

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from starlette_tailwindcss import TailwindCSS, installer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


def test_auto_install_checksum_manifest_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Raise `RuntimeError` when the release checksum manifest cannot be fetched."""

    def raise_http_404(url: str) -> bytes:
        raise HTTPError(url, 404, "Not Found", hdrs=Message(), fp=None)

    def fail_user_cache_dir(_app_name: str) -> str:
        msg = "user_cache_dir should not be called"
        raise AssertionError(msg)

    monkeypatch.setattr(installer, "_read_url", raise_http_404)
    monkeypatch.setattr(installer, "user_cache_dir", fail_user_cache_dir)

    tailwind = TailwindCSS(
        version="random-version",
        cache_dir=tmp_path,
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with tailwind.build(watch=app.debug):
            yield

    app = Starlette(debug=True, lifespan=lifespan)
    expected_error = (
        "Failed to download Tailwind CSS checksum manifest for random-version"
    )

    with (
        pytest.raises(
            RuntimeError,
            match=expected_error,
        ),
        TestClient(app),
    ):
        pass
