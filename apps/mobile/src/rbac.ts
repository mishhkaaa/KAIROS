// What each role may do, mirroring policies/rbac/roles.yaml (idea from Manjunath's d/settings). The gateway is the
// authority and /auth/me's explicit permission list always wins; this only fills in when a server sends a role
// without permissions, so the app still hides buttons the role could not use.
export const ROLE_PERMISSIONS: Record<string, string[]> = {
  viewer: ["knowledge.read"],
  member: ["task.create", "knowledge.read"],
  approver: ["task.create", "knowledge.read", "approval.resolve"],
  admin: ["task.create", "task.cancel", "approval.resolve", "knowledge.read", "knowledge.ingest", "connectors.manage", "config.read", "members.manage"],
  owner: [
    "task.create",
    "task.cancel",
    "approval.resolve",
    "knowledge.read",
    "knowledge.ingest",
    "connectors.manage",
    "config.read",
    "config.manage",
    "members.manage",
  ],
};

export function permissionsFor(role: string | null | undefined, explicit?: string[] | null): Set<string> {
  if (explicit?.length) return new Set(explicit);
  return new Set(ROLE_PERMISSIONS[role ?? ""] ?? []);
}
