"""Tema, typografi och fönsterstorlek för Repovakten (Qt-fri logik).

Färgpaletter och QSS-byggaren är rena Python-strängar – testbara utan Qt.
Två teman: ``dark`` (standard) och ``light``. Typsnittet väljs per OS med
en fallback-kedja, och fönsterstorleken utnyttjar skärmbredden utan att
bliva större än skärmen.
"""
from __future__ import annotations

from string import Template

DEFAULT_THEME = "dark"
THEMES = ("dark", "light")

# Färgnycklar – samma uppsättning i båda paletterna.
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "window_bg": "#1c1e24",
        "panel_bg": "#24262d",
        "input_bg": "#2b2e36",
        "alt_row": "#212329",
        "text": "#e6e8ec",
        "text_dim": "#9aa1ab",
        "border": "#3a3e48",
        "accent": "#4c8dff",
        "accent_hover": "#6ba0ff",
        "accent_press": "#3b74e0",
        "accent_text": "#ffffff",
        "selection": "#2f4d80",
        "danger": "#f85149",
        "success": "#3fb950",
        "warning": "#d29922",
        "menu_hover": "#2f323b",
        "scroll_thumb": "#4a4f5a",
    },
    "light": {
        "window_bg": "#f4f5f7",
        "panel_bg": "#ffffff",
        "input_bg": "#ffffff",
        "alt_row": "#f6f8fa",
        "text": "#1f2328",
        "text_dim": "#6a737d",
        "border": "#d7dce3",
        "accent": "#2f6feb",
        "accent_hover": "#4c8dff",
        "accent_press": "#2558c7",
        "accent_text": "#ffffff",
        "selection": "#d6e4ff",
        "danger": "#c93c37",
        "success": "#2da44e",
        "warning": "#b8860b",
        "menu_hover": "#e8ebf0",
        "scroll_thumb": "#c1c7d0",
    },
}

# Typsnittskedjor per OS – Qt faller vidare på nästa i listan.
FONTS: dict[str, list[str]] = {
    "windows": ["Segoe UI", "Tahoma", "sans-serif"],
    "macos": ["SF Pro Text", "Helvetica Neue", "Lucida Grande", "sans-serif"],
    "linux": ["Inter", "Ubuntu", "Cantarell", "Noto Sans", "sans-serif"],
}


def font_families(platform: str) -> list[str]:
    """Typsnittskedjan för plattformen (fallback till Linux-listan)."""
    return list(FONTS.get(platform, FONTS["linux"]))


def default_window_size(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Fönsterstorlek som utnyttjar skärmbredden utan att överstiga skärmen."""
    width = min(max(800, int(screen_w * 0.75)), 1600, screen_w - 40)
    height = min(max(520, int(screen_h * 0.75)), 1000, screen_h - 60)
    return width, height


_SHEET = Template("""
/* ---------- grund ---------- */
QMainWindow, QDialog {
    background-color: $window_bg;
}
QWidget {
    color: $text;
    font-size: 10pt;
}
QLabel { background: transparent; }
QLabel#statusLabel {
    background-color: $panel_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px 12px;
    color: $text_dim;
}

/* ---------- knappar ---------- */
QPushButton {
    background-color: $panel_bg;
    border: 1px solid $border;
    border-radius: 7px;
    padding: 6px 14px;
    min-height: 20px;
}
QPushButton:hover { background-color: $menu_hover; border-color: $scroll_thumb; }
QPushButton:pressed { background-color: $input_bg; }
QPushButton:disabled { color: $text_dim; background-color: $window_bg; }
QPushButton:focus { border-color: $accent; }
QPushButton#primary {
    background-color: $accent;
    border-color: $accent;
    color: $accent_text;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:pressed { background-color: $accent_press; }

/* ---------- fält ---------- */
QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: $selection;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: $accent;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: $panel_bg;
    border: 1px solid $border;
    selection-background-color: $selection;
    selection-color: $text;
    outline: none;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }

/* ---------- tabell ---------- */
QTableWidget, QTableView {
    background-color: $panel_bg;
    alternate-background-color: $alt_row;
    border: 1px solid $border;
    border-radius: 8px;
    gridline-color: $border;
    selection-background-color: $selection;
    selection-color: $text;
    outline: none;
}
QTableWidget::item, QTableView::item { padding: 6px 8px; border: none; }
QTableWidget::item:selected, QTableView::item:selected {
    background-color: $selection;
    color: $text;
}
QHeaderView::section {
    background-color: $window_bg;
    color: $text_dim;
    border: none;
    border-bottom: 1px solid $border;
    border-right: 1px solid $border;
    padding: 7px 8px;
    font-weight: 600;
}

/* ---------- menyer ---------- */
QMenuBar {
    background-color: $window_bg;
    border-bottom: 1px solid $border;
    padding: 2px 4px;
}
QMenuBar::item { padding: 6px 10px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background-color: $menu_hover; }
QMenu {
    background-color: $panel_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item { padding: 6px 26px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background-color: $menu_hover; }
QMenu::separator { height: 1px; background-color: $border; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; }

/* ---------- rullister ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background-color: $scroll_thumb;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background-color: $text_dim; }
QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background-color: $scroll_thumb;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- dialoger och övrigt ---------- */
QToolTip {
    background-color: $panel_bg;
    color: $text;
    border: 1px solid $border;
    padding: 4px 8px;
}
QMessageBox { background-color: $window_bg; }
QSplitter::handle { background-color: $border; }
""")


def build_stylesheet(theme: str) -> str:
    """Bygg hela QSS-arket för temat (``dark`` eller ``light``)."""
    if theme not in PALETTES:
        raise ValueError(f"Okänt tema: {theme!r} (giltiga: {', '.join(THEMES)})")
    return _SHEET.substitute(PALETTES[theme])
