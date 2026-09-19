"""Entry point for running from source and for the PyInstaller build."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from pwr_gui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
