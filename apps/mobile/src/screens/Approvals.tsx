import type { Approval } from "@kairos/contracts";
import * as Haptics from "expo-haptics";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from "react-native";
import { reason } from "../client";
import { headline, useLive } from "../live";
import { useSession } from "../session";
import { C, folderHue, mono } from "../theme";
import { BotFace, Button, Card, Label, Notice, Pill, s, Title } from "../ui";

const RISK: Record<string, [string, string]> = {
  critical: [C.failed, C.failedSoft],
  high: [C.failed, C.failedSoft],
  medium: [C.waiting, C.waitingSoft],
  low: [C.done, C.doneSoft],
};

function ApprovalCard({ a, onOpenTask }: { a: Approval; onOpenTask: (id: string) => void }) {
  const { client, can, me } = useSession();
  const { refresh } = useLive();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sc = a.syscall;
  const [riskFg, riskBg] = RISK[sc.risk ?? "medium"] ?? RISK.medium;
  const decide = async (approve: boolean) => {
    setBusy(approve ? "approve" : "reject");
    setError(null);
    try {
      await (approve ? client.approve(a.approval_id, comment) : client.reject(a.approval_id, comment));
      Haptics.notificationAsync(approve ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning).catch(() => undefined);
      await refresh();
    } catch (e) {
      setError(reason(e));
    } finally {
      setBusy(null);
    }
  };
  const target = sc.resource ?? String((sc.arguments as Record<string, unknown> | undefined)?.key ?? "");

  return (
    <Card style={{ gap: 12, borderColor: "rgba(217,119,6,0.45)" }}>
      <View style={[s.row, { alignItems: "flex-start" }]}>
        <BotFace agent={a.agent} state="WAITING" size={44} />
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={{ fontSize: 17, fontWeight: "700", color: C.text, lineHeight: 22 }}>{headline(a)}</Text>
          <View style={[s.row, { flexWrap: "wrap", gap: 6 }]}>
            <Pill color={riskFg} bg={riskBg}>{sc.risk ?? "medium"} risk</Pill>
            <Pill monoText>{sc.capability}</Pill>
            {target ? <Pill monoText>{target}</Pill> : null}
          </View>
        </View>
      </View>

      {sc.justification ? (
        <View style={{ borderLeftWidth: 3, borderLeftColor: C.brand, paddingLeft: 10 }}>
          <Text style={{ fontSize: 15, color: C.text, lineHeight: 21 }}>{sc.justification}</Text>
        </View>
      ) : null}

      <View>
        <Label>Policy</Label>
        <Text style={{ fontSize: 14, color: C.text2 }}>
          <Text style={{ fontFamily: mono, color: C.brand, fontWeight: "700" }}>{a.decision.policy}</Text> · {a.decision.reason}
        </Text>
      </View>

      <View>
        <Label>What it will send</Label>
        <ScrollView horizontal style={{ backgroundColor: C.sunk, borderRadius: 12 }} contentContainerStyle={{ padding: 10 }}>
          <Text style={{ fontFamily: mono, fontSize: 12, color: C.text }}>{JSON.stringify(sc.arguments ?? {}, null, 2)}</Text>
        </ScrollView>
      </View>

      {!!sc.evidence?.length && (
        <View style={{ gap: 4 }}>
          <Label>Evidence · {sc.evidence.length}</Label>
          {sc.evidence.slice(0, 6).map((p) => (
            <View key={p} style={s.row}>
              <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: folderHue(p) }} />
              <Text style={{ fontFamily: mono, fontSize: 12, color: C.text2, flex: 1 }} numberOfLines={1}>
                {p}
              </Text>
            </View>
          ))}
        </View>
      )}

      <Text onPress={() => onOpenTask(a.task_id)} style={{ color: C.brand, fontWeight: "600" }}>
        See the whole run ({a.task_id}) ›
      </Text>

      {error && <Notice tone="error">{error}</Notice>}

      {can("approval.resolve") ? (
        <>
          <TextInput value={comment} onChangeText={setComment} placeholder="Comment (goes in the audit journal)" placeholderTextColor={C.text3} style={s.input} multiline />
          <View style={[s.row, { gap: 10 }]}>
            <Button label="Approve" kind="approve" style={{ flex: 1 }} busy={busy === "approve"} disabled={!!busy} onPress={() => decide(true)} />
            <Button label="Reject" kind="danger" style={{ flex: 1 }} busy={busy === "reject"} disabled={!!busy} onPress={() => decide(false)} />
          </View>
          <Text style={{ fontSize: 12, color: C.text3 }}>It runs in a transaction: verified, then committed, or rolled back automatically.</Text>
        </>
      ) : (
        <Notice>Your role ({me?.role ?? "none"}) can see this request but not decide it. An approver will.</Notice>
      )}
    </Card>
  );
}

/** What agents are waiting to be allowed to do. */
export function Approvals({ onOpenTask }: { onOpenTask: (id: string) => void }) {
  const { approvals, error, loaded } = useLive();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 18, gap: 14, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        <Title sub="Risky actions pause here until a person decides.">Approvals</Title>
        {error && <Notice tone="error">{error}</Notice>}
        {approvals.map((a) => (
          <ApprovalCard key={a.approval_id} a={a} onOpenTask={onOpenTask} />
        ))}
        {loaded && !approvals.length && <Notice>Nothing is waiting. When an agent wants to write to Jira, email someone or open an issue, it asks here first.</Notice>}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
