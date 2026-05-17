from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cerber_launcher.cli import main


if __name__ == "__main__":
    print("GUI launcher удалён. Используйте CLI: python launcher.py --help", file=sys.stderr)
    raise SystemExit(main())