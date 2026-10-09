import type { Task } from "@kairos/contracts";
import { useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { headline, useLive } from "../live";
import { useSession } from "../session";
import { C, isActive, STATUS } from "../theme";
import { Card, Label, Notice, Orb, Pill, s } from "../ui";

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

export function ago(ts?: string | null): string {
  if (!ts) return "";
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  return s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 ? `${Math.round(s / 3600)}h` : `${Math.round(s / 86400)}d`;
}

export function TaskRow({ t, onOpen }: { t: Task; onOpen: (id: string) => void }) {
  const st = STATUS[t.status ?? "queued"] ?? STATUS.queued;
  const live = isActive(t.status);
  return (
    <Card onPress={() => onOpen(t.task_id)} style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
      <Orb state={t.status === "waiting_approval" ? "waiting" : live ? "working" : t.status === "completed" ? "done" : "breathing"} size={live ? 34 : 26} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={{ fontSize: 15, fontWeight: "600", color: C.text }} numberOfLines={2}>
          {t.goal}
        </Text>
        <View style={s.row}>
          <Pill color={st.color} bg={st.soft}>{st.label}</Pill>
          <Text style={[s.mono, { fontSize: 12, color: C.text3 }]}>
            {t.task_id} · {ago(t.created_at)}
          </Text>
        </View>
      </View>
    </Card>
  );
}

/** What is happening now: who you are, what needs you, what is running, what finished. */
export function Home({ onOpenTask, onApprovals, onAsk }: { onOpenTask: (id: string) => void; onApprovals: () => void; onAsk: () => void }) {
  const { me, can } = useSession();
  const { tasks, approvals, error, refresh, connected, loaded } = useLive();
  const [pulling, setPulling] = useState(false);
  const running = tasks.filter((t) => isActive(t.status));
  const recent = tasks.filter((t) => !isActive(t.status)).slice(0, 6);
  const name = (me?.user.name || me?.user.email.split("@")[0] || "there").split(" ")[0];

  return (
    <ScrollView
      contentContainerStyle={{ padding: 18, gap: 14, paddingBottom: 32 }}
      refreshControl={
        <RefreshControl
          refreshing={pulling}
          onRefresh={async () => {
            setPulling(true);
            await refresh();
            setPulling(false);
          }}
        />
      }
    >
      <View style={[s.row, { justifyContent: "space-between" }]}>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { fontSize: 30 }]}>
            {greeting()}, {name.charAt(0).toUpperCase() + name.slice(1)}.
          </Text>
          <View style={[s.row, { marginTop: 6 }]}>
            <View style={{ width: 8, height: 8, borderRadius: 8, backgroundColor: connected ? C.running : C.waiting }} />
            <Text style={[s.mono, { fontSize: 12, color: C.text2 }]}>
              {me?.org?.name ?? "no org"} · {me?.role ?? "?"} · {connected ? "live" : "reconnecting"}
            </Text>
          </View>
        </View>
        <Orb state={running.length ? "working" : "breathing"} size={44} />
      </View>

      {error && <Notice tone="error">{error}</Notice>}

      {approvals.length > 0 && (
        <Card onPress={onApprovals} style={{ backgroundColor: C.waitingSoft, borderColor: "rgba(217,119,6,0.35)", gap: 4 }}>
          <Text style={{ color: C.waiting, fontWeight: "800", fontSize: 13, letterSpacing: 0.5 }}>
            {can("approval.resolve") ? "NEEDS YOU" : "WAITING FOR AN APPROVER"} · {approvals.length}
          </Text>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: "600" }}>{headline(approvals[0])}</Text>
          <Text style={{ color: C.text2, fontSize: 13 }}>Tap to review the evidence and decide.</Text>
        </Card>
      )}

      {can("task.create") && (
        <Card onPress={onAsk} style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Orb state="breathing" size={28} />
          <Text style={{ flex: 1, fontSize: 16, color: C.text2 }}>What should KAIROS work on?</Text>
        </Card>
      )}

      {running.length > 0 && (
        <View style={{ gap: 8 }}>
          <Label>Running now · {running.length}</Label>
          {running.map((t) => (
            <TaskRow key={t.task_id} t={t} onOpen={onOpenTask} />
          ))}
        </View>
      )}

      <View style={{ gap: 8 }}>
        <Label>Recent</Label>
        {recent.map((t) => (
          <TaskRow key={t.task_id} t={t} onOpen={onOpenTask} />
        ))}
        {loaded && !tasks.length && <Notice>No tasks yet.{can("task.create") ? " Ask KAIROS for something." : ""}</Notice>}
      </View>
    </ScrollView>
  );
}
