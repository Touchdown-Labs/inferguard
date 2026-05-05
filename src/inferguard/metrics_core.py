"""Pure Prometheus exposition-format parser.

Zero dependencies beyond the standard library. Two variants:
- ``parse_prometheus_text(text)`` returns ``{name: float}`` (labels discarded).
- ``parse_labeled_prometheus_text(text)`` returns ``list[LabeledSample]`` with
  labels preserved (needed by the disagg adapters for connector detection and
  per-session attribution).

Both variants share the same line-level lexer, so numeric values round-trip
identically between the two forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabeledSample:
    """A single Prometheus sample with its labels preserved."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


def parse_prometheus_text(text: str) -> dict[str, float]:
    """Parse a Prometheus exposition text blob into ``{name: value}``.

    Labels are discarded. If a metric name appears with multiple label sets,
    the last-seen value wins. Histograms expose ``_sum`` and ``_count`` as
    separate samples, which is the shape ``histogram_avg()`` expects.
    """
    metrics: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, value = _split_sample(line)
        if name is None or value is None:
            continue
        metrics[name] = value
    return metrics


def parse_labeled_prometheus_text(text: str) -> list[LabeledSample]:
    """Parse a Prometheus exposition text blob preserving labels.

    Returns one ``LabeledSample`` per data line. HELP/TYPE comment lines are
    ignored. Lines with no numeric value are skipped silently.
    """
    samples: list[LabeledSample] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, labels, value = _split_labeled_sample(line)
        if name is None or value is None:
            continue
        samples.append(LabeledSample(name=name, value=value, labels=labels))
    return samples


def histogram_avg(metrics: dict[str, float], prefix: str) -> float | None:
    """Compute the mean of a histogram from its ``_sum`` and ``_count`` parts."""
    total = metrics.get(f"{prefix}_sum")
    count = metrics.get(f"{prefix}_count")
    if total is None or count is None or count == 0:
        return None
    return total / count


# --- internal helpers -------------------------------------------------------


def _split_sample(line: str) -> tuple[str | None, float | None]:
    """Split a data line into ``(name, value)`` with labels discarded."""
    parts = line.split()
    if len(parts) < 2:
        return None, None
    raw_name = parts[0]
    # Strip any label block (``foo{a="b"}``) off the metric name.
    name = raw_name.split("{", 1)[0]
    try:
        value = float(parts[-1])
    except ValueError:
        return None, None
    return name, value


def _split_labeled_sample(
    line: str,
) -> tuple[str | None, dict[str, str], float | None]:
    """Split a data line into ``(name, labels, value)``.

    Handles three forms:
      ``foo 1.5``
      ``foo{a="b",c="d"} 1.5``
      ``foo{a="b"} 1.5 1700000000000``   (ignores trailing timestamp)
    """
    if "{" in line:
        head, rest = line.split("{", 1)
        name = head.strip()
        close = rest.rfind("}")
        if close == -1:
            return None, {}, None
        labels_raw = rest[:close]
        tail = rest[close + 1 :].strip()
        labels = _parse_label_block(labels_raw)
    else:
        parts = line.split(None, 1)
        if len(parts) < 2:
            return None, {}, None
        name, tail = parts[0], parts[1]
        labels = {}

    value_parts = tail.split()
    if not value_parts:
        return None, labels, None
    try:
        value = float(value_parts[0])
    except ValueError:
        return None, labels, None
    return name, labels, value


def _parse_label_block(raw: str) -> dict[str, str]:
    """Parse a Prometheus label set (contents of the ``{...}`` block)."""
    labels: dict[str, str] = {}
    i = 0
    n = len(raw)
    while i < n:
        # Skip whitespace and separators.
        while i < n and raw[i] in " ,\t":
            i += 1
        if i >= n:
            break
        # Read key up to '='.
        key_start = i
        while i < n and raw[i] != "=":
            i += 1
        if i >= n:
            break
        key = raw[key_start:i].strip()
        i += 1  # skip '='
        # Expect opening quote.
        if i >= n or raw[i] != '"':
            break
        i += 1
        # Read until unescaped closing quote.
        value_chars: list[str] = []
        while i < n:
            c = raw[i]
            if c == "\\" and i + 1 < n:
                nxt = raw[i + 1]
                if nxt == "n":
                    value_chars.append("\n")
                elif nxt == '"':
                    value_chars.append('"')
                elif nxt == "\\":
                    value_chars.append("\\")
                else:
                    value_chars.append(nxt)
                i += 2
                continue
            if c == '"':
                i += 1
                break
            value_chars.append(c)
            i += 1
        if key:
            labels[key] = "".join(value_chars)
    return labels
