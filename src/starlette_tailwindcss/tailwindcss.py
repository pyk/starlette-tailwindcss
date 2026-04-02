"""Tailwind CSS CLI integration for Starlette applications."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import platform
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, overload

from platformdirs import user_cache_dir

if TYPE_CHECKING:
    import os
    from collections.abc import AsyncIterator

    from starlette.applications import Starlette

logger = logging.getLogger(__name__)

APP_NAME = "starlette-tailwindcss"
RELEASE_BASE_URL = "https://github.com/tailwindlabs/tailwindcss/releases/download"
DEFAULT_BIN_NAME = "tailwindcss"
STREAM_PREFIX = "[tailwindcss]"
PROCESS_STOP_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class Target:
    """Resolved binary names for the current platform."""

    asset_name: str
    cache_name: str
    binary_name: str


def normalize_machine(machine: str) -> str:
    """Normalize platform machine names to Tailwind release names."""
    value = machine.lower()
    if value in {"x86_64", "amd64"}:
        return "x64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    msg = f"Unsupported machine architecture: {machine}"
    raise RuntimeError(msg)


def is_musl() -> bool:
    """Return `True` when the current Linux libc is musl."""
    libc_name, _ = platform.libc_ver()
    return libc_name.lower() == "musl"


def target_platform() -> Target:
    """Build the Tailwind release target for the current platform."""
    system = platform.system().lower()
    arch = normalize_machine(platform.machine())

    if system == "linux":
        suffix = "-musl" if is_musl() else ""
        asset_name = f"tailwindcss-linux-{arch}{suffix}"
        return Target(
            asset_name=asset_name,
            cache_name=asset_name,
            binary_name=asset_name,
        )
    if system == "darwin":
        asset_name = f"tailwindcss-macos-{arch}"
        return Target(
            asset_name=asset_name,
            cache_name=f"macos-{arch}",
            binary_name=asset_name,
        )
    if system == "windows":
        asset_name = "tailwindcss-windows-x64.exe"
        return Target(
            asset_name=asset_name,
            cache_name="windows-x64",
            binary_name=asset_name,
        )

    msg = f"Unsupported operating system: {platform.system()}"
    raise RuntimeError(msg)


def sha256(path: Path) -> str:
    """Calculate a SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_url(url: str) -> bytes:
    """Read the full contents of a URL."""
    with urllib.request.urlopen(url) as response:  # noqa: S310
        return response.read()


def download_to_path(url: str, path: Path) -> None:
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
        shutil.copyfileobj(response, file)
        temp_path = Path(file.name)
    temp_path.replace(path)


def parse_checksum_manifest(content: str) -> dict[str, str]:
    """Parse Tailwind's checksum manifest into a mapping."""
    checksums: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        checksum, asset_name = line.split(maxsplit=1)
        checksums[asset_name.removeprefix("./")] = checksum
    return checksums


def ensure_executable(path: Path) -> None:
    """Mark a file executable for the current user."""
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TailwindCSS:
    """Manage Tailwind CSS CLI watch mode from a Starlette lifespan."""

    @overload
    def __init__(
        self,
        *,
        bin_path: str | os.PathLike[str],
        input: str | os.PathLike[str],
        output: str | os.PathLike[str],
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        version: str,
        input: str | os.PathLike[str],
        output: str | os.PathLike[str],
    ) -> None: ...

    def __init__(
        self,
        *,
        input: str | os.PathLike[str],  # noqa: A002
        output: str | os.PathLike[str],
        bin_path: str | os.PathLike[str] | None = None,
        version: str | None = None,
    ) -> None:
        """Create a Tailwind CSS integration configuration."""
        if bin_path is not None and version is not None:
            msg = "`bin_path` and `version` are mutually exclusive"
            raise ValueError(msg)

        self.input = Path(input)
        self.output = Path(output)
        self.bin_path = Path(bin_path).expanduser() if bin_path is not None else None
        self.version = version

    def setup(self, app: Starlette) -> None:
        """Wrap the app lifespan so Tailwind starts and stops with the app."""
        if not app.debug:
            return

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(inner_app: Starlette) -> AsyncIterator[object]:
            async with original_lifespan(inner_app) as state:
                process, stream_tasks = await self.startup()
                try:
                    yield state
                finally:
                    await self.shutdown(process, stream_tasks)

        router = cast("Any", app.router)
        router.lifespan_context = cast("Any", lifespan)

    async def startup(
        self,
    ) -> tuple[asyncio.subprocess.Process, list[asyncio.Task[None]]]:
        """Start the Tailwind watch process and stream its output."""
        binary = await self.resolve_binary()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "-i",
            str(self.input),
            "-o",
            str(self.output),
            "--watch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stream_tasks: list[asyncio.Task[None]] = []
        if process.stdout is not None:
            stream_tasks.append(
                asyncio.create_task(self.forward_stream(process.stdout, logging.INFO))
            )
        if process.stderr is not None:
            stream_tasks.append(
                asyncio.create_task(self.forward_stream(process.stderr, logging.DEBUG))
            )
        return process, stream_tasks

    async def shutdown(
        self,
        process: asyncio.subprocess.Process,
        stream_tasks: list[asyncio.Task[None]],
    ) -> None:
        """Stop the Tailwind process and cancel output forwarding tasks."""
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=PROCESS_STOP_TIMEOUT)
            except TimeoutError:
                process.kill()
                await process.wait()

        for task in stream_tasks:
            if not task.done():
                task.cancel()
        for task in stream_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def forward_stream(self, stream: asyncio.StreamReader, level: int) -> None:
        """Forward a process stream into the configured logger."""
        while True:
            line = await stream.readline()
            if not line:
                return
            message = line.decode("utf-8", errors="replace").rstrip()
            if message:
                logger.log(level, "%s %s", STREAM_PREFIX, message)

    async def resolve_binary(self) -> Path:
        """Return the binary to execute, resolving local or downloaded input."""
        if self.version is None:
            return self.resolve_local_binary()
        return await asyncio.to_thread(self.download_binary)

    def resolve_local_binary(self) -> Path:
        """Resolve a local Tailwind binary from `bin_path` or `PATH`."""
        if self.bin_path is not None:
            candidate = self.bin_path
            if candidate.exists():
                return candidate
            resolved = shutil.which(str(candidate))
            if resolved is not None:
                return Path(resolved)
            msg = f"Tailwind CSS binary not found: {candidate}"
            raise FileNotFoundError(msg)

        resolved = shutil.which(DEFAULT_BIN_NAME)
        if resolved is None:
            msg = f"`{DEFAULT_BIN_NAME}` was not found on PATH"
            raise FileNotFoundError(msg)
        return Path(resolved)

    def download_binary(self) -> Path:
        """Download, verify, and cache the Tailwind binary for this version."""
        if self.version is None:
            msg = "A release version is required to download Tailwind CSS"
            raise RuntimeError(msg)

        target = target_platform()
        cache_root = Path(user_cache_dir(APP_NAME))
        binary_path = cache_root / self.version / target.cache_name / target.binary_name
        if binary_path.exists():
            ensure_executable(binary_path)
            return binary_path

        release_base = f"{RELEASE_BASE_URL}/{self.version}"
        try:
            manifest = parse_checksum_manifest(
                read_url(f"{release_base}/sha256sums.txt").decode("utf-8"),
            )
        except urllib.error.URLError as exc:
            msg = (
                f"Failed to download Tailwind CSS checksum manifest for {self.version}"
            )
            raise RuntimeError(msg) from exc
        expected_checksum = manifest.get(target.asset_name)
        if expected_checksum is None:
            msg = (
                f"Checksum for {target.asset_name} was not found in the "
                "release manifest"
            )
            raise RuntimeError(msg)

        asset_url = f"{release_base}/{target.asset_name}"
        try:
            download_to_path(asset_url, binary_path)
        except urllib.error.URLError as exc:
            msg = f"Failed to download Tailwind CSS binary for {self.version}"
            raise RuntimeError(msg) from exc
        actual_checksum = sha256(binary_path)
        if actual_checksum != expected_checksum:
            binary_path.unlink(missing_ok=True)
            msg = (
                "Downloaded Tailwind CSS binary checksum mismatch: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )
            raise RuntimeError(msg)

        ensure_executable(binary_path)
        return binary_path
