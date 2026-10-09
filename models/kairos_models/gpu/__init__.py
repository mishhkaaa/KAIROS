"""Host resource probe: CPU / RAM / NVIDIA GPU -> ResourceSnapshot (blueprint §24). Used by P1 for ai-top + scheduler.

Owner: P4 — Platform, Data & Demo
Interface: kairos_contracts.interfaces.ResourceProbe

TODO:
  - [x] probe.py: HostProbe.snapshot() using psutil (cpu_percent(interval=None), virtual_memory())
  - [x] GPU via `nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits`
        run with asyncio.create_subprocess_exec + 1s timeout; cache result for 1s; gpu=None if missing/failing
  - [x] factory.build_resource_probe(); ResourceProbeContract green (models/tests/test_probe_contract.py)
"""
