#!/usr/bin/env python3
"""Build AgentGenerator as a standalone Windows executable.

Usage:
    pip install pyinstaller PySide6 requests
    python build_exe.py

The .exe will be placed in dist/AgentGenerator.exe
"""

import os
import sys
from pathlib import Path

try:
    import PyInstaller.__main__ as pyi
except ImportError:
    print("Please install pyinstaller first: pip install pyinstaller PySide6 requests")
    sys.exit(1)

HERE = Path(__file__).resolve().parent

args = [
    "--name=AgentGenerator",
    "--windowed",
    "--onefile",
    "--clean",
    "--noconfirm",
    # Bundle all PySide6 modules, binaries, and data
    "--collect-all=PySide6",
    "--collect-binaries=PySide6",
    "--collect-data=PySide6",
    "--collect-submodules=PySide6",
    # Hidden imports for common Qt submodules
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtNetwork",
    "--hidden-import=PySide6.QtSvg",
    "--hidden-import=PySide6.QtXml",
    "--hidden-import=shiboken6",
]

icon_path = HERE / "icon.ico"
if icon_path.exists():
    args.append(f"--icon={icon_path}")

args.append(f"--add-data={HERE / 'builtin_agents.py'}{os.pathsep}.")
args.append(str(HERE / "agent_generator.py"))

pyi.run(args)
