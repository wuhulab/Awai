"""Build AutoAPI .app bundle for macOS."""

import argparse
import plistlib
import shutil
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    app_dir = Path(args.output)
    macos_dir = app_dir / "Contents" / "MacOS"
    resources_dir = app_dir / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    dist = Path(args.dist_dir)
    for subdir in ["AutoAPI-Server", "AutoAPI-UI"]:
        src = dist / subdir
        if not src.exists():
            print(f"WARNING: {src} not found, skipping", file=sys.stderr)
            continue
        for item in src.iterdir():
            dest = macos_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    plist = {
        "CFBundleName": "AutoAPI",
        "CFBundleDisplayName": "AutoAPI",
        "CFBundleIdentifier": "com.autoapi.app",
        "CFBundleVersion": args.version,
        "CFBundleShortVersionString": args.version,
        "CFBundleExecutable": "AutoAPI-UI",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright (c) AutoAPI Team",
    }
    with open(app_dir / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(plist, f)

    print(f"Created .app at {app_dir.resolve()}")


if __name__ == "__main__":
    main()
