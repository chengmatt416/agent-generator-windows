#!/usr/bin/env python3
"""Build AgentGenerator as a standalone Windows executable.

Usage:
    pip install pyinstaller
    python build_exe.py

The .exe will be placed in dist/AgentGenerator/
"""

import os
import sys
from pathlib import Path

try:
    import PyInstaller.__main__ as pyi
except ImportError:
    print("Please install pyinstaller first: pip install pyinstaller")
    sys.exit(1)

HERE = Path(__file__).resolve().parent

args = [
    "--name=AgentGenerator",
    "--windowed",
    "--onefile",
    "--clean",
    "--noconfirm",
]

icon_path = HERE / "icon.ico"
if icon_path.exists():
    args.append(f"--icon={icon_path}")

args.append(f"--add-data={HERE / 'builtin_agents.py'}{os.pathsep}.")
args.append(str(HERE / "agent_generator.py"))

pyi.run(args)
