# apps/mobile: KAIROS on the phone

An Expo (SDK 57, React Native 0.86) app for using KAIROS away from the desk: sign in, see what is running, decide
what agents may do, and start work. Types come from `@kairos/contracts` (`shared/ts`); `metro.config.js` watches that
folder.

## What it does

| Screen | |
|---|---|
| Sign in | The server address (checked with `/health` and `/auth/config`), then: one of the demo org's people in dev mode (Alice owner, Priya approver, Sam viewer), any email in dev mode, or a one-time code from the console, which also works when the org uses Google accounts. |
| Home | A greeting, the org and your role, a live/reconnecting dot, what needs you, running tasks with thinking orbs, recent tasks. Pull to refresh. |
| Task | The goal and status, the agents on it as faces (they hop while working, look around while waiting, doze when done), the story of the run from the audit journal, and the answer with its evidence. Stop the task if your role allows. |
| Approvals | Each waiting action: which agent, the capability and target, risk, the policy that paused it, the justification, the arguments, the evidence. Approve or reject with a comment. A role without `approval.resolve` sees the request but not the buttons. |
| Ask | A goal in plain words, a priority and the demo prompts. Hidden behind a notice for roles without `task.create`. |
| Knowledge | Hybrid search over /org, with firewall flags. |
| Me | Who you are, the org, what your role lets you do, the server, notifications, sign out. |

Live data comes from the gateway's event stream (`/ws/events?token=`), with an 8-second poll behind it. When a new
approval appears or a task you were watching finishes, the phone shows a notification (while the app is open or
recently backgrounded; there is no push server). Tapping it opens the approval or the task.

## Signing in

- **Dev mode** (`KAIROS_AUTH=dev`, the default): pick a person or type any email. Addresses at `@acme.example` join
  the demo org; Priya and Sam are invited ahead, so they sign in with their roles.
- **With a code** (both modes): in the console, open your name in the menu bar, then **Sign in on your phone**. Type the
  eight characters within five minutes. The phone gets a session of its own for the same person.
- **With Google** (`KAIROS_AUTH=google`; `src/google.ts`, from Manjunath's `d/settings`): the app gets a Google ID
  token natively and exchanges it at `POST /auth/google`. The button appears only in the APK or a development build
  (native code, so not in Expo Go), and only when this is set at build time:
  ```
  EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID=<the WEB OAuth client ID, the same as the gateway's KAIROS_GOOGLE_CLIENT_ID>
  ```
  The **Android** client ID must also exist in the same Google Cloud project, registered with the package
  `ai.kairos.phone` and the SHA-1 of the signing key (`cd android && .\gradlew signingReport`). For iOS, give the
  `@react-native-google-signin/google-signin` plugin an `iosUrlScheme` in `app.json`.
- **Roles:** the buttons follow `/auth/me`'s permissions. `src/rbac.ts` mirrors `policies/rbac/roles.yaml` for a server
  that sends a role without permissions; the gateway stays the authority either way.

## Server address

| Where the phone is | Address |
|---|---|
| Android emulator on the same computer | `http://10.0.2.2:8089` (the default) |
| A phone on the laptop's hotspot or Wi-Fi | `http://<laptop IP>:8089`; `scripts\win\phone-access.ps1` (as administrator) opens the firewall and prints it |
| Over Tailscale | `https://<node>.<tailnet>.ts.net:8443` (see `infra/appliance/README.md`) |

The release build allows plain HTTP (`usesCleartextTraffic`) so it can reach a gateway on the local network.

## Develop

```bash
cd apps/mobile
npm ci
npm run typecheck
npx expo start          # Expo Go, or press a for the emulator
```

Against the mock gateway: `uv run kairos-mock-gateway --port 8089` on the laptop.

## Build the APK

```powershell
powershell -File apps\mobile\scripts\build-apk.ps1                  # arm64 phones and the x86_64 emulator
powershell -File apps\mobile\scripts\build-apk.ps1 -Abis arm64-v8a  # phones only, smaller
```

The script uses Android Studio's JDK and SDK (`%LOCALAPPDATA%\Android\Sdk`), runs `expo prebuild` and
`gradlew assembleRelease` with three workers, and copies the result to `apps/mobile/dist/kairos-<version>.apk`. The first build compiles
native code and takes a while; later ones are quick. The APK is signed with the debug key, which is fine for
sideloading and the demo but not for the Play Store. For the Play Store, make your own keystore and keep it out of the
repo (`*.jks` and `*.keystore` are ignored).

Install it on the running emulator or a phone with USB debugging:

```powershell
adb install -r apps\mobile\dist\kairos-1.1.0.apk
```

Verified: on the Pixel_6a emulator an Apollo run was started and approved from the app (8/8); Manjunath's build of
his branch was tested on a moto g54 5G (Android 15) over USB. To reach the laptop's gateway from a phone without
Wi-Fi, run `adb reverse tcp:8089 tcp:8089` and use `http://localhost:8089` in the app.

**Windows pitfalls** (all hit on team laptops):
- **Run the build detached when an agent starts it.** A Gradle build cancels when the shell that started it goes away.
  In Windows PowerShell, `$ErrorActionPreference = "Stop"` plus `*>` turns Gradle's stderr warnings into fatal errors
  (the script uses "Continue" and exit codes).
- **Memory:** the native compile, the emulator, Ollama and Docker together can exhaust the paging file ("insufficient
  memory for the Java Runtime"). Close the emulator, or pass `-Workers 2`.
- **Don't build inside OneDrive:** `ninja: error: manifest 'build.ninja' still dirty after 100 tries`, because OneDrive
  rewrites timestamps. Copy `apps/mobile` and `shared/ts` to a short local path and build there.
- **NDK error** `[CXX1101] NDK at ... did not have a source.properties file`: that NDK install is incomplete; reinstall
  it in Android Studio's SDK Manager.
- **Gradle downloads time out in Java while `curl` works:** set `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv4Stack=true`.

**Signing for a store:** create a keystore outside the repo (`keytool -genkeypair -v -keystore kairos-release.jks
-alias kairos -keyalg RSA -keysize 2048 -validity 10000`), put the store path, alias and passwords in
`%USERPROFILE%\.gradle\gradle.properties`, and point `signingConfigs.release` in `android/app/build.gradle` at them.
Never commit the keystore or passwords.

## Checks before a commit

`npm run typecheck`, `npm run contrast` (every text colour meets WCAG AA on its surface; Manjunath's check, adapted to
this palette), then `npx expo export --platform android` to confirm Metro bundles.

`android/` is generated and ignored; `app.json` is the source of truth. The icons are drawn by
`scripts/make-icons.py` from the KAIROS mark.
