"""Factory contract for P1 — kernel side (see kairos_contracts.wiring). kairosd calls these when KAIROS_MODE_<X>=real."""
from kairos_contracts.interfaces import AuditLog, EventBus, PolicyEngine
from kairos_contracts.wiring import ServiceBundle, Settings


def build_event_bus(settings: Settings, services: ServiceBundle) -> EventBus:
    """In-process bus; mirrored to a Redis Stream when Redis answers (KAIROS_EVENTS_REDIS=off disables)."""
    import logging
    import os

    from .events.bus import KernelEventBus, RedisMirror, redis_reachable

    mirror = None
    if os.getenv("KAIROS_EVENTS_REDIS", "auto").lower() != "off" and redis_reachable(settings.redis_url):
        mirror = RedisMirror(settings.redis_url)
    logging.getLogger("kairos.kernel").info("event bus: %s", "redis-mirrored" if mirror else "in-process only")
    return KernelEventBus(mirror=mirror)


def build_policy_engine(settings: Settings, services: ServiceBundle) -> PolicyEngine:
    from .policy.engine import YamlPolicyEngine

    return YamlPolicyEngine(settings.policies_dir, event_bus=services.event_bus)


def build_audit_log(settings: Settings, services: ServiceBundle) -> AuditLog:
    from .audit.log import SqliteAuditLog

    return SqliteAuditLog(settings.data_dir / "audit.db")


def build_kernel_app(settings: Settings, services: ServiceBundle):
    """The FastAPI gateway with the kernel running on top of `services` (any mix of fake and real)."""
    from .gateway.app import create_app
    from .kernel import Kernel

    return create_app(Kernel(settings, services))
