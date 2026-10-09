import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

// Shown even while the app is open: a decision is wanted wherever you are in the app.
Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false }),
});

let allowed: boolean | null = null;

/** Ask once for permission (Android 13+ and iOS need it) and set up the channel approvals ring on. */
export async function enableNotifications(): Promise<boolean> {
  if (allowed !== null) return allowed;
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("approvals", {
        name: "Approvals",
        description: "An agent is waiting for your decision",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 180, 120, 180],
        lightColor: "#0b6b60",
      });
      await Notifications.setNotificationChannelAsync("tasks", { name: "Tasks", description: "A task finished", importance: Notifications.AndroidImportance.DEFAULT });
    }
    const current = await Notifications.getPermissionsAsync();
    allowed = current.granted || (await Notifications.requestPermissionsAsync()).granted;
  } catch {
    allowed = false;
  }
  return allowed;
}

/** A local notification; the tap brings the app back to `data.screen`. */
export async function notify(title: string, body: string, data: Record<string, string>, channel: "approvals" | "tasks") {
  if (!(await enableNotifications())) return;
  await Notifications.scheduleNotificationAsync({
    content: { title, body, data, ...(Platform.OS === "android" ? {} : { sound: true }) },
    trigger: Platform.OS === "android" ? { channelId: channel } : null,
  }).catch(() => undefined);
}

export function onNotificationTap(handler: (data: Record<string, unknown>) => void): () => void {
  const sub = Notifications.addNotificationResponseReceivedListener((r) => handler(r.notification.request.content.data ?? {}));
  return () => sub.remove();
}
