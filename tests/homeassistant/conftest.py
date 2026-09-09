"""Loads the Home Assistant test plugin for this half of the suite only.

It blocks sockets for every test in its run, which is why the client tests — whose point is
talking to a real server — live in `tests/client` and run separately.
"""

pytest_plugins = "pytest_homeassistant_custom_component"
