// Google sign-in (@react-native-google-signin/google-signin), from Manjunath's d/settings. It needs native code, so it
// only works in the APK or a development build, never in Expo Go; the module is loaded lazily so Expo Go and the web
// build still start. EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID must be the WEB OAuth client ID: that is the audience the gateway
// verifies the ID token against (KAIROS_GOOGLE_CLIENT_ID). The Android client ID only has to exist in the same Cloud
// project, registered with this app's package and signing SHA-1.
import { Platform } from "react-native";

export const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID ?? "";

type Module = typeof import("@react-native-google-signin/google-signin");

function load(): Module | null {
  if (Platform.OS === "web" || !GOOGLE_WEB_CLIENT_ID) return null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("@react-native-google-signin/google-signin") as Module;
  } catch {
    return null;
  }
}

export function googleAvailable(): boolean {
  return load() !== null;
}

/** The Google ID token, or null when the user cancelled. Throws with a readable message otherwise. */
export async function googleIdToken(): Promise<string | null> {
  const mod = load();
  if (!mod) throw new Error("Google sign-in needs the APK or a development build with EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID.");
  const { GoogleSignin, isSuccessResponse } = mod;
  GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
  await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
  const res = await GoogleSignin.signIn();
  if (!isSuccessResponse(res)) return null;
  if (!res.data.idToken) throw new Error("Google returned no ID token: check the web client ID.");
  return res.data.idToken;
}

export async function googleSignOut(): Promise<void> {
  await load()?.GoogleSignin.signOut().catch(() => undefined);
}
