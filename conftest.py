"""Workspace-wide test setup: the planner's Jev router is a local model that downloads weights and takes seconds per
call, so tests use the rules. A test that wants the router sets KAIROS_JEV itself."""
import os

os.environ.setdefault("KAIROS_JEV", "off")
