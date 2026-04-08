"""Integration tests for one-shot Tailwind builds."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from starlette_tailwindcss import build, tailwindcss

if TYPE_CHECKING:
    from pathlib import Path


def _write_fake_tailwind_binary(path: Path) -> None:
    """Create a tiny CLI shim that builds once and exits."""
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import pathlib
            import sys


            def main() -> int:
                args = sys.argv[1:]
                if "--watch" in args:
                    raise SystemExit(2)

                output = pathlib.Path(args[args.index("-o") + 1])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("/* fake tailwind */\\n", encoding="utf-8")
                return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.asyncio
async def test_build_uses_local_binary(tmp_path: Path) -> None:
    """Build once with a local Tailwind binary and return resolved assets."""
    input_css = tmp_path / "globals.css"
    output_css = tmp_path / "static" / "css" / "output.css"
    fake_bin = tmp_path / "tailwindcss"

    input_css.write_text('@import "tailwindcss";\n', encoding="utf-8")
    _write_fake_tailwind_binary(fake_bin)

    assets = await build(
        input=input_css,
        output=output_css,
        bin_path=fake_bin,
    )
    assert assets.build_id is None
    assert assets.file_name == "output.css"

    assert output_css.read_text(encoding="utf-8") == "/* fake tailwind */\n"


@pytest.mark.asyncio
async def test_build_uses_auto_install(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Build once with an auto-installed Tailwind binary."""
    input_css = tmp_path / "globals.css"
    output_css = tmp_path / "static" / "css" / "output.css"
    fake_bin = tmp_path / "tailwindcss"
    calls: list[tuple[str, Path | None]] = []

    input_css.write_text('@import "tailwindcss";\n', encoding="utf-8")
    _write_fake_tailwind_binary(fake_bin)

    def fake_install(version: str, cache_dir: Path | None = None) -> Path:
        calls.append((version, cache_dir))
        return fake_bin

    monkeypatch.setattr(tailwindcss, "install", fake_install)

    assets = await build(
        input=input_css,
        output=output_css,
        version="v4.2.2",
        cache_dir=tmp_path / "cache",
    )
    assert assets.build_id is None
    assert assets.file_name == "output.css"

    assert calls == [("v4.2.2", tmp_path / "cache")]
    assert output_css.read_text(encoding="utf-8") == "/* fake tailwind */\n"
