"""Tailwind CSS binary installation helpers."""

from __future__ import annotations

import hashlib
import logging
import platform
import stat
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_cache_dir

if TYPE_CHECKING:
    from os import PathLike

logger = logging.getLogger(__name__)

_APP_NAME = "starlette-tailwindcss"
_RELEASE_BASE_URL = "https://github.com/tailwindlabs/tailwindcss/releases/download"
_PROGRESS_MAX = 100


@dataclass(frozen=True, slots=True)
class _Target:
    """Resolved binary names for the current platform."""

    asset_name: str
    cache_name: str
    binary_name: str


def _normalize_machine(machine: str) -> str:
    """Normalize platform machine names to Tailwind release names."""
    value = machine.lower()
    if value in {"x86_64", "amd64"}:
        return "x64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    msg = f"Unsupported machine architecture: {machine}"
    raise RuntimeError(msg)


def _is_musl() -> bool:
    """Return `True` when the current Linux libc is musl."""
    libc_name, _ = platform.libc_ver()
    return libc_name.lower() == "musl"


def _target_platform() -> _Target:
    """Build the Tailwind release target for the current platform."""
    system = platform.system().lower()
    arch = _normalize_machine(platform.machine())

    if system == "linux":
        suffix = "-musl" if _is_musl() else ""
        asset_name = f"tailwindcss-linux-{arch}{suffix}"
        return _Target(
            asset_name=asset_name,
            cache_name=asset_name,
            binary_name=asset_name,
        )
    if system == "darwin":
        asset_name = f"tailwindcss-macos-{arch}"
        return _Target(
            asset_name=asset_name,
            cache_name=f"macos-{arch}",
            binary_name=asset_name,
        )
    if system == "windows":
        asset_name = "tailwindcss-windows-x64.exe"
        return _Target(
            asset_name=asset_name,
            cache_name="windows-x64",
            binary_name=asset_name,
        )

    msg = f"Unsupported operating system: {platform.system()}"
    raise RuntimeError(msg)


def _sha256(path: Path) -> str:
    """Calculate a SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_url(url: str) -> bytes:
    """Read the full contents of a URL."""
    with urllib.request.urlopen(url) as response:  # noqa: S310
        return response.read()


def _download_to_path(url: str, path: Path) -> None:
    """Download a URL into a file path atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        urllib.request.urlopen(url) as response,  # noqa: S310
        tempfile.NamedTemporaryFile(
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as file,
    ):
        total_bytes_raw = response.headers.get("Content-Length")
        total_bytes = int(total_bytes_raw) if total_bytes_raw is not None else None
        downloaded = 0
        next_progress = 25
        if total_bytes is not None:
            logger.debug("Installing Tailwind CSS binary: 0%%")
        while chunk := response.read(1024 * 1024):
            file.write(chunk)
            if total_bytes is None:
                continue
            downloaded += len(chunk)
            percent = (downloaded * _PROGRESS_MAX) // total_bytes
            while next_progress <= _PROGRESS_MAX and percent >= next_progress:
                logger.debug(
                    "Installing Tailwind CSS binary: %s%%",
                    next_progress,
                )
                next_progress += 25
        temp_path = Path(file.name)
    temp_path.replace(path)


def _parse_checksum_manifest(content: str) -> dict[str, str]:
    """Parse Tailwind's checksum manifest into a mapping."""
    checksums: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        checksum, asset_name = line.split(maxsplit=1)
        checksums[asset_name.removeprefix("./")] = checksum
    return checksums


def _ensure_executable(path: Path) -> None:
    """Mark a file executable for the current user."""
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(
    version: str,
    cache_dir: str | PathLike[str] | None = None,
) -> Path:
    """Download, verify, and cache the Tailwind binary for a release version."""
    logger.debug("Starting Tailwind CSS auto-install: version=%s", version)
    target = _target_platform()
    cache_root = (
        Path(user_cache_dir(_APP_NAME))
        if cache_dir is None
        else Path(cache_dir).expanduser()
    )
    binary_path = cache_root / version / target.cache_name / target.binary_name
    if binary_path.exists():
        _ensure_executable(binary_path)
        logger.debug("Using cached Tailwind CSS binary: %s", binary_path)
        return binary_path

    release_base = f"{_RELEASE_BASE_URL}/{version}"
    logger.debug("Tailwind CSS binary cache miss: %s", binary_path)
    try:
        manifest = _parse_checksum_manifest(
            _read_url(f"{release_base}/sha256sums.txt").decode("utf-8"),
        )
    except urllib.error.URLError as exc:
        msg = f"Failed to download Tailwind CSS checksum manifest for {version}"
        raise RuntimeError(msg) from exc
    expected_checksum = manifest.get(target.asset_name)
    if expected_checksum is None:
        msg = f"Checksum for {target.asset_name} was not found in the release manifest"
        raise RuntimeError(msg)

    asset_url = f"{release_base}/{target.asset_name}"
    try:
        _download_to_path(asset_url, binary_path)
    except urllib.error.URLError as exc:
        msg = f"Failed to download Tailwind CSS binary for {version}"
        raise RuntimeError(msg) from exc
    actual_checksum = _sha256(binary_path)
    if actual_checksum != expected_checksum:
        binary_path.unlink(missing_ok=True)
        msg = (
            "Downloaded Tailwind CSS binary checksum mismatch: "
            f"expected {expected_checksum}, got {actual_checksum}"
        )
        raise RuntimeError(msg)

    _ensure_executable(binary_path)
    logger.debug("Finished Tailwind CSS auto-install: %s", binary_path)
    return binary_path
