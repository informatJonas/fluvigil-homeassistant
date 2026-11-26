"""Loads the Home Assistant test plugin for this half of the suite only.

It blocks sockets for every test in its run, which is why the client tests — whose point is
talking to a real server — live in `tests/client` and run separately.
"""

import shutil
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

_SOURCE = Path(__file__).resolve().parents[2] / "custom_components"


@pytest.fixture(autouse=True)
def install_integration(hass, enable_custom_integrations):
    """Puts the integration where Home Assistant looks for custom ones.

    Discovery reads the instance's own config directory, which in a test is a throwaway
    folder — copying it there is what makes the loader find it at all.
    """
    shutil.copytree(
        _SOURCE, Path(hass.config.config_dir) / "custom_components", dirs_exist_ok=True
    )
    hass.data.pop("custom_components", None)

    return enable_custom_integrations
