"""Entry point used by the desktop shortcut (running under pythonw.exe, no console).

The shortcut points here, so dropping an image onto it passes the path as an
argument and the image opens right away.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from imagenotes.app import main  # noqa: E402  (import after sys.path is set up)

if __name__ == "__main__":
    raise SystemExit(main())
