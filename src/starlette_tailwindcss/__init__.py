"""Starlette integration for the Tailwind CSS CLI."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, overload

from starlette_tailwindcss.tailwindcss import Assets, TailwindCSS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from os import PathLike

__all__ = ["Assets", "tailwind"]


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str],
    static_root: str | PathLike[str] | None = None,
    static_url: str = "/static",
) -> AbstractAsyncContextManager[Assets]: ...


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    version: str,
    cache_dir: str | PathLike[str] | None = None,
    static_root: str | PathLike[str] | None = None,
    static_url: str = "/static",
) -> AbstractAsyncContextManager[Assets]: ...


@overload
def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    static_root: str | PathLike[str] | None = None,
    static_url: str = "/static",
) -> AbstractAsyncContextManager[Assets]: ...


def tailwind(
    *,
    watch: bool = False,
    input: str | PathLike[str],
    output: str | PathLike[str],
    bin_path: str | PathLike[str] | None = None,
    version: str | None = None,
    cache_dir: str | PathLike[str] | None = None,
    static_root: str | PathLike[str] | None = None,
    static_url: str = "/static",
) -> AbstractAsyncContextManager[Assets]:
    """Build Tailwind CSS on demand and yield resolved asset metadata."""
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
        runner = TailwindCSS(
            input=input,
            output=output,
            version=version,
            cache_dir=cache_dir,
            static_root=static_root,
            static_url=static_url,
        )
    elif bin_path is not None:
        runner = TailwindCSS(
            input=input,
            output=output,
            bin_path=bin_path,
            static_root=static_root,
            static_url=static_url,
        )
    else:
        runner = TailwindCSS(
            input=input,
            output=output,
            static_root=static_root,
            static_url=static_url,
        )

    @asynccontextmanager
    async def runner_context() -> AsyncIterator[Assets]:
        async with runner.build(watch=watch) as assets:
            yield assets

    return runner_context()
