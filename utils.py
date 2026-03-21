from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_signal_history(history: list[dict[str, Any]], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in history:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")
