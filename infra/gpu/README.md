# GPU & model runtime (P4; P3 decides which models)

Target: RTX 5070 Laptop GPU (Blackwell, 8 GB VRAM), 32 GB RAM, Ubuntu 24.04.

## 1. NVIDIA driver (manual, needs reboots)
Blackwell (RTX 50xx) works **only with the open kernel modules, driver ≥ 580**. Proprietary modules do not support it.

1. BIOS: graphics mode **Hybrid / Optimus** (not dGPU-only). Disable Secure Boot, or enroll the MOK key on the first reboot after the install.
2. `sudo ubuntu-drivers list`, then install the newest `-open` package it lists, for example `sudo apt install nvidia-driver-580-open`. Reboot.
3. `nvidia-smi` must show the GPU. If `dmesg | grep -i nvrm` shows `RmInitAdapter failed`, install the next newer `-open` branch (at least one report says `580.159.03-open` fails on 5070 laptops).
4. `sudo prime-select on-demand`: the desktop runs on the iGPU, so all 8 GB of VRAM stay free for models.
5. Run `infra/appliance/install.sh`. It holds the `nvidia-*` packages, because a driver update mid-event breaks NVML (`Driver/library version mismatch`) until a reboot.

## 2. Container toolkit (install.sh does this)
NVIDIA Container Toolkit, then `nvidia-ctk runtime configure --runtime=docker` and restart Docker.
Check: `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
If `nvidia-smi` works on the host but not in a container, run `nvidia-ctk runtime configure` again.

## 3. Ollama
- GPU access comes from the override file:
  ```bash
  docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.gpu.yml up -d ollama
  ```
  CPU-only dev machines use the base file alone.
- Pin `OLLAMA_VERSION` in `/opt/kairos/.env` to the version you verified. RTX 50xx needs a recent release (CUDA 12.8+ builds).
- Pull the models listed in `models/models.yaml` (install.sh does this):
  ```bash
  docker compose -f infra/compose/docker-compose.yml exec -T ollama ollama pull qwen2.5:7b-instruct
  docker compose -f infra/compose/docker-compose.yml exec -T ollama ollama pull nomic-embed-text
  ```
- The embedding model is fixed per deployment. Changing it requires `POST /knowledge/reindex` (tell P2 and P3).

## 4. 8 GB VRAM sizing
The compose settings are `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KEEP_ALIVE=-1`.

| Model | Approx. VRAM |
|---|---|
| qwen2.5:7b-instruct (Q4_K_M) + KV cache for 2 × 8k slots | ~5.5 GB |
| nomic-embed-text | ~0.3 GB |
| llama3.2:3b + KV cache | ~2.5 GB, which does **not** fit alongside the other two |

Recommendation to P3: on this box, route every task class to `qwen2.5:7b-instruct` and skip `qwen2.5-coder:7b` / `llava:7b`. Swapping the 3B in and out costs 2–4 s per swap, which is more than the 3B saves. Verify with `docker compose ... exec ollama ollama ps` during a real run: `PROCESSOR` must say `100% GPU`.
