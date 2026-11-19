"""Tester för repovakten.ui.theme – paletter, QSS, typsnitt och fönsterstorlek."""
from __future__ import annotations

import pytest

from repovakten.errors import StoreError
from repovakten.store import Store
from repovakten.ui.theme import (
    DEFAULT_THEME,
    FONTS,
    PALETTES,
    THEMES,
    build_stylesheet,
    default_window_size,
    font_families,
)


# --------------------------------------------------------------- paletter

def test_bada_paletterna_har_samma_nycklar():
    dark, light = PALETTES["dark"], PALETTES["light"]
    assert set(dark) == set(light)
    for name, value in dark.items():
        assert value.startswith("#"), name


def test_stylesheet_innehaller_viktiga_delar():
    sheet = build_stylesheet("dark")
    for selector in (
        "QMainWindow",
        "QPushButton#primary",
        "QLineEdit",
        "QTableWidget",
        "QHeaderView::section",
        "QMenuBar",
        "QMenu",
        "QScrollBar:vertical",
        "QToolTip",
        "QLabel#statusLabel",
    ):
        assert selector in sheet, selector
    assert PALETTES["dark"]["accent"] in sheet  # accentfärgen används


def test_ljust_tema_egen_farg():
    dark = build_stylesheet("dark")
    light = build_stylesheet("light")
    assert PALETTES["light"]["window_bg"] in light
    assert PALETTES["light"]["window_bg"] not in dark


def test_okant_tema_felar():
    with pytest.raises(ValueError):
        build_stylesheet("blått")
    assert DEFAULT_THEME in THEMES


# --------------------------------------------------------------- typsnitt

def test_typsnittskedjor_per_os():
    assert font_families("windows")[0] == "Segoe UI"
    assert font_families("macos")[0] == "SF Pro Text"
    assert font_families("linux")[0] == "Inter"
    assert font_families("plan9") == FONTS["linux"]  # okänd plattform


def test_typsnittskedjor_slutar_i_sans_serif():
    for platform in FONTS:
        assert font_families(platform)[-1] == "sans-serif"


# --------------------------------------------------------------- fönster

@pytest.mark.parametrize(
    "skarm, forvantat",
    [
        ((2560, 1440), (1600, 1000)),  # stor skärm – rimlig maxstorlek
        ((1920, 1080), (1440, 810)),  # vanlig skärm – 75 %
        ((3840, 2160), (1600, 1000)),  # 4K – inte helskärm
        ((1024, 600), (800, 520)),  # liten – minimum, får plats
        ((800, 480), (760, 420)),  # mycket litet – aldrig större än skärmen
    ],
)
def test_fonsterstorlek_foljer_skarmen(skarm, forvantat):
    assert default_window_size(*skarm) == forvantat


# --------------------------------------------------------------- inställningar

def test_tema_sparas_i_store(tmp_path):
    store = Store(tmp_path / "state.json")
    assert store.get_theme() == "dark"  # standard
    store.set_theme("light")
    assert store.get_theme() == "light"
    assert Store(tmp_path / "state.json").get_theme() == "light"
    with pytest.raises(StoreError):
        store.set_theme("blått")


def test_fonstergeometri_sparas_i_store(tmp_path):
    store = Store(tmp_path / "state.json")
    assert store.get_window_geometry() is None
    store.set_window_geometry([10, 20, 1200, 800])
    assert store.get_window_geometry() == [10, 20, 1200, 800]
    assert Store(tmp_path / "state.json").get_window_geometry() == [10, 20, 1200, 800]
    store.set_window_geometry(None)
    assert store.get_window_geometry() is None
    with pytest.raises(StoreError):
        store.set_window_geometry([1, 2, 3])  # fel antal värden
