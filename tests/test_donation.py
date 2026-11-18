"""Tester för repovakten.donation – donationslänkar och Swish-QR (Qt-fri)."""
from __future__ import annotations

import re

import pytest

from repovakten import donation


def test_swish_numret_ar_tio_siffror():
    assert re.fullmatch(r"\d{10}", donation.SWISH_NUMBER)


def test_swish_payload_c_format():
    """Officiella C-formatet: C<nummer>;<belopp>;<meddelande>;<mask 6>."""
    payload = donation.swish_qr_payload(50)
    assert payload == f"C{donation.SWISH_NUMBER};50;{donation.SWISH_MESSAGE};6"
    assert re.fullmatch(r"C\d{10};\d{1,5};[A-Za-z0-9._~%()-]*;6", payload)


def test_swish_payload_egen_summa():
    assert donation.swish_qr_payload(73).split(";")[1] == "73"


def test_swish_payload_meddelandet_ar_urlkodat():
    falt = donation.swish_qr_payload(50).split(";")
    assert len(falt) == 4
    assert " " not in falt[2]
    assert falt[3] == "6"  # mask 6: belopp+meddelande ändringsbara


def test_paypal_url_med_belopp():
    assert donation.paypal_url(50) == "https://paypal.me/Rickard3dPrint/50SEK"
    assert donation.paypal_url(25) == "https://paypal.me/Rickard3dPrint/25SEK"


def test_paypal_utan_belopp_och_kofi_ar_https():
    assert donation.paypal_url() == donation.PAYPAL_ME
    assert donation.PAYPAL_ME.startswith("https://")
    assert donation.KOFI_URL == "https://ko-fi.com/tokke2"


@pytest.mark.parametrize("bad", [0, -5, 100_000, "abc", 5.5, True, None, "", "12.5"])
def test_normalize_amount_avvisar(bad):
    with pytest.raises(ValueError):
        donation.normalize_amount(bad)


@pytest.mark.parametrize("ok", [1, 25, 99_999, "50", " 200 "])
def test_normalize_amount_godkanner(ok):
    assert isinstance(donation.normalize_amount(ok), int)


def test_presets_inkluderar_defaultbeloppet():
    assert donation.DEFAULT_AMOUNT in donation.PRESET_AMOUNTS


def test_qr_matrix_kvadrat_med_morka_och_ljusa_moduler():
    matrix = donation.qr_matrix(50)
    n = len(matrix)
    assert n == len(matrix[0]) and n >= 21
    assert any(any(row) for row in matrix)  # mörka moduler finns
    assert any(not cell for row in matrix for cell in row)  # ljusa moduler finns


def test_qr_matrix_olika_belopp_ger_olika_qr():
    assert donation.qr_matrix(25) != donation.qr_matrix(200)
