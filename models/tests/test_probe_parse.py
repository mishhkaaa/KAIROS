"""P4 unit tests for the nvidia-smi parser (the contract suite covers snapshot())."""
from kairos_models.gpu.probe import parse_nvidia_smi


def test_parses_normal_line():
    g = parse_nvidia_smi("NVIDIA GeForce RTX 5070 Laptop GPU, 37, 5120, 8151")
    assert g is not None and g.name.endswith("Laptop GPU")
    assert g.utilization == 0.37 and g.memory_used_mb == 5120 and g.memory_total_mb == 8151


def test_na_utilization_is_zero():
    g = parse_nvidia_smi("NVIDIA GeForce RTX 5070, [N/A], 100, 8151")
    assert g is not None and g.utilization == 0.0


def test_garbage_is_none():
    assert parse_nvidia_smi("") is None
    assert parse_nvidia_smi("No devices were found") is None
    assert parse_nvidia_smi("x, y, z, w") is None
