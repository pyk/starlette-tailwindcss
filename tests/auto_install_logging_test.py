"""Tests for Tailwind auto-install logging."""

from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace, TracebackType
from typing import TYPE_CHECKING, Self

import pytest
from starlette.testclient import TestClient

from starlette_tailwindcss import TailwindCSS, installer

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import StarletteAppFactory


class FakeResponse:
    """Small urllib response stub that supports streaming reads."""

    def __init__(self, data: bytes) -> None:
        """Store response bytes and expose a matching content length."""
        self._data = data
        self._offset = 0
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self) -> Self:
        """Return the response object for use in a `with` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave the context without suppressing errors."""

    def read(self, size: int = -1) -> bytes:
        """Return the next chunk of bytes from the fake response."""
        if self._offset >= len(self._data):
            return b""
        if size < 0 or size > len(self._data) - self._offset:
            size = len(self._data) - self._offset
        start = self._offset
        self._offset += size
        return self._data[start : self._offset]


def _expect_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        msg = f"Expected log line not found: {needle}"
        pytest.fail(msg)


def test_auto_install_uses_cached_binary(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    starlette_app_factory: StarletteAppFactory,
    tmp_path: Path,
) -> None:
    """Log the cached binary when the version is already installed."""
    version = "v4.2.2"
    target = SimpleNamespace(
        asset_name="tailwindcss-linux-x64",
        cache_name="tailwindcss-linux-x64",
        binary_name="tailwindcss-linux-x64",
    )
    binary_path = tmp_path / version / target.cache_name / target.binary_name
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_bytes(b"#!/bin/sh\n")

    def fake_target_platform() -> SimpleNamespace:
        return target

    def fail_urlopen(url: str) -> None:
        msg = f"network access is not expected: {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(installer, "_target_platform", fake_target_platform)
    monkeypatch.setattr(installer.urllib.request, "urlopen", fail_urlopen)
    caplog.set_level(logging.DEBUG, logger=installer.__name__)

    tailwind = TailwindCSS(
        version=version,
        cache_dir=tmp_path,
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
    )

    with TestClient(starlette_app_factory(tailwind, debug=True)):
        pass

    _expect_contains(
        caplog.text, f"Starting Tailwind CSS auto-install: version={version}"
    )
    _expect_contains(caplog.text, f"Using cached Tailwind CSS binary: {binary_path}")


def test_auto_install_logs_download_progress(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    starlette_app_factory: StarletteAppFactory,
    tmp_path: Path,
) -> None:
    """Log download progress in 25 percent increments for a fresh install."""
    version = "v4.2.2"
    target = SimpleNamespace(
        asset_name="tailwindcss-linux-x64",
        cache_name="tailwindcss-linux-x64",
        binary_name="tailwindcss-linux-x64",
    )
    asset_bytes = b"#!/bin/sh\nexit 0\n"
    checksum = hashlib.sha256(asset_bytes).hexdigest()
    manifest_bytes = (
        "ad627e77b496cccada4a6e26eafff698ef0829081e575a4baf3af8524bb00747  "
        "./tailwindcss-linux-arm64\n"
        "8e3836d35ba5ea5422d18b93ee8f0156e17947fa1810620aee1b849c1d7ad10e  "
        "./tailwindcss-linux-arm64-musl\n"
        f"{checksum}  ./tailwindcss-linux-x64\n"
        "0e473ea3650f95166e0bfd68348b835d0e06e253766d9a1f895377d1d9a7cf54  "
        "./tailwindcss-linux-x64-musl\n"
        "2ce66b7c8101ef1245a07d1e7abb4beb35bf512fd3beecba1cdfb327580d1252  "
        "./tailwindcss-macos-arm64\n"
        "98e34c6abd00a75a74ea2d20acf9e284241d13023133076d220c6f3ca419d920  "
        "./tailwindcss-macos-x64\n"
        "bf500d4be2109250d857a8ff161abdb995b6bf5e9262d279a95b74a887ca51d7  "
        "./tailwindcss-windows-x64.exe\n"
    ).encode()

    def fake_target_platform() -> SimpleNamespace:
        return target

    def fake_urlopen(url: str) -> FakeResponse:
        if url.endswith("sha256sums.txt"):
            return FakeResponse(manifest_bytes)
        if url.endswith(target.asset_name):
            return FakeResponse(asset_bytes)
        msg = f"unexpected url: {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(installer, "_target_platform", fake_target_platform)
    monkeypatch.setattr(installer.urllib.request, "urlopen", fake_urlopen)
    caplog.set_level(logging.DEBUG, logger=installer.__name__)

    tailwind = TailwindCSS(
        version=version,
        cache_dir=tmp_path,
        input=tmp_path / "input.css",
        output=tmp_path / "output.css",
    )

    with TestClient(starlette_app_factory(tailwind, debug=True)):
        pass

    binary_path = tmp_path / version / target.cache_name / target.binary_name
    assert binary_path.read_bytes() == asset_bytes
    _expect_contains(
        caplog.text, f"Starting Tailwind CSS auto-install: version={version}"
    )
    _expect_contains(caplog.text, f"Tailwind CSS binary cache miss: {binary_path}")
    _expect_contains(caplog.text, "Installing Tailwind CSS binary: 0%")
    _expect_contains(caplog.text, "Installing Tailwind CSS binary: 25%")
    _expect_contains(caplog.text, "Installing Tailwind CSS binary: 50%")
    _expect_contains(caplog.text, "Installing Tailwind CSS binary: 75%")
    _expect_contains(caplog.text, "Installing Tailwind CSS binary: 100%")
    _expect_contains(caplog.text, f"Finished Tailwind CSS auto-install: {binary_path}")
