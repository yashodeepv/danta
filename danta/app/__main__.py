"""danta studio [--port 8765] [--no-browser]

Starts Spec Studio locally and opens it in the browser.
"""

import argparse

from danta.app.server import serve

if __name__ == '__main__':
    ap = argparse.ArgumentParser(prog='danta studio', description=__doc__)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    serve(a.port, not a.no_browser)
