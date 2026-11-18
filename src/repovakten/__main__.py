"""En startpunkt för Repovakten – ``python -m repovakten``.

Samma kommando på Windows, macOS och Linux:

* ``python -m repovakten`` – startar GUI:t.
* ``python -m repovakten --autostart`` – startar minimerat (läget som
  autostartregistreringen använder vid inloggning).
* ``python -m repovakten --enable-autostart`` / ``--disable-autostart`` –
  ställ in eller stäng av att appen startar med datorn.
* ``python -m repovakten --version`` – skriv versionsnumret.

Filen kan också köras direkt (``python repovakten/__main__.py``) – så
fungerar autostartregistreringen från både pip-installation och portabel
ZIP utan miljövariabler.
"""
from __future__ import annotations

import argparse
import sys

if __package__ in (None, ""):
    # Direktkörning av filen: lägg paketets förälder på sökvägen så
    # importerna fungerar oavsett var appen ligger.
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repovakten import __version__  # noqa: E402  (efter sökvägsfixen ovan)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repovakten",
        description="Repovakten – installationshanterare för GitHub-appar.",
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="starta minimerat (används när appen startar med datorn)",
    )
    parser.add_argument(
        "--enable-autostart",
        action="store_true",
        help="starta Repovakten automatiskt vid inloggning",
    )
    parser.add_argument(
        "--disable-autostart",
        action="store_true",
        help="stäng av automatisk start vid inloggning",
    )
    parser.add_argument("--version", action="store_true", help="skriv versionsnumret")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.version:
        print(f"Repovakten {__version__}")
        return 0

    if args.enable_autostart or args.disable_autostart:
        from repovakten import autostart

        try:
            if args.enable_autostart:
                print(autostart.enable())
            else:
                removed = autostart.disable()
                print("Autostart av." if removed else "Autostart var redan av.")
        except Exception as exc:
            print(f"Det gick inte: {exc}", file=sys.stderr)
            return 1
        return 0

    from repovakten.gui import main as gui_main

    return gui_main(start_minimized=args.autostart)


if __name__ == "__main__":
    raise SystemExit(main())
