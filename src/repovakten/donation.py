"""Donationsuppgifter och Qt-fri logik för donator-dialogen.

Samma principer som stod.html (Mitt Maskinkök):

* Swish-QR enligt Swish officiella C-format:
  ``C<nummer>;<belopp>;<meddelande>;<mask>`` där mask 6 betyder att
  belopp och meddelande kan ändras i appen men numret är låst.
* Swish-numret visas aldrig i klartext i gränssnittet – bara QR-koden
  innehåller det. Numret läses ur Tokke2/recept ``json/donation.json``.
* PayPal-länken får med beloppet (``paypal.me/…/<belopp>SEK``).
* Ko-fi för engångs- eller månadsstöd med valfritt belopp.

Modulen är Qt-fri så att den kan testas utan skärm; QR-matrisen ritas
till en QPixmap av :mod:`repovakten.ui.donation_dialog`.
"""
from __future__ import annotations

from urllib.parse import quote

from .errors import RepovaktenError

# ---------------------------------------------------------------- konton
# Källa: Tokke2/recept json/donation.json (publik) + stod.html.
SWISH_NUMBER = "0721817177"  # visas aldrig i klartext – bara i QR-koden
PAYPAL_ME = "https://paypal.me/Rickard3dPrint"
KOFI_URL = "https://ko-fi.com/tokke2"

# ---------------------------------------------------------------- Swish
SWISH_MESSAGE = "Repovakten"
# Mask 6 = belopp + meddelande ändringsbara, numret låst (Swish C-format).
SWISH_MASK = "6"

# ---------------------------------------------------------------- belopp
DEFAULT_AMOUNT = 50
PRESET_AMOUNTS = (25, 50, 100, 200)
MAX_AMOUNT = 99_999


def normalize_amount(value: object) -> int:
    """Validera ett belopp och returnera det som ett heltal (1..MAX_AMOUNT kr)."""
    if isinstance(value, bool):
        raise ValueError("Beloppet måste vara ett heltal.")
    if isinstance(value, int):
        kr = value
    elif isinstance(value, str) and value.strip().isdigit():
        kr = int(value.strip())
    else:
        raise ValueError(f"Ogiltigt belopp: {value!r}")
    if not 1 <= kr <= MAX_AMOUNT:
        raise ValueError(f"Beloppet måste vara mellan 1 och {MAX_AMOUNT} kr.")
    return kr


def swish_qr_payload(amount: int) -> str:
    """Returnera Swish-QR:ens innehåll i officiella C-formatet."""
    kr = normalize_amount(amount)
    message = quote(SWISH_MESSAGE, safe="")
    return f"C{SWISH_NUMBER};{kr};{message};{SWISH_MASK}"


def paypal_url(amount: int | None = None) -> str:
    """paypal.me-länk – med beloppet förifyllt om det anges."""
    if amount is None:
        return PAYPAL_ME
    return f"{PAYPAL_ME}/{normalize_amount(amount)}SEK"


def qr_matrix(amount: int) -> list[list[int]]:
    """Returnera QR-matrisen (1 = mörk modul) för Swish-betalningen.

    Kräver det lilla paketet ``segno`` (inga beroenden); om det saknas
    lyfts :class:`RepovaktenError` med ett användbart felmeddelande.
    """
    payload = swish_qr_payload(amount)
    try:
        import segno
    except ImportError as exc:  # pragma: no cover – beror på installationen
        raise RepovaktenError(
            "QR-koden kunde inte ritas: Python-paketet 'segno' saknas. "
            "Installera det med: pip install segno"
        ) from exc
    code = segno.make(payload, error="m")
    return [[1 if cell else 0 for cell in row] for row in code.matrix]
