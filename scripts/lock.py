"""Recompile the lockfiles and mark Windows-only packages.

pip-compile resolves for the platform it runs on. On Windows it pins packages
that only Windows needs (pywin32 for mcp, colorama for click) without a marker,
which breaks installs in Linux images and CI. This adds the marker back.

    python scripts/lock.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_ONLY = ("pywin32", "colorama")
MARKER = ' ; sys_platform == "win32"'


def compile_lock(src: str, out: str, *extra: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "-q",
            "--generate-hashes",
            "--strip-extras",
            *extra,
            "-o",
            out,
            src,
        ],
        cwd=ROOT,
        check=True,
    )


def mark_windows_only(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for name in WINDOWS_ONLY:
        text = re.sub(
            rf"^({re.escape(name)}==[^\s;]+)( \\)$",
            rf"\1{MARKER}\2",
            text,
            flags=re.M,
        )
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    compile_lock("requirements.in", "requirements.txt")
    compile_lock("requirements-dev.in", "requirements-dev.txt", "--allow-unsafe")
    for name in ("requirements.txt", "requirements-dev.txt"):
        mark_windows_only(ROOT / name)


if __name__ == "__main__":
    main()
