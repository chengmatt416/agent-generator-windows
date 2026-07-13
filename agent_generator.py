#!/usr/bin/env python3
"""Challenge 2026 Agent Generator — Windows Edition.

A PySide6 desktop app that generates, edits, validates, and deploys
Python AI agents for the Challenge 2026 game.

Usage:  python agent_generator.py
"""

from __future__ import annotations

import ast
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontDatabase, QIcon, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QFrame, QMenu,
)

from builtin_agents import AGENTS

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
LAUNCHER_DIR = Path("C:/Program Files/Launcher/Contents/Resources/agent")
MODELS = ["gemini-3.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]

PRESETS = [
    ("Aggressive Predictor",
     "Predict opponent position using velocity vector. Place mines (trap1) ahead of movement path, "
     "use dance line (trap6) when opponent is in open field, and ripple (trap7) to force jumps. "
     "Tsunami (trap4) to push opponent into existing traps. Spam cheap traps when energy is low, "
     "unleash expensive combos when energy > 80% cap. Heal aggressively at <=2 HP."),
    ("Energy Denier",
     "Focus on denying opponent energy balls. Always place trap1 (mine) and trap5 (slippery floor) "
     "near the energy ball position. When opponent has high combo (>=3), use trap6 (dance line) or "
     "trap7 (ripple) to force a jump and reset their combo. Prioritize trap5 on ball location. "
     "Use trap9 (watermelon) to bomb the ball area. Only heal when <=1 HP."),
    ("Zone Controller",
     "Control zones by placing trap5 (slippery floor) in key paths and chokepoints. Use trap4 "
     "(tsunami) to push opponent into slippery zones. Combined trap6 (dance line) + trap7 (ripple) "
     "for unavoidable jump-or-die scenarios. Trap8 (crack) to cut off escape. Trap2 (tracking ring) "
     "for chasing. Maintain energy reserve for zone control combos."),
    ("Corner Camper",
     "Camp near field edges. When opponent approaches corners/edges, hit them with trap10 (shotgun) "
     "from boundary. Use trap3 (seagull) from edges to chase. Trap9 (watermelon) for parabolic shots. "
     "Trap1 (mine) along walls. Heal when hurt. Best in early phases."),
    ("Phase Adaptive",
     "Dynamically adjust based on phase. Phase 0-1: cheap traps only (trap1, trap5). Phase 2-3: add "
     "trap2, trap3, trap9. Phase 4-5: full combos with trap6, trap7, trap4. Track elapsed time and "
     "phase transitions. Keep 10 energy buffer for emergencies. Print phase changes."),
]

GUIDE_TEXT = [
    ("1. Required imports", "from api import *  —  gives you Vector2, Direction, GameClientBase, ApiError"),
    ("2. Entry point", "def run(client):  —  this is where your agent logic lives"),
    ("3. Game loop", "while True:  —  keep running; the game feeds data each iteration"),
    ("4. Read state", "Use client.get_*() to read positions, energy, health, combo, phase"),
    ("5. Place traps", "client.spawn_trap1(Vector2(x, y)) through spawn_trap10(...)"),
    ("6. Heal when hurt", "client.heal()  —  max 2 heals per game, cost varies by phase"),
    ("7. Error handling", "API returns ApiError on failure; check with isinstance(result, ApiError)"),
    ("8. Debug", "print() works — shows in terminal (non-default agent) or agent.log"),
]

API_REFERENCE = {
    "Read Functions (use client. prefix)": [
        ("client.get_my_health()", "→ int"),
        ("client.get_my_energy()", "→ int"),
        ("client.get_opponent_player_position()", "→ Vector2"),
        ("client.get_opponent_energy_ball_position()", "→ Vector2"),
        ("client.get_opponent_player_velocity()", "→ Vector2"),
        ("client.get_elapsed_time()", "→ float (seconds)"),
        ("client.get_opponent_combo()", "→ int (0-5)"),
        ("client.get_phase()", "→ int (0-5)"),
        ("client.get_available_traps()", "→ [int]"),
        ("client.get_cooldown_time(trap_id)", "→ float"),
    ],
    "Actions": [("client.heal()", "→ dict or ApiError")],
    "Traps (use client. prefix)": [
        ("client.spawn_trap1(pos)", "mine, cost 5"),
        ("client.spawn_trap2(time, radius)", "ring, cost 15"),
        ("client.spawn_trap3(pos, dir, speed)", "seagull, cost 13"),
        ("client.spawn_trap4(pos, dir)", "tsunami, cost 20"),
        ("client.spawn_trap5(pos)", "slippery, cost 5"),
        ("client.spawn_trap6(dir, speed)", "dance, cost 20"),
        ("client.spawn_trap7(pos, rate)", "ripple, cost 20"),
        ("client.spawn_trap8(start, end)", "crack, cost 15"),
        ("client.spawn_trap9(start, end, air)", "watermelon, cost 12"),
        ("client.spawn_trap10(pos, d1,d2,d3)", "shotgun, cost 15"),
    ],
    "Types": [
        ("Vector2(x, y)", "2D coordinate"),
        ("Direction.UP/DOWN/LEFT/RIGHT", "unit vectors"),
    ],
    "Tips": [
        "• Available traps: check 6 in client.get_available_traps()",
        "• Cooldown: client.get_cooldown_time(1) == 0.0",
        "• Error: isinstance(result, ApiError)",
        "• Silence: client.print_api_errors = False",
    ],
}


# ──────────────────────────────────────────────
# Python Syntax Highlighter
# ──────────────────────────────────────────────
class PythonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []
        self._setup_rules()

    def _fmt(self, color: str, bold=False, italic=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    def _setup_rules(self):
        kw = r'\b(?:def|if|else|elif|while|for|in|return|import|from|as|class|try|except|finally|raise|with|pass|break|continue|and|or|not|True|False|None|is|lambda|yield|global|nonlocal|assert|del)\b'

        comments = (r'#[^\n]*', self._fmt('#2e7d32'))
        strings = (r'"(?:[^"\\]|\\.)*"', self._fmt('#d32f2f'))
        strings_s = (r"'(?:[^'\\]|\\.)*'", self._fmt('#d32f2f'))
        numbers = (r'\b(?:[0-9]+\.?[0-9]*|\.[0-9]+)\b', self._fmt('#9e6a00'))
        decorators = (r'@\w+', self._fmt('#8d6e00'))
        api_calls = (r'\bclient\.\w+\(', self._fmt('#00796b'))
        trap_calls = (r'\bspawn_trap\d+\(', self._fmt('#00796b'))
        keywords = (kw, self._fmt('#2e3bb0'))
        func_def = (r'\bdef\s+(\w+)', self._fmt('#2e3bb0', bold=True), 1)
        cls_def = (r'\bclass\s+(\w+)', self._fmt('#2e3bb0', bold=True), 1)

        self._rules = [
            comments, strings, strings_s, numbers, decorators,
            api_calls, trap_calls, keywords, func_def, cls_def,
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt, *extra in self._rules:
            group = extra[0] if extra else 0
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(group), m.end(group) - m.start(group), fmt)


# ──────────────────────────────────────────────
# Gemini API
# ──────────────────────────────────────────────
GEMINI_SYSTEM_PROMPT = """You are an expert at writing Python AI agents for the game "Challenge 2026 — CSIE's Scenic Island Escape".

## Game Rules
- 2-player PvP, 5 min per round, 440x440 field centered at (0,0)
- Each player has 5 HP, loses 1 HP when hit by a damage trap
- Players move with WASD + Space (jump, 0.5s airtime), speed 300 units/s
- Your agent controls trap placement only (not movement)
- 10 trap types, each with energy cost, cooldown, and unique mechanics
- Energy regens naturally (faster over time) and via energy balls
- 6 phases (0-5) with increasing energy caps and regen rates
- Heal up to 2 times per game (restores 2 HP)

## Required Imports
```python
from api import *
import math
import random
```

## Entry Point (example structure)
```python
def run(client):
    client.print_api_errors = False
    while True:
        health = client.get_my_health()
        energy = client.get_my_energy()
        pos = client.get_opponent_player_position()
        # your logic here
        client.spawn_trap1(pos)
        result = client.heal()
```

## Available API (all methods must be called via `client.` prefix)

### Read Functions
- `client.get_my_health() -> int`
- `client.get_my_energy() -> int`
- `client.get_opponent_player_position() -> Vector2`
- `client.get_opponent_energy_ball_position() -> Vector2`
- `client.get_opponent_player_velocity() -> Vector2`
- `client.get_elapsed_time() -> float`
- `client.get_opponent_combo() -> int`
- `client.get_phase() -> int` (0-5)
- `client.get_available_traps() -> list[int]`
- `client.get_cooldown_time(trap_id: int) -> float`

### Heal
- `client.heal()` — heals 2 HP, max 2 uses per game

### Traps (10 types, all called via `client.`)
1. `client.spawn_trap1(position: Vector2)` — mine, cost 5, cooldown 2s, damage trap
2. `client.spawn_trap2(time: float, radius: float)` — tracking ring, cost 15, cooldown 5s, reveals and damages
3. `client.spawn_trap3(position: Vector2, direction: Vector2, speed: float)` — seagull, cost 13, cooldown 4s, projectile trap
4. `client.spawn_trap4(position: Vector2, direction: Vector2)` — tsunami, cost 20, cooldown 8s, pushes opponent
5. `client.spawn_trap5(position: Vector2)` — slippery floor, cost 5, cooldown 3s, makes opponent slide
6. `client.spawn_trap6(direction: Direction, speed: float)` — dance line, cost 20, cooldown 8s, forces jump
7. `client.spawn_trap7(position: Vector2, rate: float)` — ripple, cost 20, cooldown 8s, periodic wave
8. `client.spawn_trap8(start: Vector2, end: Vector2)` — crack, cost 15, cooldown 5s, line trap
9. `client.spawn_trap9(start: Vector2, end: Vector2, air_time: float)` — watermelon, cost 12, cooldown 5s, parabolic
10. `client.spawn_trap10(position: Vector2, dir1: Vector2, dir2: Vector2, dir3: Vector2)` — shotgun, cost 15, cooldown 6s

### Types
- `Vector2(x: float, y: float)` — 2D coordinate with `.x` and `.y` properties
- `Direction` — enum with `.UP`, `.DOWN`, `.LEFT`, `.RIGHT`

### Error Handling
```python
result = client.spawn_trap1(Vector2(0, 0))
if isinstance(result, ApiError):
    print(f"Failed: {result}")
```

## Output Rules
- Output ONLY the Python code, no explanation or markdown (no ```python either)
- Include `client.print_api_errors = False` at the start of run()
- Print status every ~2 seconds with print()
- Use print() for debug output
- CRITICAL: All API calls MUST use client. prefix — e.g. `client.get_my_health()`, `client.spawn_trap1(pos)`, `client.heal()`. Never call API functions without `client.`."""


def gemini_generate(api_key: str, model: str, strategy: str, timeout: int = 120) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    full_prompt = GEMINI_SYSTEM_PROMPT + "\n\n## Player's Strategy\n" + strategy + "\n\nGenerate the agent code:"
    payload = {
        "contents": [
            {"parts": [{"text": full_prompt}]}
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e

    candidates = result.get("candidates", [])
    if not candidates:
        raise RuntimeError("No response from API")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    return text.strip()


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────
def validate_code(code: str) -> dict:
    result = {"passed": False, "syntax_ok": False, "has_import": False, "has_run_func": False, "errors": []}

    try:
        tree = ast.parse(code)
        result["syntax_ok"] = True
    except SyntaxError as e:
        result["errors"].append(f"Syntax error: {e}")
        return result

    imports_from_api = any(
        isinstance(n, ast.ImportFrom) and n.module == "api" for n in ast.walk(tree)
    )
    has_run = any(
        isinstance(n, ast.FunctionDef) and n.name == "run"
        and any(a.id == "client" for a in n.args.args if isinstance(a, ast.Name))
        for n in ast.walk(tree)
    )
    result["has_import"] = imports_from_api
    result["has_run_func"] = has_run

    if not imports_from_api:
        result["errors"].append("Missing `from api import *`")
    if not has_run:
        result["errors"].append("Missing `def run(client)`")
    if result["syntax_ok"] and imports_from_api and has_run:
        result["passed"] = True
    return result


# ──────────────────────────────────────────────
# Deploy
# ──────────────────────────────────────────────
def deploy_as_default(code: str) -> str | None:
    agent_dir = LAUNCHER_DIR
    if not agent_dir.is_dir():
        return f"Launcher directory not found at {agent_dir}"

    try:
        agent_py = agent_dir / "agent.py"
        backup = agent_dir / "agent.py.backup"
        if not backup.exists() and agent_py.exists():
            import shutil
            shutil.copy2(str(agent_py), str(backup))

        agent_py.write_text(code, encoding="utf-8")

        verify = agent_py.read_text(encoding="utf-8")
        if len(verify) != len(code):
            return "Verification failed: size mismatch"
        _update_player_settings_agent_path()
        return None
    except Exception as e:
        return f"Deploy failed: {e}"


def deploy_with_wrapper(code: str) -> str | None:
    agent_dir = LAUNCHER_DIR
    if not agent_dir.is_dir():
        return f"Launcher directory not found at {agent_dir}"

    try:
        scripts_dir = agent_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        custom_path = scripts_dir / "agent_custom.py"
        custom_path.write_text(code, encoding="utf-8")

        agent_py = agent_dir / "agent.py"
        backup = agent_dir / "agent.py.wrapperbak"
        if not backup.exists() and agent_py.exists():
            import shutil
            shutil.copy2(str(agent_py), str(backup))

        wrapper = """# ruff: disable[F403]
# ruff: disable[F405]
from api import *
from scripts.agent_custom import run
"""
        agent_py.write_text(wrapper, encoding="utf-8")

        verify = agent_py.read_text(encoding="utf-8")
        if "agent_custom" not in verify:
            return "Verification failed: wrapper content mismatch"
        _update_player_settings_agent_path()
        return None
    except Exception as e:
        return f"Wrapper deploy failed: {e}"


def _player_settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", ""))
    else:
        base = Path.home()
    return base / "Godot/app_userdata/Challenge2026/player_settings.cfg"


def _update_player_settings_agent_path() -> None:
    settings_path = _player_settings_path()
    agent_py = LAUNCHER_DIR / "agent.py"
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        if settings_path.exists():
            lines = settings_path.read_text(encoding="utf-8").splitlines()
            replaced = False
            for i, line in enumerate(lines):
                if line.startswith("last_agent_file="):
                    lines[i] = f'last_agent_file="{agent_py}"'
                    replaced = True
                    break
            if not replaced:
                lines.append(f'last_agent_file="{agent_py}"')
            settings_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            settings_path.write_text(f'[file_selector]\nlast_agent_file="{agent_py}"\n', encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not update player settings: {e}")


def launch_launcher():
    import subprocess
    try:
        if sys.platform == "win32":
            os.startfile(str(LAUNCHER_DIR.parent.parent.parent / "Launcher.exe"))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "/Applications/Launcher.app"])
        else:
            subprocess.Popen(["xdg-open", str(LAUNCHER_DIR.parent)])
    except Exception as e:
        raise RuntimeError(f"Failed to launch game: {e}")


# ──────────────────────────────────────────────
# History persistence
# ──────────────────────────────────────────────
HISTORY_FILE = Path.home() / ".agent_generator_history.json"


def load_history() -> list[dict]:
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text("utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def save_history(items: list[dict]):
    try:
        HISTORY_FILE.write_text(json.dumps(items[-50:], ensure_ascii=False), "utf-8")
    except Exception:
        pass


# ──────────────────────────────────────────────
# Code Stats
# ──────────────────────────────────────────────
def compute_stats(code: str) -> dict:
    return {
        "lines": code.count("\n"),
        "functions": code.count("def "),
        "traps": sorted(set(i for i in range(1, 11) if f"spawn_trap{i}" in code)),
        "api_calls": len(re.findall(r"client\.\w+", code)),
    }


# ══════════════════════════════════════════════
# UI Helpers
# ══════════════════════════════════════════════
def _make_card_frame(title: str, description: str, parent=None) -> QFrame:
    frame = QFrame(parent)
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet("""
        QFrame { border: 1px solid #ccc; border-radius: 8px; padding: 8px;
                  background: #fafafa; margin: 2px; }
        QFrame:hover { background: #f0f0f0; border-color: #ff9800; }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    name_lbl = QLabel(title)
    name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
    layout.addWidget(name_lbl)
    desc_lbl = QLabel(description)
    desc_lbl.setWordWrap(True)
    desc_lbl.setStyleSheet("font-size: 11px; color: #666;")
    layout.addWidget(desc_lbl)
    return frame


def _make_section_card(title: str, icon_text: str, widget: QWidget) -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet("""
        QFrame { border: 1px solid #ddd; border-radius: 8px; padding: 10px;
                  background: white; margin: 0px; }
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)

    header = QLabel(f"{icon_text}  {title}")
    header.setStyleSheet("font-size: 12px; font-weight: 600; color: #555; padding-bottom: 4px;")
    layout.addWidget(header)
    layout.addWidget(widget)
    return frame


# ══════════════════════════════════════════════
# Main Window
# ══════════════════════════════════════════════
class AgentGeneratorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agent Generator — Challenge 2026")
        self.setMinimumSize(680, 800)
        self.resize(900, 850)

        # ── State ──
        self.api_key = ""
        self.model_name = MODELS[0]
        self.generated_code = ""
        self.manual_code = ""
        self.strategy_history: list[dict] = load_history()

        # ── Central widget ──
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QLabel("⚡ Agent Generator")
        header.setStyleSheet("""
            font-size: 22px; font-weight: bold; padding: 14px 20px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #fff3e0, stop:1 #ffffff);
            border-bottom: 1px solid #eee;
        """)
        main_layout.addWidget(header)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; }
            QTabBar::tab { padding: 10px 20px; font-size: 13px; }
            QTabBar::tab:selected { border-bottom: 2px solid #ff9800; color: #e65100; font-weight: bold; }
        """)
        main_layout.addWidget(self.tabs)

        # Create tabs
        self.ai_tab = self._build_ai_tab()
        self.builtin_tab = self._build_builtin_tab()
        self.manual_tab = self._build_manual_tab()

        self.tabs.addTab(self.ai_tab, "🤖  AI Generate")
        self.tabs.addTab(self.builtin_tab, "📦  Built-in")
        self.tabs.addTab(self.manual_tab, "✏️  Manual")

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("padding: 6px 16px; color: #666; font-size: 11px; "
                                         "border-top: 1px solid #eee; background: #fafafa;")
        main_layout.addWidget(self.status_label)

        # Connect tab change
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Load saved API key
        self._load_settings()

    def toast(self, message: str, is_error: bool = False):
        self.status_label.setText(message)
        color = "#c62828" if is_error else "#2e7d32"
        self.status_label.setStyleSheet(f"padding: 6px 16px; color: {color}; "
                                         f"font-size: 11px; border-top: 1px solid #eee; background: #fafafa;")
        QTimer.singleShot(5000, self._reset_status)

    def _reset_status(self):
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("padding: 6px 16px; color: #666; font-size: 11px; "
                                         "border-top: 1px solid #eee; background: #fafafa;")

    def _load_settings(self):
        import json
        try:
            p = Path.home() / ".agent_generator_settings.json"
            if p.exists():
                d = json.loads(p.read_text("utf-8"))
                self.api_key = d.get("api_key", "")
                self.model_name = d.get("model", MODELS[0])
                self.api_key_input.setText(self.api_key)
                idx = self.model_combo.findText(self.model_name)
                if idx >= 0:
                    self.model_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _save_settings(self):
        import json
        try:
            p = Path.home() / ".agent_generator_settings.json"
            d = {"api_key": self.api_key, "model": self.model_name}
            p.write_text(json.dumps(d), "utf-8")
        except Exception:
            pass

    # ──────── Tab: AI Generate ────────
    def _build_ai_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(12)

        # API Key
        api_group = QWidget()
        api_layout = QHBoxLayout(api_group)
        api_layout.setContentsMargins(0, 0, 0, 0)
        api_label = QLabel("🔑 API Key")
        api_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        api_layout.addWidget(api_label)
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your Gemini API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        api_layout.addWidget(self.api_key_input)
        self.api_toggle_btn = QPushButton("👁")
        self.api_toggle_btn.setFixedWidth(30)
        self.api_toggle_btn.setCheckable(True)
        self.api_toggle_btn.toggled.connect(
            lambda c: self.api_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )
        api_layout.addWidget(self.api_toggle_btn)
        layout.addWidget(api_group)

        # Model
        model_group = QWidget()
        model_layout = QHBoxLayout(model_group)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_label = QLabel("🧠 Model")
        model_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        model_layout.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(MODELS)
        self.model_combo.currentTextChanged.connect(lambda t: setattr(self, "model_name", t))
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        layout.addWidget(model_group)

        # Strategy
        strat_group = QGroupBox("Strategy Description")
        strat_group.setStyleSheet("QGroupBox { font-weight: 600; font-size: 12px; padding-top: 12px; }")
        strat_layout = QVBoxLayout(strat_group)
        self.strategy_input = QPlainTextEdit()
        self.strategy_input.setPlaceholderText("Describe your agent's strategy in detail...")
        self.strategy_input.setMinimumHeight(80)
        self.strategy_input.setMaximumHeight(120)
        strat_layout.addWidget(self.strategy_input)

        # Presets
        presets_label = QLabel("Presets:")
        presets_label.setStyleSheet("font-size: 11px; color: #888;")
        strat_layout.addWidget(presets_label)
        preset_scroll = QScrollArea()
        preset_scroll.setWidgetResizable(True)
        preset_scroll.setMaximumHeight(200)
        preset_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preset_container = QWidget()
        preset_list_layout = QVBoxLayout(preset_container)
        preset_list_layout.setContentsMargins(0, 0, 0, 0)
        preset_list_layout.setSpacing(4)
        for name, desc in PRESETS:
            btn = QPushButton(name)
            btn.setStyleSheet("""
                QPushButton { text-align: left; padding: 6px 10px; border: 1px solid #ddd;
                              border-radius: 4px; background: #f9f9f9; font-size: 11px; }
                QPushButton:hover { background: #fff3e0; border-color: #ff9800; }
            """)
            btn.clicked.connect(lambda _, n=name, d=desc: self._load_preset(n, d))
            preset_list_layout.addWidget(btn)
        preset_scroll.setWidget(preset_container)
        strat_layout.addWidget(preset_scroll)
        layout.addWidget(strat_group)

        # History
        history_group = QWidget()
        history_layout = QHBoxLayout(history_group)
        history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_btn = QPushButton("📜  History")
        self.history_btn.clicked.connect(self._show_history)
        history_layout.addWidget(self.history_btn)
        history_layout.addStretch()
        layout.addWidget(history_group)

        # Generate button
        self.generate_btn = QPushButton("✨  Generate Agent")
        self.generate_btn.setStyleSheet("""
            QPushButton { padding: 10px 24px; font-size: 14px; font-weight: bold;
                          background: #ff9800; color: white; border: none; border-radius: 6px; }
            QPushButton:hover { background: #f57c00; }
            QPushButton:disabled { background: #ccc; }
        """)
        self.generate_btn.clicked.connect(self._generate)
        layout.addWidget(self.generate_btn)

        # Output area
        output_group = QGroupBox("Generated Code")
        output_group.setStyleSheet("QGroupBox { font-weight: 600; font-size: 12px; padding-top: 12px; }")
        output_layout = QVBoxLayout(output_group)
        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(True)
        self.output_editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        output_layout.addWidget(self.output_editor)

        # Output actions
        out_actions = QHBoxLayout()
        self.validate_btn = QPushButton("✓  Validate")
        self.validate_btn.clicked.connect(lambda: self._validate(self.generated_code))
        out_actions.addWidget(self.validate_btn)
        out_actions.addStretch()

        self.deploy_btn = QPushButton("🚀  Deploy to Launcher")
        self.deploy_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #ff9800; color: white; "
                                       "border: none; border-radius: 4px; font-weight: bold; }"
                                       "QPushButton:disabled { background: #ccc; }")
        self.deploy_btn.clicked.connect(lambda: self._deploy(self.generated_code))
        out_actions.addWidget(self.deploy_btn)

        self.deploy_wrapper_btn = QPushButton("🔗  Deploy w/ Wrapper")
        self.deploy_wrapper_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #7b1fa2; color: white; "
                                               "border: none; border-radius: 4px; font-weight: bold; }"
                                               "QPushButton:disabled { background: #ccc; }")
        self.deploy_wrapper_btn.clicked.connect(lambda: self._deploy_wrapper(self.generated_code))
        out_actions.addWidget(self.deploy_wrapper_btn)
        output_layout.addLayout(out_actions)
        layout.addWidget(output_group)

        # Stats
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(self.stats_label)

        layout.addStretch()
        return scroll

    def _on_api_key_changed(self, text: str):
        self.api_key = text.strip()
        self._save_settings()

    def _load_preset(self, name: str, desc: str):
        self.strategy_input.setPlainText(desc)

    def _generate(self):
        if not self.api_key:
            QMessageBox.warning(self, "Missing API Key", "Please enter your Gemini API key.")
            return
        strategy = self.strategy_input.toPlainText().strip()
        if not strategy:
            QMessageBox.warning(self, "Missing Strategy", "Please describe your agent's strategy.")
            return

        self.generate_btn.setEnabled(False)
        self.generate_btn.setText("⏳ Generating...")
        self.toast("Contacting Gemini API...", is_error=False)
        QApplication.processEvents()

        try:
            code = gemini_generate(self.api_key, self.model_name, strategy)
            self.generated_code = code
            self.output_editor.setPlainText(code)

            # Save to history
            self.strategy_history.insert(0, {
                "strategy": strategy,
                "model": self.model_name,
                "date": time.strftime("%Y-%m-%d %H:%M"),
                "code": code,
            })
            save_history(self.strategy_history)

            stats = compute_stats(code)
            self.stats_label.setText(
                f"📊 {stats['lines']} lines | {stats['functions']} functions | "
                f"{len(stats['traps'])} trap types | {stats['api_calls']} API calls"
            )
            self.toast("✅ Agent generated successfully!", is_error=False)
        except Exception as e:
            self.toast(f"❌ Generation failed: {e}", is_error=True)
            QMessageBox.critical(self, "Generation Failed", str(e))
        finally:
            self.generate_btn.setEnabled(True)
            self.generate_btn.setText("✨  Generate Agent")

    def _show_history(self):
        if not self.strategy_history:
            QMessageBox.information(self, "History", "No history yet.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Strategy History")
        dlg.resize(500, 400)
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        for i, item in enumerate(self.strategy_history):
            text = f"[{item.get('date', '?')}] {item.get('model', '?')} — {item.get('strategy', '')[:60]}..."
            lst.addItem(QListWidgetItem(text))
        layout.addWidget(lst)

        def _load_hist():
            idx = lst.currentRow()
            if idx >= 0 and idx < len(self.strategy_history):
                item = self.strategy_history[idx]
                self.strategy_input.setPlainText(item.get("strategy", ""))
                self.generated_code = item.get("code", "")
                self.output_editor.setPlainText(self.generated_code)
                dlg.accept()

        load_btn = QPushButton("Load Selected")
        load_btn.clicked.connect(_load_hist)
        layout.addWidget(load_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.reject)
        layout.addWidget(close_btn)
        dlg.exec()

    # ──────── Tab: Built-in ────────
    def _build_builtin_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        self.selected_builtin = ""
        self.builtin_card_frames: list[QFrame] = []
        self.builtin_code_map: dict[str, str] = {}

        for agent in AGENTS:
            frame = _make_card_frame(agent["name"], agent["description"])
            frame.mousePressEvent = lambda _, n=agent["name"]: self._select_builtin(n)
            layout.addWidget(frame)
            self.builtin_card_frames.append(frame)
            self.builtin_code_map[agent["name"]] = agent["code"]

            # Click indicator
            click_lbl = QLabel("Click to select")
            click_lbl.setStyleSheet("font-size: 10px; color: #bbb; text-align: right;")
            click_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            frame.layout().addWidget(click_lbl)

        # Action bar
        action_bar = QHBoxLayout()
        self.builtin_validate_btn = QPushButton("✓  Validate")
        self.builtin_validate_btn.setEnabled(False)
        self.builtin_validate_btn.clicked.connect(lambda: self._validate(self.generated_code))
        action_bar.addWidget(self.builtin_validate_btn)
        action_bar.addStretch()

        self.builtin_deploy_btn = QPushButton("🚀  Deploy to Launcher")
        self.builtin_deploy_btn.setEnabled(False)
        self.builtin_deploy_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #ff9800; color: white; "
                                               "border: none; border-radius: 4px; font-weight: bold; }"
                                               "QPushButton:disabled { background: #ccc; }")
        self.builtin_deploy_btn.clicked.connect(lambda: self._deploy(self.generated_code))
        action_bar.addWidget(self.builtin_deploy_btn)

        self.builtin_wrapper_btn = QPushButton("🔗  Deploy w/ Wrapper")
        self.builtin_wrapper_btn.setEnabled(False)
        self.builtin_wrapper_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #7b1fa2; color: white; "
                                                "border: none; border-radius: 4px; font-weight: bold; }"
                                                "QPushButton:disabled { background: #ccc; }")
        self.builtin_wrapper_btn.clicked.connect(lambda: self._deploy_wrapper(self.generated_code))
        action_bar.addWidget(self.builtin_wrapper_btn)
        layout.addLayout(action_bar)

        # Status for selected
        self.builtin_status = QLabel("")
        self.builtin_status.setStyleSheet("font-size: 11px; color: #888; padding: 4px 0;")
        layout.addWidget(self.builtin_status)

        layout.addStretch()
        return scroll

    def _select_builtin(self, name: str):
        self.selected_builtin = name
        self.generated_code = self.builtin_code_map.get(name, "")
        self.builtin_status.setText(f"Selected: {name} — {len(self.generated_code.splitlines())} lines")
        self.builtin_validate_btn.setEnabled(True)
        self.builtin_deploy_btn.setEnabled(True)
        self.builtin_wrapper_btn.setEnabled(True)

        for frame in self.builtin_card_frames:
            frame.setStyleSheet("""
                QFrame { border: 1px solid #ccc; border-radius: 8px; padding: 8px;
                          background: #fafafa; margin: 2px; }
            """)
        # Highlight selected
        idx = [a["name"] for a in AGENTS].index(name)
        if idx >= 0:
            self.builtin_card_frames[idx].setStyleSheet("""
                QFrame { border: 2px solid #ff9800; border-radius: 8px; padding: 8px;
                          background: #fff3e0; margin: 2px; }
            """)

    # ──────── Tab: Manual ────────
    def _build_manual_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)

        # Guide section (collapsible)
        self.guide_visible = True
        self.guide_frame = QFrame()
        self.guide_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.guide_frame.setStyleSheet("""
            QFrame { border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px;
                      background: #f5f5f5; }
        """)
        guide_layout = QVBoxLayout(self.guide_frame)
        guide_title = QLabel("📖 Agent Writing Guide")
        guide_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #555;")
        guide_layout.addWidget(guide_title)
        for label, detail in GUIDE_TEXT:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #333;")
            lbl.setFixedWidth(150)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            det = QLabel(detail)
            det.setWordWrap(True)
            det.setStyleSheet("font-size: 11px; color: #666;")
            row.addWidget(det)
            guide_layout.addLayout(row)
        hide_btn = QPushButton("Hide Guide")
        hide_btn.setFixedWidth(100)
        hide_btn.clicked.connect(self._toggle_guide)
        guide_layout.addWidget(hide_btn, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.guide_frame)

        self.show_guide_btn = QPushButton("📖 Show Guide")
        self.show_guide_btn.setFixedWidth(120)
        self.show_guide_btn.clicked.connect(self._toggle_guide)
        self.show_guide_btn.hide()
        layout.addWidget(self.show_guide_btn)

        # Editor section
        editor_card = QFrame()
        editor_card.setFrameShape(QFrame.Shape.StyledPanel)
        editor_card.setStyleSheet("""
            QFrame { border: 1px solid #ddd; border-radius: 8px; padding: 8px; background: white; }
        """)
        editor_layout = QVBoxLayout(editor_card)

        editor_header = QHBoxLayout()
        editor_title = QLabel("✏️  Script Editor")
        editor_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #555;")
        editor_header.addWidget(editor_title)
        editor_header.addStretch()

        # Templates menu
        self.template_menu = QMenu()
        for agent in AGENTS:
            act = QAction(agent["name"], self)
            act.triggered.connect(lambda _, a=agent: self._load_template(a["code"]))
            self.template_menu.addAction(act)
        template_btn = QPushButton("📂 Templates")
        template_btn.setMenu(self.template_menu)
        editor_header.addWidget(template_btn)

        # API Reference button
        self.api_ref_btn = QPushButton("ℹ️ API")
        self.api_ref_btn.clicked.connect(self._show_api_ref)
        editor_header.addWidget(self.api_ref_btn)
        editor_layout.addLayout(editor_header)

        # Syntax-highlighted editor
        self.manual_editor = QPlainTextEdit()
        self.manual_editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.manual_editor.setStyleSheet("""
            QPlainTextEdit { border: 1px solid #e0e0e0; border-radius: 4px; padding: 6px; }
        """)
        self.highlighter = PythonSyntaxHighlighter(self.manual_editor.document())
        self.manual_editor.textChanged.connect(self._on_manual_code_changed)
        editor_layout.addWidget(self.manual_editor)
        layout.addWidget(editor_card, stretch=1)

        # Action buttons
        actions = QHBoxLayout()
        self.manual_validate_btn = QPushButton("✓  Validate")
        self.manual_validate_btn.clicked.connect(self._validate_manual)
        actions.addWidget(self.manual_validate_btn)
        actions.addStretch()

        self.manual_deploy_btn = QPushButton("🚀  Deploy to Launcher")
        self.manual_deploy_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #ff9800; color: white; "
                                              "border: none; border-radius: 4px; font-weight: bold; }")
        self.manual_deploy_btn.clicked.connect(self._deploy_manual)
        actions.addWidget(self.manual_deploy_btn)

        self.manual_wrapper_btn = QPushButton("🔗  Deploy w/ Wrapper")
        self.manual_wrapper_btn.setStyleSheet("QPushButton { padding: 8px 16px; background: #7b1fa2; color: white; "
                                               "border: none; border-radius: 4px; font-weight: bold; }")
        self.manual_wrapper_btn.clicked.connect(self._deploy_manual_wrapper)
        actions.addWidget(self.manual_wrapper_btn)
        layout.addLayout(actions)

        return widget

    def _toggle_guide(self):
        self.guide_visible = not self.guide_visible
        self.guide_frame.setVisible(self.guide_visible)
        self.show_guide_btn.setVisible(not self.guide_visible)

    def _load_template(self, code: str):
        self.manual_editor.setPlainText(code)

    def _show_api_ref(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("API Reference")
        dlg.resize(350, 500)
        layout = QVBoxLayout(dlg)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        clayout = QVBoxLayout(content)
        clayout.setSpacing(6)

        for section, items in API_REFERENCE.items():
            sec_label = QLabel(section)
            sec_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #555; padding-top: 6px;")
            clayout.addWidget(sec_label)
            for name, desc in items:
                row = QHBoxLayout()
                nl = QLabel(name)
                nl.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
                nl.setStyleSheet("font-size: 11px; color: #333;")
                nl.setFixedWidth(170)
                nl.setAlignment(Qt.AlignmentFlag.AlignRight)
                row.addWidget(nl)
                dl = QLabel(desc)
                dl.setStyleSheet("font-size: 11px; color: #888;")
                row.addWidget(dl)
                clayout.addLayout(row)

        clayout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    def _on_manual_code_changed(self):
        self.manual_code = self.manual_editor.toPlainText()

    def _validate_manual(self):
        code = self.manual_editor.toPlainText()
        self._validate(code)

    def _deploy_manual(self):
        code = self.manual_editor.toPlainText()
        self._deploy(code)

    def _deploy_manual_wrapper(self):
        code = self.manual_editor.toPlainText()
        self._deploy_wrapper(code)

    # ──────── Tab change ────────
    def _on_tab_changed(self, idx: int):
        if idx == 2:  # Manual tab
            if not self.manual_code:
                self.manual_editor.setPlainText(AGENTS[0]["code"])

    # ──────── Shared actions ────────
    def _validate(self, code: str):
        if not code.strip():
            QMessageBox.warning(self, "Validation", "No code to validate.")
            return

        result = validate_code(code)

        dlg = QDialog(self)
        dlg.setWindowTitle("Validation Result")
        dlg.resize(400, 250)
        layout = QVBoxLayout(dlg)

        status_icon = "✅" if result["passed"] else "❌"
        status_lbl = QLabel(f"{status_icon}  {'PASSED' if result['passed'] else 'FAILED'}")
        status_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; "
                                  f"color: {'#2e7d32' if result['passed'] else '#c62828'};")
        layout.addWidget(status_lbl)

        details = QTextEdit()
        details.setReadOnly(True)
        details.setStyleSheet("font-size: 11px;")
        lines = [
            f"✓ Syntax: {'OK' if result['syntax_ok'] else 'FAIL'}",
            f"✓ from api import *: {'OK' if result['has_import'] else 'FAIL'}",
            f"✓ def run(client): {'OK' if result['has_run_func'] else 'FAIL'}",
        ]
        if result["errors"]:
            lines.append("")
            lines.append("Errors:")
            for e in result["errors"]:
                lines.append(f"  • {e}")
        details.setPlainText("\n".join(lines))
        layout.addWidget(details)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec()

    def _deploy(self, code: str):
        if not code.strip():
            QMessageBox.warning(self, "Deploy", "No code to deploy.")
            return

        if not LAUNCHER_DIR.is_dir():
            QMessageBox.warning(
                self, "Launcher Not Found",
                f"Launcher directory not found at:\n{LAUNCHER_DIR}\n\n"
                "Please make sure Launcher for Challenge 2026 is installed.",
            )
            return

        err = deploy_as_default(code)
        if err:
            self.toast(f"❌ {err}", is_error=True)
            QMessageBox.critical(self, "Deploy Failed", err)
        else:
            self.toast("✅ Deployed as default agent! Launching Launcher...", is_error=False)
            self._launch()

    def _deploy_wrapper(self, code: str):
        if not code.strip():
            QMessageBox.warning(self, "Deploy", "No code to deploy.")
            return

        if not LAUNCHER_DIR.is_dir():
            QMessageBox.warning(
                self, "Launcher Not Found",
                f"Launcher directory not found at:\n{LAUNCHER_DIR}\n\n"
                "Please make sure Launcher for Challenge 2026 is installed.",
            )
            return

        err = deploy_with_wrapper(code)
        if err:
            self.toast(f"❌ {err}", is_error=True)
            QMessageBox.critical(self, "Deploy Failed", err)
        else:
            self.toast("✅ Wrapper deployed! Launching Launcher...", is_error=False)
            self._launch()

    def _launch(self):
        try:
            launch_launcher()
        except Exception as e:
            self.toast(f"⚠️  Deployed but launch failed: {e}", is_error=True)


# ══════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Agent Generator")
    app.setOrganizationName("Challenge2026")

    # Set app icon (attempt to load)
    icon_path = Path(__file__).parent / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = AgentGeneratorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
