from __future__ import annotations

from typing import Any

from .constants import DISK_HEALTH_PREFIX, DISK_IO_PREFIX, DISK_USAGE_PREFIX, METRIC_SPEC_BY_ID


def _fallback_label(metric_id: str) -> str:
    spec = METRIC_SPEC_BY_ID.get(metric_id)
    if spec is not None:
        return spec.label
    if "|" in metric_id:
        _prefix, suffix = metric_id.split("|", 1)
        return suffix or "Metric"
    return metric_id.replace("_", " ").strip() or "Metric"


def _dynamic_children(parent_metric: str, snapshot: dict[str, dict[str, Any]]) -> list[str]:
    prefix = {
        "disk_usage_all": DISK_USAGE_PREFIX,
        "disk_io_all": DISK_IO_PREFIX,
        "disk_health": DISK_HEALTH_PREFIX,
    }.get(parent_metric)
    if prefix is None:
        return []

    children = [metric_id for metric_id in snapshot if metric_id.startswith(prefix)]
    children.sort(
        key=lambda metric_id: (
            str(snapshot.get(metric_id, {}).get("sort_key") or "").casefold(),
            str(snapshot.get(metric_id, {}).get("label") or metric_id).casefold(),
            metric_id.casefold(),
        )
    )
    return children


def expand_metric_ids(
    selected_metrics: list[str] | tuple[str, ...],
    snapshot: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Replace expandable parent metrics with their current dynamic children."""
    data = snapshot or {}
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_metric_id in selected_metrics:
        metric_id = str(raw_metric_id)
        children = _dynamic_children(metric_id, data)
        candidates = children or [metric_id]
        for candidate in candidates:
            if candidate and candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return expanded


def metric_display_label(
    metric_id: str,
    snapshot: dict[str, dict[str, Any]] | None = None,
) -> str:
    reading = (snapshot or {}).get(metric_id, {})
    label = str(reading.get("label") or "").strip()
    return label or _fallback_label(metric_id)
