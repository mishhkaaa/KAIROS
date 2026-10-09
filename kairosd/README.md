# kairosd — composition root

The only code that imports implementations. `wiring.py` maps each component to its fake (from `kairos_contracts.testing.fakes`) or its real factory (`<package>/factory.py`), chosen by `KAIROS_MODE_<COMPONENT>=fake|real`. If a real factory still raises `NotImplementedError`, it falls back to the fake with a warning.

```bash
uv run kairosd --print-wiring                      # which implementation backs each service
KAIROS_MODE_KNOWLEDGE=real uv run kairosd          # integrate one component at a time
KAIROS_DEFAULT_MODE=real uv run kairosd            # everything real
```
Maintained by P1. Registering a new factory is a one-line change in `REGISTRY`.
