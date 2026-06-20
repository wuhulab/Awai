"""Build AppDir directory structure for AutoAPI AppImage / Linux packaging."""

import argparse
import shutil
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    out = Path(args.output)
    dist = Path(args.dist_dir)

    # Create directory structure
    bindir = out / "usr" / "bin"
    sharedir = out / "usr" / "share" / "autoapi"
    appdir = out / "usr" / "share" / "applications"
    bindir.mkdir(parents=True, exist_ok=True)
    sharedir.mkdir(parents=True, exist_ok=True)
    appdir.mkdir(parents=True, exist_ok=True)

    # Copy onedir bundles
    for subdir in ["AutoAPI-Server", "AutoAPI-UI"]:
        src = dist / subdir
        if not src.exists():
            print(f"WARNING: {src} not found, skipping", file=sys.stderr)
            continue
        for item in src.iterdir():
            dest = sharedir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Config files
    src_dir = Path.cwd()
    for cfg in ["System.json", "rules.json.example"]:
        cfg_src = src_dir / cfg
        if cfg_src.exists():
            shutil.copy2(cfg_src, sharedir / cfg)

    # Wrapper scripts
    wrappers = {
        "autoapi-server": "/usr/share/autoapi/AutoAPI-Server",
        "autoapi-ui": "/usr/share/autoapi/AutoAPI-UI",
    }
    for name, target in wrappers.items():
        script = bindir / name
        script.write_text(f'#!/bin/bash\nexec "{target}" "$@"\n')
        script.chmod(0o755)

    # Desktop entry
    desktop = appdir / "autoapi-ui.desktop"
    desktop.write_text(
        "[Desktop Entry]\n"
        "Name=AutoAPI\n"
        "Comment=AI-API Forwarding Tool\n"
        "Exec=autoapi-ui\n"
        "Icon=autoapi\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=Network;\n"
    )

    print(f"Created packaging structure at {out.resolve()}")


if __name__ == "__main__":
    main()
