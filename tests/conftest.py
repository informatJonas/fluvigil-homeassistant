"""Makes the API client importable without a Home Assistant install.

`api.py` and `const.py` import nothing from Home Assistant — that separation is deliberate,
because it keeps the part that talks to the network testable on its own. Importing them the
ordinary way would still execute the package's `__init__.py`, which does pull Home Assistant
in, so the package is registered here by hand: relative imports inside it keep working, and
`__init__.py` never runs.

The coordinator, config flow and sensor are intentionally not covered here. They are thin
wrappers over Home Assistant machinery, and testing them means installing the framework —
a cost worth paying when the integration is submitted upstream, not for a first gauge.
"""

import sys
import types
from pathlib import Path

_INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "fluvigil"

_package = types.ModuleType("fluvigil")
_package.__path__ = [str(_INTEGRATION_ROOT)]
sys.modules.setdefault("fluvigil", _package)
