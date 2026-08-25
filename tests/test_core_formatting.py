from __future__ import annotations

import pytest

from oh_my_ruyi.core.formatting import STORAGE_BYTE_UNITS, format_bytes


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 B"),
        (1024, "1.0 KiB"),
        (1024**2, "1.0 MiB"),
        (1024**4, "1.0 TiB"),
    ],
)
def test_format_bytes_uses_binary_units(size: int, expected: str) -> None:
    assert format_bytes(size, units=STORAGE_BYTE_UNITS) == expected


def test_format_bytes_rejects_units_without_bytes() -> None:
    with pytest.raises(ValueError, match="start with B"):
        format_bytes(1, units=("KiB",))
