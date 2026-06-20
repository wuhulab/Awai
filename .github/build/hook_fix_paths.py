"""PyInstaller runtime hook -- fix BASE_DIR for frozen builds."""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).parent.resolve()
    os.chdir(str(exe_dir))
    sys.path.insert(0, str(exe_dir))
