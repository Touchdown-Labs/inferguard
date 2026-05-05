"""External engine validation entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def validate_external(
    endpoint_url: str,
    *,
    engine: str,
    output_dir: str | Path,
    model_path: str | None = None,
    **flags: Any,
) -> Any:
    from inferguard.launch_engine import launch

    return launch(
        engine=engine,
        output_dir=output_dir,
        external_launch=True,
        endpoint_url=endpoint_url,
        model_path=model_path,
        **flags,
    )


def external_process_info(endpoint_url: str) -> dict[str, Any]:
    return {"endpoint": endpoint_url, "pid": None, "source": "not_available"}
