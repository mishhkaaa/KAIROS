import os

import pytest
from kairos_kernel.testing import kernel_factory

# Never mirror unit-test events into whatever Redis happens to run on localhost; the Redis tests use their own container.
os.environ.setdefault("KAIROS_EVENTS_REDIS", "off")


@pytest.fixture
def make_kernel(tmp_path):
    return kernel_factory(tmp_path)
