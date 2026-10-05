"""Publish a GitHub release with the built ImageNotes.exe and the portable ZIP."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from imagenotes import config  # noqa: E402

DIST = PROJECT_ROOT / "dist"
EXE = DIST / f"{config.APP_NAME}.exe"
ZIP = DIST / f"{config.APP_NAME}-{config.VERSION}-win64-portable.zip"

DEFAULT_NOTES = """\
ImageNotes {version}

Annotate images and very large maps on Windows. Portable: unpack and run, nothing to install.

Notes come as text (with colour, size and angle), an arrow, a cross, a checkmark and freehand
drawing. Pan with the right mouse button, zoom under the cursor with the wheel. Notes save
themselves into one working copy, so your original image is never touched and stays editable
when you open it again.

The exe is not code-signed, so SmartScreen shows "unknown publisher": More info -> Run anyway.
"""


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an ImageNotes release on GitHub")
    parser.add_argument("--tag", default=f"v{config.VERSION}", help="release tag (default: v<version>)")
    parser.add_argument("--notes", default="", help="release description (default: the template)")
    parser.add_argument("--no-build", action="store_true", help="do not build the exe")
    parser.add_argument(
        "--notes-only", action="store_true",
        help="only fix the description of an existing release (no build, no upload)",
    )
    args = parser.parse_args()

    if not shutil_which("gh"):
        print("error: gh CLI is not in PATH.")
        return 1
    status = gh("auth", "status")
    if status.returncode != 0:
        print("error: gh is not logged in. Run: gh auth login")
        return 1

    notes = args.notes or DEFAULT_NOTES.format(version=config.VERSION)

    if args.notes_only:
        edit = gh("release", "edit", args.tag, "--notes", notes,
                  "--title", f"{config.APP_NAME} {config.VERSION}")
        if edit.returncode != 0:
            print("error: could not update the description:", edit.stderr.strip())
            return 1
        print(f"Description of {args.tag} updated.")
        return 0

    if not args.no_build or not EXE.exists() or not ZIP.exists():
        print("Building the exe and the ZIP…")
        build = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "build_exe.py")])
        if build.returncode != 0:
            print("error: the build failed.")
            return 1

    assets = [p for p in (EXE, ZIP) if p.exists()]
    if not assets:
        print("error: nothing to upload in dist/")
        return 1
    for path in assets:
        print(f"  {path.name}: {path.stat().st_size / 1024 / 1024:.1f} MB")

    exists = gh("release", "view", args.tag).returncode == 0

    if exists:
        print(f"Release {args.tag} already exists, replacing the assets and the description.")
        upload = gh("release", "upload", args.tag, *[str(p) for p in assets], "--clobber")
        if upload.returncode != 0:
            print("error while uploading:", upload.stderr.strip())
            return 1
        edit = gh("release", "edit", args.tag, "--notes", notes, "--title", f"{config.APP_NAME} {config.VERSION}")
        if edit.returncode != 0:
            print("warning: could not update the description:", edit.stderr.strip())
    else:
        print(f"Creating release {args.tag}.")
        create = gh(
            "release", "create", args.tag,
            *[str(p) for p in assets],
            "--title", f"{config.APP_NAME} {config.VERSION}",
            "--notes", notes,
            "--target", "main",
        )
        if create.returncode != 0:
            print("error creating the release:", create.stderr.strip())
            return 1

    view = gh("release", "view", args.tag, "--json", "url,assets",
              "--jq", '"url: \\(.url)\\nfiles: " + ([.assets[] | "\\(.name) (\\(.size/1048576*100|round/100) MB)"] | join(", "))')
    print(view.stdout.strip() or "OK")
    return 0


def shutil_which(program: str) -> str:
    """Find a program in PATH without importing shutil (the name clashes with a local variable)."""
    import shutil

    return shutil.which(program) or ""


if __name__ == "__main__":
    raise SystemExit(main())
