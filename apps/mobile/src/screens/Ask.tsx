import type { TaskCreate } from "@kairos/contracts";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { reason } from "../client";
import { useLive } from "../live";
import { useSession } from "../session";
import { C } from "../theme";
import { Button, Card, Label, Notice, Orb, s, Title } from "../ui";

// One example of each kind of goal the Jev router tells apart; any organization's goals work the same way.
const SUGGESTIONS: [string, string][] = [
  ["Investigate a project overrun", "Investigate why Project Apollo is over budget and six weeks behind schedule. Identify root causes, update the tracker, and prepare a recovery plan."],
  ["Summarize this week's decisions", "Summarize the decisions our teams made this week, with the documents behind each one."],
  ["Which vendors did we overpay?", "Which vendors did we overpay last quarter? Draft a note for finance."],
  ["Search the web", "What is the latest stable Python release? Search the web."],
];
type Priority = NonNullable<TaskCreate["priority"]>;

/** Start work: a goal in plain words; KAIROS plans it, runs agents and asks before anything risky. */
export function Ask({ onStarted }: { onStarted: (id: string) => void }) {
  const { client, can, me } = useSession();
  const { refresh } = useLive();
  const [goal, setGoal] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!can("task.create"))
    return (
      <View style={{ padding: 18, gap: 14 }}>
        <Title>Ask KAIROS</Title>
        <Notice>Your role ({me?.role ?? "none"}) can read results but not start tasks. Ask an admin for the member role.</Notice>
      </View>
    );

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const t = await client.createTask({ goal: goal.trim(), priority });
      setGoal("");
      refresh();
      onStarted(t.task_id);
    } catch (e) {
      setError(reason(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} keyboardShouldPersistTaps="handled">
        <Title sub="Say what you need. Agents plan it, cite their evidence and ask before acting.">Ask KAIROS</Title>
        <Card style={{ gap: 12 }}>
          <View style={[s.row, { alignItems: "flex-start" }]}>
            <Orb state={busy ? "working" : goal ? "breathing" : "breathing"} size={30} />
            <TextInput
              value={goal}
              onChangeText={setGoal}
              placeholder="Investigate, find or fix something…"
              placeholderTextColor={C.text3}
              multiline
              style={{ flex: 1, minHeight: 110, fontSize: 18, color: C.text, textAlignVertical: "top" }}
              accessibilityLabel="Goal"
            />
          </View>
          <View style={{ flexDirection: "row", borderRadius: 12, borderWidth: 1, borderColor: C.line, overflow: "hidden" }}>
            {(["high", "normal", "background"] as Priority[]).map((p) => (
              <Pressable key={p} onPress={() => setPriority(p)} style={{ flex: 1, paddingVertical: 9, alignItems: "center", backgroundColor: priority === p ? C.brandSoft : C.card }} accessibilityRole="radio" accessibilityState={{ selected: priority === p }}>
                <Text style={{ fontWeight: priority === p ? "700" : "500", color: priority === p ? C.brand : C.text2, textTransform: "capitalize" }}>{p}</Text>
              </Pressable>
            ))}
          </View>
          <Button label="Start" onPress={start} busy={busy} disabled={!goal.trim()} />
        </Card>
        {error && <Notice tone="error">{error}</Notice>}
        <View style={{ gap: 8 }}>
          <Label>Try</Label>
          {SUGGESTIONS.map(([label, text]) => (
            <Card key={label} onPress={() => setGoal(text)} style={{ paddingVertical: 12 }}>
              <Text style={{ fontSize: 15, color: C.text, fontWeight: "600" }}>{label}</Text>
            </Card>
          ))}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
