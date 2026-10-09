"""Contract test for P4's ResourceProbe. SKIPs until implemented."""
import pytest
from kairos_contracts.testing import contracts as c
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_models.gpu import factory


class TestProbe(c.ResourceProbeContract):
    def make(self):
        s = Settings()
        try:
            return factory.build_resource_probe(s, ServiceBundle(settings=s))
        except NotImplementedError as e:
            pytest.skip(f"not implemented yet: {e}")
