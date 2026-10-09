import type { SearchHit } from "@kairos/contracts";
import { useState } from "react";
import { FlatList, Text, TextInput, View } from "react-native";
import { reason } from "../client";
import { useSession } from "../session";
import { C, folderHue, mono } from "../theme";
import { Button, Card, Notice, Orb, s, Title } from "../ui";

/** Search what the organization knows (/org), with the same hybrid search agents use. */
export function Knowledge() {
  const { client } = useSession();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const search = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setHits((await client.search(q.trim(), 10)).hits);
    } catch (e) {
      setError(reason(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <FlatList
      data={hits ?? []}
      keyExtractor={(h) => `${h.path}#${h.chunk_id ?? ""}`}
      contentContainerStyle={{ padding: 18, gap: 10, paddingBottom: 40 }}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={
        <View style={{ gap: 12, marginBottom: 4 }}>
          <Title sub="Documents, decisions, tickets and meetings under /org.">Knowledge</Title>
          <View style={s.row}>
            <TextInput value={q} onChangeText={setQ} onSubmitEditing={search} returnKeyType="search" placeholder="security policy vendors" placeholderTextColor={C.text3} style={[s.input, { flex: 1 }]} accessibilityLabel="Search" />
            <Button label="Search" onPress={search} busy={busy} />
          </View>
          {error && <Notice tone="error">{error}</Notice>}
          {busy && (
            <View style={{ alignItems: "center", padding: 12 }}>
              <Orb state="working" size={40} />
            </View>
          )}
          {hits && !hits.length && <Notice>Nothing matched. Try other words.</Notice>}
        </View>
      }
      renderItem={({ item: h }) => (
        <Card style={{ gap: 6 }}>
          <View style={s.row}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: folderHue(h.path) }} />
            <Text style={{ flex: 1, fontSize: 15, fontWeight: "700", color: C.text }} numberOfLines={1}>
              {h.title}
            </Text>
            <Text style={{ fontFamily: mono, fontSize: 11, color: C.text3 }}>{h.score.toFixed(2)}</Text>
          </View>
          <Text style={{ fontFamily: mono, fontSize: 11, color: C.text2 }} numberOfLines={1}>
            {h.path}
          </Text>
          <Text style={{ fontSize: 14, color: C.text2, lineHeight: 20 }} numberOfLines={4}>
            {h.snippet}
          </Text>
          {!!h.firewall_flags?.length && <Text style={{ color: C.failed, fontSize: 12, fontWeight: "600" }}>Flagged by the prompt firewall: {h.firewall_flags.join(", ")}</Text>}
        </Card>
      )}
    />
  );
}
