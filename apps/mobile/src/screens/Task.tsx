import type { AuditEntry, ProcessTreeNode, RunTimeline, Task as TaskT } from "@kairos/contracts";
import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { reason } from "../client";
import { useSession } from "../session";
import { C, folderHue, isActive, mono, STATUS } from "../theme";
import { BotFace, Button, Card, Label, Notice, Orb, Pill, s } from "../ui";
import { ago } from "./Home";

const KIND_COLOUR: Record<string, string> = {
  task: C.text2,
  spawn: C.blue,
  state: C.text3,
  model: C.violet,
  knowledge: "#0891b2",
  memory: "#7c3aed",
  ipc: C.blue,
  syscall: C.brand,
  policy: C.waiting,
  approval: C.waiting,
  tool: C.running,
  verify: C.done,
  commit: C.done,
  rollback: C.failed,
};

function flatten(nodes: ProcessTreeNode[], depth = 0): { node: ProcessTreeNode; depth: number }[] {
  return nodes.flatMap((n) => [{ node: n, depth }, ...flatten(n.children ?? [], depth + 1)]);
}

/** The steps worth reading on a phone: skip the state bookkeeping, keep what the agents did. */
const worth = (e: AuditEntry) => e.kind !== "state" && e.kind !== "verify";

/** One task, live: the agents working on it, the story so far, and the answer with its evidence. */
export function Task({ id, onBack }: { id: string; onBack: () => void }) {
  const { client, can } = useSession();
  const [task, setTask] = useState<TaskT | null>(null);
  const [tree, setTree] = useState<ProcessTreeNode[]>([]);
  const [story, setStory] = useState<RunTimeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [all, setAll] = useState(false);

  const load = useCallback(async () => {
    try {
      const [t, p, a] = await Promise.all([client.task(id), client.processTree(id).catch(() => []), client.timeline(id).catch(() => null)]);
      setTask(t);
      setTree(p);
      if (a) setStory(a);
      setError(null);
    } catch (e) {
      setError(reason(e));
    }
  }, [client, id]);

  useEffect(() => {
    load();
    let soon: ReturnType<typeof setTimeout> | undefined;
    const stop = client.events(
      () => {
        soon ??= setTimeout(() => {
          soon = undefined;
          load();
        }, 400);
      },
      ["task.*", "process.*", "syscall.*", "approval.*", "knowledge.retrieved", "tool.*"],
    );
    const timer = setInterval(load, 5_000);
    return () => {
      stop();
      clearTimeout(soon);
      clearInterval(timer);
    };
  }, [client, load]);

  const st = STATUS[task?.status ?? "queued"] ?? STATUS.queued;
  const live = isActive(task?.status);
  const agents = flatten(tree);
  const steps = (story?.entries ?? []).filter(worth);
  const shown = all ? steps : steps.slice(-12);
  const evidence = task?.result?.evidence ?? [];

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14, paddingBottom: 40 }}>
      <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="Back" hitSlop={12}>
        <Text style={{ color: C.brand, fontSize: 16, fontWeight: "600" }}>‹ Back</Text>
      </Pressable>
      {error && <Notice tone="error">{error}</Notice>}
      {task && (
        <Card style={{ gap: 10 }}>
          <View style={[s.row, { alignItems: "flex-start" }]}>
            <Orb state={task.status === "waiting_approval" ? "waiting" : live ? "working" : task.status === "completed" ? "done" : "breathing"} size={40} />
            <Text style={{ flex: 1, fontSize: 18, fontWeight: "700", color: C.text, lineHeight: 24 }}>{task.goal}</Text>
          </View>
          <View style={[s.row, { flexWrap: "wrap" }]}>
            <Pill color={st.color} bg={st.soft}>{st.label}</Pill>
            <Text style={[s.mono, { fontSize: 12, color: C.text3 }]}>
              {task.task_id} · {ago(task.created_at)} ago · {task.priority ?? "normal"}
            </Text>
          </View>
          {live && can("task.cancel") && (
            <Button
              label="Stop this task"
              kind="danger"
              busy={cancelling}
              onPress={async () => {
                setCancelling(true);
                await client.cancelTask(id).catch((e) => setError(reason(e)));
                setCancelling(false);
                load();
              }}
            />
          )}
        </Card>
      )}

      {agents.length > 0 && (
        <View style={{ gap: 8 }}>
          <Label>Agents on it · {agents.length}</Label>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {agents.map(({ node }) => (
              <View key={node.pid} style={{ alignItems: "center", width: 84, gap: 4 }}>
                <BotFace agent={node.agent} state={node.state} size={48} />
                <Text style={{ fontSize: 12, fontWeight: "600", color: C.text }} numberOfLines={1}>
                  {node.agent.replace(/-agent.*$/, "")}
                </Text>
                <Text style={[s.mono, { fontSize: 10, color: C.text3 }]}>
                  #{node.pid} {String(node.state).toLowerCase()}
                </Text>
              </View>
            ))}
          </ScrollView>
        </View>
      )}

      {task?.result?.summary && (
        <Card style={{ gap: 8 }}>
          <Label>Answer</Label>
          <Text style={{ fontSize: 15, lineHeight: 22, color: C.text }}>{task.result.summary.replace(/^#+\s*/gm, "").replace(/\*\*/g, "")}</Text>
          {evidence.length > 0 && (
            <View style={{ gap: 6, marginTop: 4 }}>
              <Label>Evidence · {evidence.length}</Label>
              {evidence.slice(0, 10).map((p) => (
                <View key={p} style={s.row}>
                  <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: folderHue(p) }} />
                  <Text style={{ fontFamily: mono, fontSize: 12, color: C.text2, flex: 1 }} numberOfLines={1}>
                    {p}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </Card>
      )}

      {steps.length > 0 && (
        <View style={{ gap: 8 }}>
          <View style={[s.row, { justifyContent: "space-between" }]}>
            <Label style={{ marginBottom: 0 }}>How it went · {steps.length} steps</Label>
            {steps.length > 12 && (
              <Pressable onPress={() => setAll((x) => !x)} hitSlop={10}>
                <Text style={{ color: C.brand, fontWeight: "600" }}>{all ? "Latest" : "All"}</Text>
              </Pressable>
            )}
          </View>
          <Card style={{ gap: 0, paddingVertical: 6 }}>
            {shown.map((e, i) => (
              <View key={e.entry_id} style={{ flexDirection: "row", gap: 10, paddingVertical: 8, borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>
                <View style={{ width: 8, height: 8, borderRadius: 8, marginTop: 6, backgroundColor: KIND_COLOUR[e.kind] ?? C.text3 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, color: C.text, lineHeight: 19 }}>{e.summary}</Text>
                  <Text style={[s.mono, { fontSize: 11, color: C.text3 }]}>
                    {e.actor} · {e.kind}
                  </Text>
                </View>
              </View>
            ))}
          </Card>
        </View>
      )}
    </ScrollView>
  );
}
