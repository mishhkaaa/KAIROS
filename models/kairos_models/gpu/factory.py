"""Factory for P4's ResourceProbe. kairosd calls it when KAIROS_MODE_PROBE=real."""
from kairos_contracts.interfaces import ResourceProbe
from kairos_contracts.wiring import ServiceBundle, Settings

from .probe import HostProbe


def build_resource_probe(settings: Settings, services: ServiceBundle) -> ResourceProbe:
    return HostProbe()
