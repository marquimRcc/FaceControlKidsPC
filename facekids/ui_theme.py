"""Three accessible parent-panel palettes and isolated Windows-user preference.

The original palette must remain pixel-for-pixel compatible with the
previous panel. Preferences live under the PARENT account's LOCALAPPDATA,
not in the shared child/biometric SQLite database. No Windows authentication,
service configuration or face templates are affected by theme changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

DEFAULT_THEME = "Atual"

THEMES: dict[str, dict[str, str]] = {
    "Atual": {
        "BG_MAIN": "#0F0F17", "BG_HEADER": "#181825", "BG_CARD": "#181825",
        "BG_BOX": "#1E1E2E", "BG_BOX_HOVER": "#252538",
        "BG_FIELD": "#11111B", "BORDER_DEFAULT": "#313244",
        "BORDER_ACCENT": "#38BDF8", "TEXT_TITLE": "#CDD6F4",
        "TEXT_SUB": "#A6ADC8", "TEXT_MUTED": "#6C7086",
        "ACCENT_BLUE": "#38BDF8", "ACCENT_CYAN": "#89DCEB",
        "ACCENT_GREEN": "#A6E3A1", "ACCENT_YELLOW": "#F9E2AF",
        "ACCENT_RED": "#F38BA8", "ACCENT_PURPLE": "#CBA6F7",
        "TEXT_ON_ACCENT": "#0B0B12", "YELLOW_HOVER": "#FFF0BA",
    },
    "Claro": {
        "BG_MAIN": "#F4F7FC", "BG_HEADER": "#FFFFFF", "BG_CARD": "#FFFFFF",
        "BG_BOX": "#E8EFF9", "BG_BOX_HOVER": "#DBE8F8",
        "BG_FIELD": "#FFFFFF", "BORDER_DEFAULT": "#CFD9E8",
        "BORDER_ACCENT": "#2563EB", "TEXT_TITLE": "#172033",
        "TEXT_SUB": "#44546B", "TEXT_MUTED": "#64748B",
        "ACCENT_BLUE": "#1D4ED8", "ACCENT_CYAN": "#0E7490",
        "ACCENT_GREEN": "#166534", "ACCENT_YELLOW": "#92400E",
        "ACCENT_RED": "#B91C1C", "ACCENT_PURPLE": "#6D28D9",
        "TEXT_ON_ACCENT": "#FFFFFF", "YELLOW_HOVER": "#B45309",
    },
    "Escuro": {
        "BG_MAIN": "#101827", "BG_HEADER": "#162236", "BG_CARD": "#1C293D",
        "BG_BOX": "#273750", "BG_BOX_HOVER": "#354864",
        "BG_FIELD": "#0C1525", "BORDER_DEFAULT": "#40526A",
        "BORDER_ACCENT": "#60A5FA", "TEXT_TITLE": "#F1F5F9",
        "TEXT_SUB": "#CDD7E5", "TEXT_MUTED": "#99A9BD",
        "ACCENT_BLUE": "#60A5FA", "ACCENT_CYAN": "#67E8F9",
        "ACCENT_GREEN": "#86EFAC", "ACCENT_YELLOW": "#FDE68A",
        "ACCENT_RED": "#FDA4AF", "ACCENT_PURPLE": "#DDD6FE",
        "TEXT_ON_ACCENT": "#101827", "YELLOW_HOVER": "#FBBF24",
    },
}


def theme_palette(name: str) -> dict[str, str]:
    """Return a defensive copy and reject unknown theme names."""
    if type(name) is not str or name not in THEMES:
        raise ValueError("Tema inválido. Selecione Atual, Claro ou Escuro.")
    return dict(THEMES[name])


def preference_path(*, base: Path | None = None) -> Path:
    """Per-user preference (separate from ProgramData/FaceKids)."""
    if base is None:
        user_data = os.environ.get("LOCALAPPDATA")
        if not user_data:
            # Only for developer/test systems. Never fall back to shared ProgramData.
            user_data = str(Path.home() / ".local" / "share")
        base = Path(user_data)
    return Path(base) / "FaceKids" / "parent-ui-preferences.json"


def load_theme(*, path: Path | None = None) -> str:
    source = Path(path) if path is not None else preference_path()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return DEFAULT_THEME
    if type(data) is not dict or data.get("version") != 1:
        return DEFAULT_THEME
    selected = data.get("theme")
    return selected if type(selected) is str and selected in THEMES else DEFAULT_THEME


def save_theme(name: str, *, path: Path | None = None) -> None:
    theme_palette(name)  # Validate BEFORE filesystem writes.
    destination = Path(path) if path is not None else preference_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(
        prefix=".parent-ui-", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "theme": name}, file, ensure_ascii=False)
            file.write("\n")
        os.replace(staging, destination)
    finally:
        Path(staging).unlink(missing_ok=True)
