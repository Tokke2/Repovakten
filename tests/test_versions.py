"""Tester för repovakten.versions."""
from __future__ import annotations

import pytest

from repovakten.versions import (
    is_newer,
    newest_tag,
    parse_version,
    stable_sort_key,
    try_version_key,
    version_key,
)
from repovakten.errors import VersionParseError


def test_v_prefix_ignoreras():
    assert version_key("v1.2.0") == version_key("1.2.0")
    assert version_key("V2.0.0") == version_key("v2.0.0")


def test_tackning_av_saknade_delar():
    assert version_key("1.2") == version_key("1.2.0")
    assert version_key("1") == version_key("1.0.0")


def test_numerisk_ordning():
    assert version_key("1.10.0") > version_key("1.9.0")
    assert version_key("2.0.0") > version_key("1.99.99")


def test_stabil_sorteras_efter_prerelease():
    assert version_key("1.2.0") > version_key("1.2.0-rc.1")
    assert version_key("1.2.0-rc.2") > version_key("1.2.0-rc.1")
    assert version_key("1.2.0-rc.10") > version_key("1.2.0-rc.2")  # numeriskt, inte lexikografiskt


def test_numerisk_prerelease_fore_alfanumerisk():
    assert version_key("1.0.0-1") < version_key("1.0.0-alpha")
    assert version_key("1.0.0-alpha") < version_key("1.0.0-beta")


def test_byggmetadata_ignoreras():
    assert version_key("1.2.0+byggnad.5") == version_key("1.2.0")


def test_eftersta_led_med_bokstaver():
    # "1.2rc1" tolkas som 1.2 pre-release "rc1"
    parsed = parse_version("1.2rc1")
    assert parsed.numbers == (1, 2)
    assert parsed.prerelease == ("rc1",)


def test_ogiltiga_taggavrivs():
    for tag in ["", "  ", "x", "1.x.2", "a.b.c", "1..2", "-1.2.0", "1.2-"]:
        with pytest.raises(VersionParseError):
            parse_version(tag)


def test_try_version_key_kraschar_aldrig():
    assert try_version_key("helt-konstigt") is None
    assert try_version_key(None) is None
    assert try_version_key("1.2.3") is not None


def test_stable_sort_key_blandad_lista():
    taggar = ["konstigt", "v1.0.0", "v1.2.0", "v1.1.0"]
    sorterade = sorted(taggar, key=stable_sort_key)
    assert sorterade == ["konstigt", "v1.0.0", "v1.1.0", "v1.2.0"]


def test_newest_tag():
    assert newest_tag(["v1.0.0", "v2.0.0", "v1.5.0"]) == "v2.0.0"
    assert newest_tag([]) is None


def test_is_newer():
    assert is_newer("v1.3.0", "v1.2.0")
    assert not is_newer("v1.2.0", "v1.2.0")
    assert not is_newer("v1.2.0-rc.1", "v1.2.0")
