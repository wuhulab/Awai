"""Build AutoAPI AppImage by creating AppDir and running appimagetool."""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--pkg-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    appdir = Path(f"AutoAPI-{args.version}.AppDir")
    if appdir.exists():
        shutil.rmtree(appdir)

    shutil.copytree(args.pkg_dir, appdir, dirs_exist_ok=True)

    # AppRun
    apprun = appdir / "AppRun"
    lines = [
        "#!/bin/bash",
        'HERE="$(dirname "$(readlink -f "$0")")"',
        'exec "$HERE/bin/autoapi-ui"',
        "",
    ]
    apprun.write_text("\n".join(lines))
    apprun.chmod(0o755)

    # .desktop file
    desktop = appdir / "AutoAPI.desktop"
    lines = [
        "[Desktop Entry]",
        "Name=AutoAPI",
        "Comment=AI-API Forwarding Tool",
        "Exec=autoapi-ui",
        "Icon=autoapi",
        "Terminal=false",
        "Type=Application",
        "Categories=Network;Utility;",
        "",
    ]
    desktop.write_text("\n".join(lines))

    # Download appimagetool if not present
    tool = Path("/tmp/appimagetool")
    if not tool.exists():
        url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        print(f"Downloading appimagetool from {url}...")
        urllib.request.urlretrieve(url, tool)
        tool.chmod(0o755)

    # Build AppImage
    output_path = Path(args.output).resolve()
    cmd = [str(tool), "--no-appstream", str(appdir), str(output_path)]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"appimagetool failed (rc={result.returncode}), trying --appimage-extract-and-run...", file=sys.stderr)
        cmd = [str(tool), "--appimage-extract-and-run", "--no-appstream", str(appdir), str(output_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"stderr: {result.stderr}", file=sys.stderr)
        print(f"stdout: {result.stdout}", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"AppImage created: {output_path}")


if __name__ == "__main__":
    main()
