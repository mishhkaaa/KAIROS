"use client";

import type { Member, OrgRole } from "@kairos/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Mail, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { Loading } from "@/components/desktop/orb";
import { PersonAvatar, useSession } from "@/components/session";
import { cn } from "@/lib/utils";
import { AppHeader, button, Card, errText, field, NotAllowed, Pill } from "./kit";

const RANK = ["viewer", "member", "approver", "admin", "owner"];

/** What each permission means, in the words the roles table uses. */
const PERMISSION_LABEL: Record<string, string> = {
  "task.create": "Start tasks",
  "task.cancel": "Stop tasks and processes",
  "approval.resolve": "Approve or reject actions",
  "knowledge.read": "Read /org and results",
  "knowledge.ingest": "Add knowledge, mount folders",
  "connectors.manage": "Connect GitHub, Calendar",
  "config.read": "See system settings",
  "config.manage": "Change system settings",
  "members.manage": "Invite and manage people",
};

function MemberRow({ m, orgId, roles, canManage, myRole, me }: { m: Member; orgId: string; roles: OrgRole[]; canManage: boolean; myRole?: string | null; me?: string }) {
  const client = useClient();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const key = m.user_id || m.email;
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["org-members", orgId] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const setRole = useMutation({
    mutationFn: (role: string) => client.setRole(orgId, key, role),
    onSuccess: (x) => {
      refresh();
      toast.success(`${x.name || x.email} is now ${x.role}`);
    },
    onError: (e) => toast.error("Role not changed", { description: errText(e) }),
  });
  const remove = useMutation({
    mutationFn: () => client.removeMember(orgId, key),
    onSuccess: () => {
      refresh();
      toast.success(`${m.name || m.email} removed`);
    },
    onError: (e) => toast.error("Not removed", { description: errText(e) }),
  });
  // Only an owner can hand out (or take away) ownership.
  const grantable = roles.filter((r) => myRole === "owner" || r.role !== "owner").map((r) => r.role);
  const self = me !== undefined && (m.user_id === me || m.email === me);
  const editable = canManage && !self && (myRole === "owner" || m.role !== "owner");

  return (
    <li className="flex flex-wrap items-center gap-3 px-3 py-2.5">
      <PersonAvatar name={m.name} email={m.email} url={m.avatar_url} size={34} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 truncate text-sm font-medium">
          {m.name || m.email.split("@")[0].replace(/^./, (c) => c.toUpperCase())}
          {self && <Pill tone="brand">you</Pill>}
          {m.status === "invited" && (
            <Pill tone="warn">
              <Mail className="size-3" /> invited
            </Pill>
          )}
        </p>
        <p className="truncate font-mono text-xs text-text-2">{m.email}</p>
      </div>
      {editable ? (
        <select
          value={m.role}
          onChange={(e) => setRole.mutate(e.target.value)}
          disabled={setRole.isPending}
          aria-label={`Role of ${m.email}`}
          className={cn(field, "h-8 w-32 font-mono text-xs")}
        >
          {grantable.includes(m.role) ? null : <option value={m.role}>{m.role}</option>}
          {grantable.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      ) : (
        <Pill mono tone={m.role === "owner" ? "brand" : "neutral"}>{m.role}</Pill>
      )}
      {editable &&
        (confirm ? (
          <span className="flex items-center gap-1">
            <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending} className={cn(button.danger, "h-8")}>
              Remove
            </button>
            <button type="button" onClick={() => setConfirm(false)} className={cn(button.quiet, "h-8")}>
              Keep
            </button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} aria-label={`Remove ${m.email}`} className="rounded-lg p-2 text-text-2 hover:bg-st-failed/10 hover:text-st-failed">
            <Trash2 className="size-4" />
          </button>
        ))}
    </li>
  );
}

function InviteForm({ orgId, roles, myRole }: { orgId: string; roles: OrgRole[]; myRole?: string | null }) {
  const client = useClient();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const invite = useMutation({
    mutationFn: () => client.invite(orgId, { email: email.trim(), role }),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ["org-members", orgId] });
      toast.success(`Invited ${m.email} as ${m.role}`, { description: "They join the moment they sign in with that email." });
      setEmail("");
    },
    onError: (e) => toast.error("Invite not sent", { description: errText(e) }),
  });
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (email.includes("@")) invite.mutate();
      }}
    >
      <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@company.com" aria-label="Email to invite" className={cn(field, "flex-1")} />
      <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" className={cn(field, "w-32 font-mono text-xs")}>
        {roles
          .filter((r) => myRole === "owner" || r.role !== "owner")
          .map((r) => (
            <option key={r.role} value={r.role}>{r.role}</option>
          ))}
      </select>
      <button type="submit" disabled={invite.isPending || !email.includes("@")} className={button.primary}>
        <UserPlus className="size-4" /> Invite
      </button>
    </form>
  );
}

/** Roles down the side, permissions across: what each level of power may do, read from policies/rbac/roles.yaml. */
function RoleMatrix({ roles, myRole }: { roles: OrgRole[]; myRole?: string | null }) {
  const perms = Object.keys(PERMISSION_LABEL).filter((p) => roles.some((r) => r.permissions?.includes(p)));
  const ordered = [...roles].sort((a, b) => RANK.indexOf(b.role) - RANK.indexOf(a.role));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="text-left text-xs text-text-2">
            <th className="pb-2 font-medium">Permission</th>
            {ordered.map((r) => (
              <th key={r.role} className="pb-2 text-center font-mono font-semibold">
                <span className={cn("rounded-md px-1.5 py-0.5", r.role === myRole && "bg-brand text-white")}>{r.role}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {perms.map((p) => (
            <tr key={p}>
              <td className="py-1.5 pr-3">
                <span className="block">{PERMISSION_LABEL[p]}</span>
                <span className="font-mono text-[11px] text-text-2">{p}</span>
              </td>
              {ordered.map((r) => (
                <td key={r.role} className={cn("text-center", r.role === myRole && "bg-brand-subtle/40")}>
                  {r.permissions?.includes(p) ? <Check className="mx-auto size-4 text-st-completed" aria-label="yes" /> : <span className="text-text-2/40" aria-label="no">·</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="mt-3 grid gap-2 @xl:grid-cols-2">
        {ordered.map((r) => (
          <li key={r.role} className="text-xs text-text-2">
            <span className="font-mono font-semibold text-foreground">{r.role}</span> · {r.description}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The organization: who is in it, what each of them may do, and invitations. */
export function OrganizationApp() {
  const client = useClient();
  const { me, can } = useSession();
  const org = useQuery({ queryKey: ["org-me"], queryFn: () => client.myOrg(), refetchInterval: 30_000 });
  const orgId = org.data?.org_id;
  const members = useQuery({ queryKey: ["org-members", orgId], queryFn: () => client.members(orgId!), enabled: !!orgId, refetchInterval: 30_000 });
  const roles = useQuery({ queryKey: ["org-roles", orgId], queryFn: () => client.roles(orgId!), enabled: !!orgId, staleTime: 5 * 60_000 });
  const canManage = can("members.manage");
  const list = [...(members.data ?? [])].sort((a, b) => RANK.indexOf(b.role) - RANK.indexOf(a.role) || a.email.localeCompare(b.email));
  const invited = list.filter((m) => m.status === "invited").length;

  if (org.isError) return <p className="p-6 text-sm text-st-failed">Could not load the organization: {errText(org.error)}</p>;
  if (!org.data) return <Loading label="Loading the organization" state="working" />;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <AppHeader
        app="organization"
        title={org.data.name}
        sub={
          <>
            <span className="font-mono">{org.data.org_id}</span>
            {org.data.domain && <> · anyone at <span className="font-mono">@{org.data.domain}</span> joins as a member</>}
          </>
        }
      >
        <div className="flex items-center gap-2">
          <Pill>{list.length - invited} {list.length - invited === 1 ? "member" : "members"}</Pill>
          {invited > 0 && <Pill tone="warn">{invited} invited</Pill>}
          {me?.role && <Pill tone="brand" mono>you: {me.role}</Pill>}
        </div>
      </AppHeader>

      <div className="grid gap-4 @[1180px]:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card title="People">
          <div className="space-y-3">
            {canManage ? <InviteForm orgId={org.data.org_id} roles={roles.data ?? []} myRole={me?.role} /> : <NotAllowed role={me?.role} permission="members.manage" what="invite people or change roles" />}
            {members.isPending ? (
              <Loading label="Loading members" state="working" />
            ) : (
              <ul className="divide-y divide-hairline rounded-xl border border-hairline">
                {list.map((m) => (
                  <MemberRow key={m.email} m={m} orgId={org.data.org_id} roles={roles.data ?? []} canManage={canManage} myRole={me?.role} me={me?.user.user_id} />
                ))}
              </ul>
            )}
          </div>
        </Card>
        <Card title="What each role may do" aside={<span className="font-mono text-[11px] text-text-2">policies/rbac/roles.yaml</span>}>
          {roles.data ? <RoleMatrix roles={roles.data} myRole={me?.role} /> : <Loading label="Loading roles" state="working" />}
          <p className="mt-3 text-xs text-text-2">
            Roles decide what people may ask of KAIROS. What agents may do is decided separately, by policy: an approver still signs off on every risky action an agent proposes.
          </p>
        </Card>
      </div>
    </div>
  );
}
