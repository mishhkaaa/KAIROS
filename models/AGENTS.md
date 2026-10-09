# models/ — owner P3, EXCEPT `kairos_models/gpu/` + `tests/test_probe_contract.py` (ResourceProbe, owner P4)
- P3: providers (Ollama first), PolicyRouter, embeddings (ONE fixed model per deployment), models.yaml. Brief: shared/services/P3-agents-models.md
- Hard rule: privacy=restricted ⇒ local model or KairosError("MODEL_UNAVAILABLE").
- P4: host resource probe (psutil + nvidia-smi). Brief: shared/services/P4-platform-data-demo.md
