"""Import all integration modules against the installed Home Assistant release."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for path in sorted(Path("custom_components/central_heating").rglob("*.py")):
    parts = path.with_suffix("").parts
    module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
    importlib.import_module(module)
    print(module)
