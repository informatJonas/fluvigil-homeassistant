"""Puts the integration into a throwaway Home Assistant instance.

The Home Assistant test plugin loads itself and blocks sockets for every test in its run,
which is why the client tests — whose point is talking to a real server — live in
`tests/client` and run separately.
"""

import shutil
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parents[2] / "custom_components"


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """A writable directory per test; the default one is meant to be shared."""
    return hass_tmp_config_dir


@pytest.fixture(autouse=True)
def install_integration(hass):
    """Puts the integration where Home Assistant looks for custom ones.

    Discovery reads the instance's own config directory, which in a test is a throwaway
    folder — copying it there is what makes the loader find it at all.
    """
    shutil.copytree(
        _SOURCE, Path(hass.config.config_dir) / "custom_components", dirs_exist_ok=True
    )
    hass.data.pop("custom_components", None)
