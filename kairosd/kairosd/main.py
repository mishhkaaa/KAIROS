"""kairosd — the KAIROS server process (systemd unit: infra/systemd/kairosd.service).

    uv run kairosd                         # everything fake -> runs today
    KAIROS_DEFAULT_MODE=real uv run kairosd
    KAIROS_MODE_KNOWLEDGE=real uv run kairosd   # integrate one component at a time
    uv run kairosd --print-wiring          # show which implementation backs each service
"""
from __future__ import annotations

import argparse
import logging

from kairos_contracts.wiring import Settings

from .wiring import build_app, build_services


def main() -> None:
    ap = argparse.ArgumentParser(prog="kairosd")
    ap.add_argument("--print-wiring", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = Settings.from_env()
    bundle = build_services(settings)
    width = max(len(k) for k in bundle.modes)
    for attr, mode in bundle.modes.items():
        print(f"  {attr:<{width}}  {mode:<15} {type(getattr(bundle, attr)).__module__}.{type(getattr(bundle, attr)).__name__}")
    if args.print_wiring:
        return

    import uvicorn

    uvicorn.run(build_app(bundle), host=settings.gateway_host, port=settings.gateway_port)


if __name__ == "__main__":
    main()
