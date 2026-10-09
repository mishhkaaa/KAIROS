"""HostProbe: CPU / RAM via psutil, NVIDIA GPU via nvidia-smi (stale-while-revalidate, never blocks > 0.4 s)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time

import psutil
from kairos_contracts.schema import GpuStatus, ResourceSnapshot

log = logging.getLogger("kairos.models.gpu.probe")

_QUERY = ["--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
_MAX_AGE_S = 1.0
_FIRST_WAIT_S = 0.4
_SMI_TIMEOUT_S = 2.0


def parse_nvidia_smi(line: str) -> GpuStatus | None:
    parts = [p.strip() for p in line.split(",")]
    if len(parts) != 4:
        return None
    name, util, used, total = parts
    try:
        utilization = 0.0 if util.startswith("[") else min(max(float(util) / 100, 0.0), 1.0)
        used_mb, total_mb = int(float(used)), int(float(total))
    except ValueError:
        return None
    if not name or total_mb <= 0:
        return None
    return GpuStatus(name=name, utilization=utilization, memory_used_mb=min(used_mb, total_mb), memory_total_mb=total_mb)


class HostProbe:
    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)
        self._smi = shutil.which("nvidia-smi")
        self._gpu: GpuStatus | None = None
        self._gpu_ts = 0.0
        self._refresh: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._primed = False

    async def _refresh_gpu(self) -> None:
        assert self._smi is not None
        gpu = None
        try:
            proc = await asyncio.create_subprocess_exec(self._smi, *_QUERY, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=_SMI_TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise
            lines = out.decode(errors="replace").strip().splitlines()
            gpu = parse_nvidia_smi(lines[0]) if proc.returncode == 0 and lines else None
        except (OSError, TimeoutError) as e:
            log.debug("nvidia-smi failed: %s", e)
        self._gpu, self._gpu_ts = gpu, time.monotonic()

    async def _gpu_status(self) -> GpuStatus | None:
        if self._smi is None:
            return None
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            self._loop, self._refresh, self._primed = loop, None, False
        if time.monotonic() - self._gpu_ts > _MAX_AGE_S and (self._refresh is None or self._refresh.done()):
            self._refresh = loop.create_task(self._refresh_gpu())
        if not self._primed and self._refresh is not None:
            self._primed = True
            try:
                await asyncio.wait_for(asyncio.shield(self._refresh), _FIRST_WAIT_S)
            except TimeoutError:
                pass
        return self._gpu

    async def snapshot(self) -> ResourceSnapshot:
        vm = psutil.virtual_memory()
        try:
            gpu = await self._gpu_status()
        except Exception:  # the probe must never raise
            log.exception("gpu probe failed")
            gpu = None
        return ResourceSnapshot(cpu_percent=min(max(psutil.cpu_percent(interval=None), 0.0), 100.0),
                                ram_used_mb=(vm.total - vm.available) // 2**20, ram_total_mb=vm.total // 2**20, gpu=gpu)
