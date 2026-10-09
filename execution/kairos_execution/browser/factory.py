"""Factory for P4's BrowserDriver (see kairos_contracts.wiring). kairosd calls it when KAIROS_MODE_BROWSER=real."""
from kairos_contracts.interfaces import BrowserDriver
from kairos_contracts.wiring import ServiceBundle, Settings

from .driver import PlaywrightDriver


def build_browser_driver(settings: Settings, services: ServiceBundle) -> BrowserDriver:
    return PlaywrightDriver()
