"""KAIROS shared contracts: schemas, service interfaces, fakes, contract tests and the gateway API spec.

Bump CONTRACT_VERSION on every change that can break another work split (see shared/README.md).
"""
# 0.13.0 joins two lines that both counted from 0.9.0: identity, connectors, mounts and sign-in codes (A/C, 0.10-0.11)
# with thought-process events, dynamic agents and the db tool (B, 0.10-0.12).
CONTRACT_VERSION = "0.13.0"
