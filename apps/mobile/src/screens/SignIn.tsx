import type { AuthConfig, Session } from "@kairos/contracts";
import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { createClient, normaliseUrl, reason } from "../client";
import { googleAvailable, googleIdToken } from "../google";
import { DEFAULT_SERVER, useSession } from "../session";
import { C, mono } from "../theme";
import { Button, Card, Label, Mark, Notice, Person, s } from "../ui";

/** Seeded in dev mode: one person per level of power. */
const PEOPLE = [
  { email: "alice@acme.example", name: "Alice", role: "owner", note: "Runs the org" },
  { email: "priya@acme.example", name: "Priya", role: "approver", note: "Signs off on actions" },
  { email: "sam@acme.example", name: "Sam", role: "viewer", note: "Reads results only" },
];

/** First run: which KAIROS server, then who you are (a demo account, any email in dev mode, or a code from the console). */
export function SignIn() {
  const { server, setServer, signIn } = useSession();
  const [url, setUrl] = useState(server);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");

  const check = async (target = url) => {
    setChecking(true);
    setError(null);
    setConfig(null);
    try {
      const c = createClient(target, null);
      await c.health();
      setConfig(await c.authConfig());
      if (normaliseUrl(target) !== normaliseUrl(server)) setServer(normaliseUrl(target));
    } catch (e) {
      setError(reason(e));
    } finally {
      setChecking(false);
    }
  };
  // Try the saved server once on open. On first run the emulator's address is the default; a real phone reaches the
  // laptop as localhost when it is plugged in over USB with `adb reverse tcp:8089 tcp:8089`, so try that next.
  useEffect(() => {
    (async () => {
      if (server === DEFAULT_SERVER) {
        for (const candidate of [DEFAULT_SERVER, "http://localhost:8089"]) {
          try {
            await createClient(candidate, null).health();
            setUrl(candidate);
            return check(candidate);
          } catch {
            /* try the next */
          }
        }
      }
      check(server);
    })();
    // once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (key: string, f: () => Promise<Session>) => {
    setBusy(key);
    setError(null);
    try {
      signIn(await f());
    } catch (e) {
      setError(reason(e));
    } finally {
      setBusy(null);
    }
  };
  const client = createClient(url, null);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16, paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: "center", marginTop: 24, marginBottom: 8, gap: 10 }}>
          <Mark size={48} />
          <Text style={[s.title, { fontSize: 32 }]}>
            KAIR<Text style={{ color: C.brand }}>OS</Text>
          </Text>
          <Text style={{ color: C.text2, fontSize: 15, textAlign: "center" }}>Your organization&apos;s AI in your pocket: start work, watch it run, and decide what it may do.</Text>
        </View>

        <Card style={{ gap: 10 }}>
          <Label>Server</Label>
          <TextInput value={url} onChangeText={(t) => { setUrl(t); setConfig(null); }} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="http://192.168.137.1:8089" placeholderTextColor={C.text3} style={[s.input, s.mono]} accessibilityLabel="Server address" onSubmitEditing={() => check()} />
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              {config ? (
                <Text style={{ color: C.done, fontWeight: "600" }}>Connected · {config.mode === "google" ? "Google accounts" : "dev sign-in"}</Text>
              ) : (
                <Text style={{ color: C.text2, fontSize: 13 }}>{checking ? "Checking…" : "The computer running KAIROS, port 8089: 10.0.2.2 from the emulator, localhost over USB (adb reverse)."}</Text>
              )}
            </View>
            <Button label="Check" kind="quiet" onPress={() => check()} busy={checking} style={{ minHeight: 40 }} />
          </View>
        </Card>

        {error && <Notice tone="error">{error}</Notice>}

        {config?.mode === "dev" && (
          <Card style={{ gap: 8 }}>
            <Label>Demo organization · Acme Corp</Label>
            {PEOPLE.map((p) => (
              <Pressable
                key={p.email}
                onPress={() => run(p.email, () => client.devLogin(p.email, p.name))}
                disabled={!!busy}
                style={({ pressed }) => [s.row, { padding: 10, borderRadius: 14, borderWidth: 1, borderColor: C.line, backgroundColor: pressed ? C.brandSoft : C.card }]}
                accessibilityRole="button"
                accessibilityLabel={`Sign in as ${p.name}, ${p.role}`}
              >
                <Person name={p.name} email={p.email} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 16, fontWeight: "700", color: C.text }}>
                    {p.name} <Text style={{ fontFamily: mono, fontSize: 12, color: C.text2, fontWeight: "500" }}>{p.role}</Text>
                  </Text>
                  <Text style={{ color: C.text2, fontSize: 13 }}>{p.note}</Text>
                </View>
                {busy === p.email ? <Text style={{ color: C.brand }}>…</Text> : <Text style={{ color: C.text3, fontSize: 20 }}>›</Text>}
              </Pressable>
            ))}
            <View style={[s.row, { marginTop: 4 }]}>
              <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="or any email" placeholderTextColor={C.text3} style={[s.input, { flex: 1 }]} accessibilityLabel="Email" />
              <Button label="Go" onPress={() => run("email", () => client.devLogin(email.trim()))} disabled={!email.includes("@")} busy={busy === "email"} />
            </View>
          </Card>
        )}

        {config?.mode === "google" && (
          <Card style={{ gap: 10 }}>
            <Label>Your organization uses Google</Label>
            {googleAvailable() ? (
              <Button
                label="Continue with Google"
                kind="quiet"
                busy={busy === "google"}
                onPress={() =>
                  run("google", async () => {
                    const token = await googleIdToken();
                    if (!token) throw new Error("Google sign-in was cancelled.");
                    return client.googleLogin(token);
                  })
                }
              />
            ) : (
              <Text style={{ color: C.text2, fontSize: 14 }}>
                This build has no Google client ID (EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID). Use a code from the console below.
              </Text>
            )}
          </Card>
        )}

        {config && (
          <Card style={{ gap: 10 }}>
            <Label>I have a code</Label>
            <Text style={{ color: C.text2, fontSize: 14 }}>In the console, open your name in the menu bar, then &ldquo;Sign in on your phone&rdquo;.</Text>
            <View style={s.row}>
              <TextInput
                value={code}
                onChangeText={(t) => setCode(t.toUpperCase())}
                autoCapitalize="characters"
                autoCorrect={false}
                placeholder="K7QM-4ZPD"
                placeholderTextColor={C.text3}
                style={[s.input, s.mono, { flex: 1, fontSize: 20, letterSpacing: 3 }]}
                accessibilityLabel="Sign-in code"
              />
              <Button label="Sign in" onPress={() => run("code", () => client.redeem(code))} disabled={code.replace(/[^A-Z0-9]/g, "").length < 8} busy={busy === "code"} />
            </View>
          </Card>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
