import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { BackHandler, Pressable, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { LiveProvider, useLive } from "./src/live";
import { onNotificationTap } from "./src/notify";
import { Approvals } from "./src/screens/Approvals";
import { Ask } from "./src/screens/Ask";
import { Home } from "./src/screens/Home";
import { Knowledge } from "./src/screens/Knowledge";
import { Me } from "./src/screens/Me";
import { SignIn } from "./src/screens/SignIn";
import { Task } from "./src/screens/Task";
import { SessionProvider, useSession } from "./src/session";
import { C } from "./src/theme";
import { Mark, Orb } from "./src/ui";

type Tab = "home" | "approvals" | "ask" | "knowledge" | "me";
const TABS: { id: Tab; label: string; glyph: string }[] = [
  { id: "home", label: "Home", glyph: "◧" },
  { id: "approvals", label: "Approvals", glyph: "◉" },
  { id: "ask", label: "Ask", glyph: "✦" },
  { id: "knowledge", label: "Knowledge", glyph: "▦" },
  { id: "me", label: "Me", glyph: "◍" },
];

export default function App() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <Root />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

function Root() {
  const { ready, session } = useSession();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.ground }} edges={["top", "left", "right"]}>
      <StatusBar style="dark" />
      {!ready ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 14 }}>
          <Mark size={44} />
          <Orb state="working" size={32} />
        </View>
      ) : session ? (
        <LiveProvider>
          <Main />
        </LiveProvider>
      ) : (
        <SignIn />
      )}
    </SafeAreaView>
  );
}

/** Five tabs, and one task opened on top of them. */
function Main() {
  const [tab, setTab] = useState<Tab>("home");
  const [taskId, setTaskId] = useState<string | null>(null);
  const { approvals } = useLive();

  // Android's back button closes an open task before it leaves the app.
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (taskId) {
        setTaskId(null);
        return true;
      }
      if (tab !== "home") {
        setTab("home");
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [taskId, tab]);

  // A tapped notification opens what it was about.
  useEffect(
    () =>
      onNotificationTap((data) => {
        if (data.screen === "approvals") {
          setTaskId(null);
          setTab("approvals");
        } else if (data.screen === "task" && typeof data.task === "string") setTaskId(data.task);
      }),
    [],
  );

  const open = (id: string) => setTaskId(id);
  return (
    <View style={{ flex: 1 }}>
      <View style={{ flex: 1 }}>
        {taskId ? (
          <Task id={taskId} onBack={() => setTaskId(null)} />
        ) : tab === "home" ? (
          <Home onOpenTask={open} onApprovals={() => setTab("approvals")} onAsk={() => setTab("ask")} />
        ) : tab === "approvals" ? (
          <Approvals onOpenTask={open} />
        ) : tab === "ask" ? (
          <Ask onStarted={(id) => setTaskId(id)} />
        ) : tab === "knowledge" ? (
          <Knowledge />
        ) : (
          <Me />
        )}
      </View>
      <SafeAreaView edges={["bottom"]} style={{ backgroundColor: "rgba(255,255,255,0.96)", borderTopWidth: 1, borderTopColor: C.line }}>
        <View style={{ flexDirection: "row", paddingTop: 6, paddingBottom: 4 }} accessibilityRole="tablist">
          {TABS.map((t) => {
            const on = tab === t.id && !taskId;
            return (
              <Pressable
                key={t.id}
                onPress={() => {
                  setTaskId(null);
                  setTab(t.id);
                }}
                style={{ flex: 1, alignItems: "center", gap: 2, minHeight: 48, justifyContent: "center" }}
                accessibilityRole="tab"
                accessibilityState={{ selected: on }}
                accessibilityLabel={t.id === "approvals" && approvals.length ? `${t.label}, ${approvals.length} waiting` : t.label}
              >
                <View>
                  <Text style={{ fontSize: 20, color: on ? C.brand : C.text3 }}>{t.glyph}</Text>
                  {t.id === "approvals" && approvals.length > 0 && (
                    <View style={{ position: "absolute", top: -4, right: -12, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: C.failed, alignItems: "center", justifyContent: "center", paddingHorizontal: 4 }}>
                      <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>{approvals.length}</Text>
                    </View>
                  )}
                </View>
                <Text style={{ fontSize: 11, fontWeight: on ? "700" : "500", color: on ? C.brand : C.text2 }}>{t.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </SafeAreaView>
    </View>
  );
}
