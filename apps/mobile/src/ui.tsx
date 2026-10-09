import { useEffect, useRef } from "react";
import { ActivityIndicator, Animated, Easing, Pressable, StyleSheet, Text, type TextStyle, View, type ViewStyle } from "react-native";
import Svg, { Circle, Ellipse, Line, Path, Rect } from "react-native-svg";
import { C, mono } from "./theme";

export function Card({ children, style, onPress }: { children: React.ReactNode; style?: ViewStyle; onPress?: () => void }) {
  if (onPress)
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [s.card, style, pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] }]}>
        {children}
      </Pressable>
    );
  return <View style={[s.card, style]}>{children}</View>;
}

export function Pill({ children, color = C.text2, bg = C.sunk, monoText }: { children: React.ReactNode; color?: string; bg?: string; monoText?: boolean }) {
  return (
    <View style={[s.pill, { backgroundColor: bg }]}>
      <Text style={[s.pillText, { color }, monoText && { fontFamily: mono }]} numberOfLines={1}>
        {children}
      </Text>
    </View>
  );
}

export function Button({
  label,
  onPress,
  kind = "primary",
  busy,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  kind?: "primary" | "quiet" | "danger" | "approve";
  busy?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  const bg = kind === "primary" ? C.brand : kind === "approve" ? C.done : kind === "danger" ? C.card : C.card;
  const fg = kind === "primary" || kind === "approve" ? "#fff" : kind === "danger" ? C.failed : C.text;
  const border = kind === "danger" ? "rgba(220,38,38,0.45)" : kind === "quiet" ? C.line : bg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [s.button, { backgroundColor: bg, borderColor: border }, (disabled || busy) && { opacity: 0.5 }, pressed && { transform: [{ scale: 0.98 }] }, style]}
    >
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[s.buttonText, { color: fg }]}>{label}</Text>}
    </Pressable>
  );
}

export function Title({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.title}>{children}</Text>
      {sub ? <Text style={s.sub}>{sub}</Text> : null}
    </View>
  );
}

export const Label = ({ children, style }: { children: React.ReactNode; style?: TextStyle }) => <Text style={[s.label, style]}>{children}</Text>;

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "error" | "warn" }) {
  const map = { info: [C.sunk, C.text2], error: [C.failedSoft, C.failed], warn: [C.waitingSoft, C.waiting] } as const;
  return (
    <View style={[s.notice, { backgroundColor: map[tone][0] }]}>
      <Text style={{ color: map[tone][1], fontSize: 14, lineHeight: 20 }}>{children}</Text>
    </View>
  );
}

/** A thinking orb: a ring of dots and a core. It breathes when idle, spins while working, pulses amber while waiting. */
export function Orb({ state = "breathing", size = 28 }: { state?: "breathing" | "working" | "waiting" | "done"; size?: number }) {
  const spin = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loops: Animated.CompositeAnimation[] = [];
    if (state === "working") loops.push(Animated.loop(Animated.timing(spin, { toValue: 1, duration: 1400, easing: Easing.linear, useNativeDriver: true })));
    if (state !== "done")
      loops.push(
        Animated.loop(
          Animated.sequence([
            Animated.timing(pulse, { toValue: 1, duration: state === "waiting" ? 600 : 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
            Animated.timing(pulse, { toValue: 0, duration: state === "waiting" ? 600 : 1600, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
          ]),
        ),
      );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [state, spin, pulse]);
  const color = state === "waiting" ? C.waiting : state === "done" ? C.done : C.running;
  const r = size / 2;
  const dots = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2;
    return { x: r + Math.cos(a) * (r - 2.5), y: r + Math.sin(a) * (r - 2.5), o: 0.25 + 0.75 * (i / 12) };
  });
  const rotate = spin.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.82, 1.08] });
  return (
    <View style={{ width: size, height: size }} accessibilityLabel={`KAIROS ${state}`}>
      <Animated.View style={{ position: "absolute", width: size, height: size, transform: [{ rotate }] }}>
        <Svg width={size} height={size}>
          {dots.map((d, i) => (
            <Circle key={i} cx={d.x} cy={d.y} r={Math.max(1.1, size / 22)} fill={color} opacity={state === "working" ? d.o : 0.55} />
          ))}
        </Svg>
      </Animated.View>
      <Animated.View style={{ position: "absolute", left: size * 0.3, top: size * 0.3, width: size * 0.4, height: size * 0.4, borderRadius: size, backgroundColor: color, opacity: 0.9, transform: [{ scale }] }} />
    </View>
  );
}

/** The same faces the desktop gives agents: planner a blue droid, finance a green clover, and so on. */
const KNOWN: Record<string, [string, string]> = {
  planner: ["droid", "#2f7cf6"],
  finance: ["clover", "#16b67a"],
  engineering: ["mech", "#ff8a3d"],
  research: ["alien", "#7b61ff"],
  action: ["star", "#f5a623"],
  data: ["hexagon", "#00b3c7"],
  writer: ["flower", "#f0628f"],
  operator: ["pill", "#5c6bc0"],
};
const COLOURS = ["#14a89a", "#c56cf0", "#7cc242", "#ff5a5f", "#00b3c7", "#f5a623", "#2f7cf6"];

export function faceFor(agent: string): [string, string] {
  const role = agent.replace(/-agent.*$/, "").replace(/-[0-9a-f]{2,}$/, "").split("-")[0];
  if (KNOWN[role]) return KNOWN[role];
  let h = 0;
  for (const c of role) h = (h * 31 + c.charCodeAt(0)) | 0;
  return ["blob", COLOURS[Math.abs(h) % COLOURS.length]];
}

/** An agent's face. It hops while its process works, looks around while it waits, and dozes when it is done. */
export function BotFace({ agent, state, size = 40 }: { agent: string; state?: string; size?: number }) {
  const [shape, color] = faceFor(agent);
  const hop = useRef(new Animated.Value(0)).current;
  const st = (state ?? "").toUpperCase();
  const working = ["RUNNING", "READY", "CREATED", "INITIALIZING"].includes(st);
  const waiting = ["WAITING", "PAUSED", "BLOCKED"].includes(st);
  const asleep = !working && !waiting;
  useEffect(() => {
    if (asleep) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(hop, { toValue: 1, duration: working ? 380 : 900, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(hop, { toValue: 0, duration: working ? 380 : 900, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        Animated.delay(working ? 120 : 500),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [hop, working, asleep]);
  const translateY = hop.interpolate({ inputRange: [0, 1], outputRange: [0, working ? -size * 0.12 : 0] });
  const look = hop.interpolate({ inputRange: [0, 1], outputRange: [-size * 0.05, size * 0.05] });
  const body =
    shape === "droid" || shape === "mech" || shape === "pill" ? (
      <Rect x={4} y={8} width={32} height={28} rx={shape === "pill" ? 14 : 8} fill={color} />
    ) : shape === "clover" || shape === "flower" ? (
      <Path d="M20 4c5 0 8 4 8 8 4 0 8 3 8 8s-4 8-8 8c0 4-3 8-8 8s-8-4-8-8c-4 0-8-3-8-8s4-8 8-8c0-4 3-8 8-8z" fill={color} />
    ) : shape === "star" ? (
      <Path d="M20 3l5 10 11 2-8 8 2 12-10-6-10 6 2-12-8-8 11-2z" fill={color} />
    ) : shape === "hexagon" ? (
      <Path d="M20 3l15 9v16l-15 9-15-9V12z" fill={color} />
    ) : shape === "alien" ? (
      <Ellipse cx={20} cy={21} rx={16} ry={15} fill={color} />
    ) : (
      <Path d="M20 5c9 0 16 6 16 15s-5 16-16 16S4 29 4 20 11 5 20 5z" fill={color} />
    );
  return (
    <Animated.View style={{ width: size, height: size, transform: [{ translateY }] }} accessibilityLabel={`${agent} ${st.toLowerCase() || "idle"}`}>
      <Svg width={size} height={size} viewBox="0 0 40 40">
        {body}
        {shape === "droid" && <Line x1={20} y1={8} x2={20} y2={3} stroke={color} strokeWidth={2} />}
        {asleep ? (
          <>
            <Line x1={13} y1={21} x2={17} y2={21} stroke="#fff" strokeWidth={2} strokeLinecap="round" />
            <Line x1={23} y1={21} x2={27} y2={21} stroke="#fff" strokeWidth={2} strokeLinecap="round" />
          </>
        ) : null}
      </Svg>
      {!asleep && (
        <Animated.View style={{ position: "absolute", left: 0, right: 0, top: size * 0.44, flexDirection: "row", justifyContent: "center", gap: size * 0.14, transform: [{ translateX: waiting ? look : 0 }] }}>
          {[0, 1].map((i) => (
            <View key={i} style={{ width: size * 0.13, height: size * 0.17, borderRadius: size, backgroundColor: "#fff" }} />
          ))}
        </Animated.View>
      )}
    </Animated.View>
  );
}

/** A person: their initials on a colour from their email. */
export function Person({ name, email, size = 36 }: { name?: string | null; email: string; size?: number }) {
  const hues = ["#0d9488", "#2563eb", "#7c3aed", "#db2777", "#ea580c", "#16a34a", "#0891b2"];
  let h = 0;
  for (const c of email) h = (h * 31 + c.charCodeAt(0)) | 0;
  const initials = (name || email.split("@")[0]).split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
  return (
    <View style={{ width: size, height: size, borderRadius: size, backgroundColor: hues[Math.abs(h) % hues.length], alignItems: "center", justifyContent: "center" }}>
      <Text style={{ color: "#fff", fontWeight: "700", fontSize: size * 0.38 }}>{initials}</Text>
    </View>
  );
}

/** The KAIROS mark: four tesserae. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Rect x={2} y={2} width={9} height={9} rx={2} fill={C.brand} />
      <Rect x={13} y={2} width={9} height={9} rx={2} fill={C.brand} opacity={0.55} />
      <Rect x={2} y={13} width={9} height={9} rx={2} fill={C.brand} opacity={0.55} />
      <Rect x={13} y={13} width={9} height={9} rx={2} fill={C.text} opacity={0.85} />
    </Svg>
  );
}

export const s = StyleSheet.create({
  card: { backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: C.line, padding: 14, shadowColor: "#0f172a", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 1 },
  pill: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start" },
  pillText: { fontSize: 12, fontWeight: "600" },
  button: { minHeight: 46, borderRadius: 14, borderWidth: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 16 },
  buttonText: { fontSize: 16, fontWeight: "700" },
  title: { fontSize: 28, fontWeight: "800", color: C.text, letterSpacing: -0.6 },
  sub: { fontSize: 14, color: C.text2, marginTop: 2 },
  label: { fontSize: 12, fontWeight: "700", color: C.text2, letterSpacing: 0.6, textTransform: "uppercase", marginBottom: 6 },
  notice: { borderRadius: 14, padding: 12 },
  input: { minHeight: 48, borderRadius: 14, borderWidth: 1, borderColor: C.line, backgroundColor: C.card, paddingHorizontal: 14, fontSize: 16, color: C.text },
  mono: { fontFamily: mono },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
});
