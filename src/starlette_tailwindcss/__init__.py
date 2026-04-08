"""Starlette integration for the Tailwind CSS CLI."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, overload

from starlette_tailwindcss.tailwindcss import Assets, TailwindCSS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable
    from os import PathLike

__all__ = ["Assets", "build", "tailwind"]


def _create_runner(
    *,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str] | None = None,
    version: str | None = None,
    cache_dir: str | PathLike[str] | None = None,
) -> TailwindCSS:
    """Create a Tailwind runner with the requested binary resolution mode."""
    if bin_path is not None and version is not None:
        msg = "`bin_path` and `version` are mutually exclusive"
        raise ValueError(msg)
    if cache_dir is not None and version is None:
        msg = "`cache_dir` requires `version`"
        raise ValueError(msg)
    if cache_dir is not None and bin_path is not None:
        msg = "`cache_dir` is only valid with `version`"
        raise ValueError(msg)
    if version is not None:
        return TailwindCSS(
            input=input,
            output=output,
            version=version,
            cache_dir=cache_dir,
        )
    if bin_path is not None:
        return TailwindCSS(
            input=input,
            output=output,
            bin_path=bin_path,
        )
    return TailwindCSS(
        input=input,
        output=output,
    )


@overload
def build(
    *,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str],
) -> Awaitable[Assets]: ...


@overload
def build(
    *,
    input: str | PathLike[str],
    output: str | PathLike[str],
    version: str,
    cache_dir: str | PathLike[str] | None = None,
) -> Awaitable[Assets]: ...


@overload
def build(
    *,
    input: str | PathLike[str],
    output: str | PathLike[str],
) -> Awaitable[Assets]: ...


async def build(
    *,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str] | None = None,
    version: str | None = None,
    cache_dir: str | PathLike[str] | None = None,
) -> Assets:
    """Build Tailwind CSS once and return resolved asset metadata."""
    runner = _create_runner(
        input=input,
        output=output,
        bin_path=bin_path,
        version=version,
        cache_dir=cache_dir,
    )
    async with runner.build(watch=False) as assets:
        return assets


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str],
) -> AbstractAsyncContextManager[Assets]: ...


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    version: str,
    cache_dir: str | PathLike[str] | None = None,
) -> AbstractAsyncContextManager[Assets]: ...


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
) -> AbstractAsyncContextManager[Assets]: ...


def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str] | None = None,
    version: str | None = None,
    cache_dir: str | PathLike[str] | None = None,
) -> AbstractAsyncContextManager[Assets]:
    """Build Tailwind CSS on demand and yield resolved asset metadata."""
    runner = _create_runner(
        input=input,
        output=output,
        bin_path=bin_path,
        version=version,
        cache_dir=cache_dir,
    )

    @asynccontextmanager
    async def runner_context() -> AsyncIterator[Assets]:
        async with runner.build(watch=watch) as assets:
            yield assets

    return runner_context()
