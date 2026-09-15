"""Open the local UI without blocking its HTTP serving loop."""

import sys
import threading
import webbrowser


def open_browser(url):
    def operation():
        try:
            if not webbrowser.open(url, new=2):
                print(
                    "Could not open a browser; open the printed session URL manually.",
                    file=sys.stderr,
                )
        except Exception as error:
            print(
                f"Could not open a browser: {error}. Open the printed session URL manually.",
                file=sys.stderr,
            )

    thread = threading.Thread(target=operation, name="epomaker-browser", daemon=True)
    thread.start()
    return thread
