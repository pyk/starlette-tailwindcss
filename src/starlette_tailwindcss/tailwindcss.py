# ruff: noqa: A002
"""Tailwind CSS CLI integration for Starlette applications."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, overload

from .installer import download_binary

if TYPE_CHECKING:
    import os
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_DEFAULT_BIN_NAME = "tailwindcss"
_PROCESS_STOP_TIMEOUT = 5.0


class TailwindCSS:
    """Manage Tailwind CSS CLI build and watch mode."""

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
        cache_dir: str | os.PathLike[str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        *,
        input: str | os.PathLike[str],
        output: str | os.PathLike[str],
        bin_path: str | os.PathLike[str] | None = None,
        version: str | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
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
        self.output = Path(output)
        self.bin_path = Path(bin_path).expanduser() if bin_path is not None else None
        self.version = version
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir is not None else None

    @asynccontextmanager
    async def build(self, *, watch: bool = False) -> AsyncIterator[None]:
        """Build Tailwind CSS once and optionally watch for changes."""
        binary = await self._resolve_binary()
        await self._build_once(binary)

        watch_process: asyncio.subprocess.Process | None = None
        stream_tasks: list[asyncio.Task[None]] = []
        if watch:
            watch_process, stream_tasks = await self._spawn_watch(binary)

        try:
            yield
        finally:
            await self._shutdown_watch(watch_process, stream_tasks)

    async def _build_once(self, binary: Path) -> None:
        """Run a one-time Tailwind build."""
        logger.info(
            "Building Tailwind CSS output: %s build -i %s -o %s",
            binary,
            self.input,
            self.output,
        )
        self.output.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "build",
            "-i",
            str(self.input),
            "-o",
            str(self.output),
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
    ) -> tuple[asyncio.subprocess.Process, list[asyncio.Task[None]]]:
        """Start the Tailwind watch process and stream its output."""
        logger.info(
            "Spawning Tailwind CSS CLI in background: %s -i %s -o %s --watch",
            binary,
            self.input,
            self.output,
        )
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

        logger.info("Killing spawned Tailwind CSS CLI process: pid=%s", process.pid)
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
        return await asyncio.to_thread(download_binary, self.version, self.cache_dir)

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
