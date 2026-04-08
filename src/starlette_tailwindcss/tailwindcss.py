"""Tailwind CSS CLI integration for Starlette applications."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import shutil
import string
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, overload

from starlette_tailwindcss.installer import install

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from os import PathLike

logger = logging.getLogger(__name__)

_BUILD_ID_ALPHABET = string.ascii_letters
_BUILD_ID_LENGTH = 8
_DEFAULT_BIN_NAME = "tailwindcss"
_PROCESS_STOP_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class Assets:
    """Resolved Tailwind asset metadata for the current startup."""

    build_id: str | None
    file_name: str


def _generate_build_id(length: int = _BUILD_ID_LENGTH) -> str:
    """Generate a short build id for cache-busting output filenames."""
    return "".join(secrets.choice(_BUILD_ID_ALPHABET) for _ in range(length))


class TailwindCSS:
    """Manage Tailwind CSS CLI build and watch mode."""

    @overload
    def __init__(
        self,
        *,
        input: str | PathLike[str],
        output: str | PathLike[str],
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        bin_path: str | PathLike[str],
        input: str | PathLike[str],
        output: str | PathLike[str],
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        version: str,
        input: str | PathLike[str],
        output: str | PathLike[str],
        cache_dir: str | PathLike[str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        *,
        input: str | PathLike[str],
        output: str | PathLike[str],
        bin_path: str | PathLike[str] | None = None,
        version: str | None = None,
        cache_dir: str | PathLike[str] | None = None,
    ) -> None:
        """Create a Tailwind CSS integration configuration."""
        if bin_path is not None and version is not None:
            msg = "`bin_path` and `version` are mutually exclusive"
            raise ValueError(msg)
        if cache_dir is not None and version is None:
            msg = "`cache_dir` requires `version`"
            raise ValueError(msg)
        if cache_dir is not None and bin_path is not None:
            msg = "`cache_dir` is only valid with `version`"
            raise ValueError(msg)

        self.input = Path(input)
        self.output_template = Path(output)
        self.bin_path = Path(bin_path).expanduser() if bin_path is not None else None
        self.version = version
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir is not None else None

    @asynccontextmanager
    async def build(self, *, watch: bool = False) -> AsyncIterator[Assets]:
        """Build Tailwind CSS once and optionally watch for changes."""
        assets, output_path = self._resolve_assets()
        binary = await self._resolve_binary()
        await self._build_once(binary, output_path)

        watch_process: asyncio.subprocess.Process | None = None
        stream_tasks: list[asyncio.Task[None]] = []
        if watch:
            watch_process, stream_tasks = await self._spawn_watch(
                binary,
                output_path,
            )

        try:
            yield assets
        finally:
            # Shutdown can race with external signal handlers during app teardown.
            # Shield cleanup so the watch process is always terminated.
            await asyncio.shield(self._shutdown_watch(watch_process, stream_tasks))

    async def _build_once(self, binary: Path, output: Path) -> None:
        """Run a one-time Tailwind build."""
        logger.info(
            "run build: %s build -i %s -o %s",
            binary,
            self.input,
            output,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "build",
            "-i",
            str(self.input),
            "-o",
            str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stream_tasks: list[asyncio.Task[None]] = []
        if process.stdout is not None:
            stream_tasks.append(
                asyncio.create_task(self._forward_stream(process.stdout, logging.INFO))
            )
        if process.stderr is not None:
            stream_tasks.append(
                asyncio.create_task(self._forward_stream(process.stderr, logging.DEBUG))
            )
        return_code = await process.wait()
        await self._drain_stream_tasks(stream_tasks)
        if return_code != 0:
            msg = f"Tailwind CSS build failed with exit code {return_code}"
            raise RuntimeError(msg)

    async def _spawn_watch(
        self,
        binary: Path,
        output: Path,
    ) -> tuple[asyncio.subprocess.Process, list[asyncio.Task[None]]]:
        """Start the Tailwind watch process and stream its output."""
        logger.info(
            "start watch: %s -i %s -o %s --watch",
            binary,
            self.input,
            output,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "-i",
            str(self.input),
            "-o",
            str(output),
            "--watch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stream_tasks: list[asyncio.Task[None]] = []
        if process.stdout is not None:
            stream_tasks.append(
                asyncio.create_task(self._forward_stream(process.stdout, logging.INFO))
            )
        if process.stderr is not None:
            stream_tasks.append(
                asyncio.create_task(self._forward_stream(process.stderr, logging.DEBUG))
            )
        return process, stream_tasks

    async def _shutdown_watch(
        self,
        process: asyncio.subprocess.Process | None,
        stream_tasks: list[asyncio.Task[None]],
    ) -> None:
        """Stop the Tailwind watch process and cancel output tasks."""
        if process is None:
            return

        logger.info("stop watch pid=%s", process.pid)
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=_PROCESS_STOP_TIMEOUT)
            except TimeoutError:
                process.kill()
                await process.wait()

        await self._drain_stream_tasks(stream_tasks)

    async def _drain_stream_tasks(self, stream_tasks: list[asyncio.Task[None]]) -> None:
        """Cancel process stream forwarders and wait for them to finish."""
        for task in stream_tasks:
            if not task.done():
                task.cancel()
        for task in stream_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _forward_stream(self, stream: asyncio.StreamReader, level: int) -> None:
        """Forward a process stream into the configured logger."""
        while True:
            line = await stream.readline()
            if not line:
                return
            message = line.decode("utf-8", errors="replace").rstrip()
            if message:
                logger.log(level, "%s", message)

    async def _resolve_binary(self) -> Path:
        """Return the binary to execute, resolving local or downloaded input."""
        if self.version is None:
            return self._resolve_local_binary()
        return await asyncio.to_thread(install, self.version, self.cache_dir)

    def _resolve_assets(self) -> tuple[Assets, Path]:
        """Resolve the build id, output path, and file name."""
        output_text = str(self.output_template)
        build_id = _generate_build_id() if "{build_id}" in output_text else None
        if build_id is not None:
            output_text = output_text.replace("{build_id}", build_id)
        output_path = Path(output_text).expanduser()
        assets = Assets(build_id=build_id, file_name=output_path.name)
        return assets, output_path

    def _resolve_local_binary(self) -> Path:
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

        resolved = shutil.which(_DEFAULT_BIN_NAME)
        if resolved is None:
            msg = f"`{_DEFAULT_BIN_NAME}` was not found on PATH"
            raise FileNotFoundError(msg)
        return Path(resolved)
