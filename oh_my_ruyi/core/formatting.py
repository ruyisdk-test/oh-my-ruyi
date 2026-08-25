"""Small formatting helpers shared by service and presentation modules."""

from __future__ import annotations


DEFAULT_BYTE_UNITS = ("B", "KiB", "MiB", "GiB")
STORAGE_BYTE_UNITS = (*DEFAULT_BYTE_UNITS, "TiB", "PiB")


def format_bytes(
    size: int,
    *,
    units: tuple[str, ...] = DEFAULT_BYTE_UNITS,
) -> str:
    """Format a byte count using binary units and one decimal when scaled."""
    if not units or units[0] != "B":
        raise ValueError("byte units must start with B")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


__all__ = ["DEFAULT_BYTE_UNITS", "STORAGE_BYTE_UNITS", "format_bytes"]
