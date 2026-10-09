"""Every fake must pass its own contract suite — proves the suites are satisfiable and the fakes honest."""
from kairos_contracts.testing import contracts as c
from kairos_contracts.testing import fakes as f


class TestEventBus(c.EventBusContract):
    def make(self):
        return f.InMemoryEventBus()


class TestPolicy(c.PolicyEngineContract):
    def make(self):
        return f.FakePolicyEngine()


class TestAudit(c.AuditLogContract):
    def make(self):
        return f.InMemoryAuditLog()


class TestKnowledge(c.KnowledgeServiceContract):
    def make(self):
        return f.FakeKnowledgeService(models=f.FakeModelRouter(), firewall=f.FakeContextFirewall())


class TestFirewall(c.ContextFirewallContract):
    def make(self):
        return f.FakeContextFirewall()


class TestMemory(c.MemoryServiceContract):
    def make(self):
        return f.FakeMemoryService()


class TestModels(c.ModelRouterContract):
    def make(self):
        return f.FakeModelRouter()


class TestRegistry(c.AgentRegistryContract):
    def make(self):
        return f.FakeAgentRegistry()


class TestRuntime(c.AgentRuntimeContract):
    def make(self):
        return f.FakeAgentRuntime(), f.FakeAgentRegistry()


class TestArtifacts(c.ArtifactStoreContract):
    def make(self):
        return f.InMemoryArtifactStore()


class TestSandbox(c.SandboxManagerContract):
    def make(self):
        return f.FakeSandboxManager()


class TestTools(c.ToolExecutorContract):
    def make(self):
        return f.FakeToolExecutor()


class TestConverter(c.SourceConverterContract):
    def make(self):
        return f.FakeMarkdownConverter(), str(f.FIXTURE_OKF_DIR / "projects")


class TestBrowser(c.BrowserDriverContract):
    def make(self):
        from kairos_contracts.schema import SandboxInfo, SandboxSpec, SandboxStatus

        sb = SandboxInfo(sandbox_id="SB-1", status=SandboxStatus.RUNNING, spec=SandboxSpec(task_id="T-1", display=True),
                         endpoints={"playwright": "ws://fake"})
        return f.FakeBrowserDriver(), sb, "https://docs.vendor.example/sdk-v5"


class TestProbe(c.ResourceProbeContract):
    def make(self):
        return f.FakeResourceProbe()
