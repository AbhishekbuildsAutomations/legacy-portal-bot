"""Start the fake portal: python -m portal"""

import os

from . import create_app

port = int(os.environ.get("PORTAL_PORT", 5050))
print(f"Fake legacy portal on http://127.0.0.1:{port}  (local only, Ctrl+C to stop)")
create_app().run(host="127.0.0.1", port=port)
