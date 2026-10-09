import Constants from "expo-constants";
import { ScrollView, Switch, Text, View } from "react-native";
import { enableNotifications } from "../notify";
import { useSession } from "../session";
import { C, mono } from "../theme";
import { Button, Card, Label, Person, Pill, s } from "../ui";

const PERMISSION_LABEL: Record<string, string> = {
  "task.create": "Start tasks",
  "task.cancel": "Stop tasks",
  "approval.resolve": "Approve or reject actions",
  "knowledge.read": "Read /org and results",
  "knowledge.ingest": "Add knowledge",
  "connectors.manage": "Connect services",
  "config.read": "See system settings",
  "config.manage": "Change system settings",
  "members.manage": "Manage people",
};

/** Who you are here, what your role lets you do, which server, and notifications. */
export function Me() {
  const { me, server, notify, setNotify, signOut } = useSession();
  if (!me) return null;
  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14, paddingBottom: 40 }}>
      <Card style={{ ...s.row, gap: 14 }}>
        <Person name={me.user.name} email={me.user.email} size={54} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 20, fontWeight: "800", color: C.text }}>{me.user.name || me.user.email.split("@")[0]}</Text>
          <Text style={{ fontSize: 14, color: C.text2 }}>{me.user.email}</Text>
        </View>
      </Card>
      <Card style={{ gap: 10 }}>
        <Label>Organization</Label>
        <View style={s.row}>
          <Text style={{ flex: 1, fontSize: 17, fontWeight: "700", color: C.text }}>{me.org?.name ?? "none yet"}</Text>
          {me.role && (
            <Pill color={C.brand} bg={C.brandSoft} monoText>
              {me.role}
            </Pill>
          )}
        </View>
        <Label style={{ marginTop: 6 }}>Your role lets you</Label>
        {Object.entries(PERMISSION_LABEL).map(([p, label]) => {
          const yes = me.permissions?.includes(p);
          return (
            <View key={p} style={s.row}>
              <Text style={{ width: 18, color: yes ? C.done : C.text3, fontWeight: "800" }}>{yes ? "✓" : "·"}</Text>
              <Text style={{ flex: 1, color: yes ? C.text : C.text3 }}>{label}</Text>
            </View>
          );
        })}
      </Card>
      <Card style={{ gap: 10 }}>
        <Label>This phone</Label>
        <View style={s.row}>
          <Text style={{ flex: 1, color: C.text }}>Notify me about approvals and finished tasks</Text>
          <Switch
            value={notify}
            onValueChange={async (on) => {
              if (on) await enableNotifications();
              setNotify(on);
            }}
            trackColor={{ true: C.brand, false: C.line }}
          />
        </View>
        <Text style={{ fontFamily: mono, fontSize: 12, color: C.text2 }}>{server}</Text>
        <Text style={{ fontSize: 12, color: C.text3 }}>
          Signed in with {me.mode === "google" ? "Google" : "dev sign-in"} · app {Constants.expoConfig?.version ?? "1.0.0"}
        </Text>
      </Card>
      <Button label="Sign out" kind="danger" onPress={signOut} />
    </ScrollView>
  );
}
