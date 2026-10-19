"""Bump the app version everywhere (python package, desktop app and lock files).

    uv run python scripts/bump_version.py 0.1.1

Then: git add -A, git commit, git tag v0.1.1, git push, git push --tags
The tag triggers .github/workflows/release.yml, which builds and publishes the installer; installed apps pick it up.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sub_file(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"Could not find the version in {path}")
    path.write_text(new, encoding="utf-8", newline="\n")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: uv run python scripts/bump_version.py 0.1.1")
    v = sys.argv[1]
    sub_file(ROOT / "pyproject.toml", r'^version = "[^"]+"', f'version = "{v}"')
    sub_file(ROOT / "src" / "vision" / "__init__.py", r'^__version__ = "[^"]+"', f'__version__ = "{v}"')
    npm = shutil.which("npm") or sys.exit("npm not found on PATH")
    subprocess.run([npm, "version", v, "--no-git-tag-version", "--allow-same-version"], cwd=ROOT / "desktop", check=True)
    uv = shutil.which("uv")
    if uv:
        subprocess.run([uv, "lock"], cwd=ROOT, check=False)
    print(f"\nVersion is now {v}. Next:")
    print(f'  git add -A ; git commit -m "Release {v}" ; git tag v{v} ; git push ; git push --tags')


if __name__ == "__main__":
    main()
