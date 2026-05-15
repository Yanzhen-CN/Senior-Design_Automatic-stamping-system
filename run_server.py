from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Missing dependencies. Run: conda env create -f environment.yml"
        ) from exc

    uvicorn.run(
        "stamping_system.api:app",
        host=os.environ.get("STAMPING_HOST", "127.0.0.1"),
        port=int(os.environ.get("STAMPING_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
