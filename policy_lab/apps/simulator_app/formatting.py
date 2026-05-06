from __future__ import annotations


def format_optional_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def format_optional_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"R$ {value:,.2f}"


def format_optional_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def format_by_kind(value: float | None, kind: str) -> str:
    if kind == "pct":
        return format_optional_pct(value)
    if kind == "money":
        return format_optional_money(value)
    return format_optional_number(value)


def format_delta_by_kind(
    baseline: float | None,
    candidate: float | None,
    kind: str,
) -> str:
    if baseline is None or candidate is None:
        return "N/A"
    delta = candidate - baseline
    if kind == "pct":
        return f"{delta * 100:+.2f}pp"
    if kind == "money":
        return f"{delta:+,.2f}"
    return f"{delta:+.2f}"


def delta_text(value: float, baseline: float, *, scale: float = 100.0) -> str:
    delta = (value - baseline) * scale
    prefix = "+" if delta >= 0 else ""
    suffix = "pp" if scale == 100.0 else ""
    return f"{prefix}{delta:.2f}{suffix}"


def delta_text_optional(
    value: float | None,
    baseline: float | None,
    *,
    scale: float = 100.0,
) -> str:
    if value is None or baseline is None:
        return ""
    delta = (value - baseline) * scale
    prefix = "+" if delta >= 0 else ""
    suffix = "pp" if scale == 100.0 else ""
    return f"{prefix}{delta:.2f}{suffix}"
