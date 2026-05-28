"""Entry point: python gologin_ui/run.py — mở GUI manager."""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for p in (_PARENT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from gologin_ui.gologin_manager import main

if __name__ == "__main__":
    main()
