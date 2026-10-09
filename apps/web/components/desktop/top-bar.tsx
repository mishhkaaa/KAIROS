"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell, LogOut, Search, Settings2, Smartphone, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { Menubar } from "radix-ui";
import { useState, useSyncExternalStore } from "react";
import { useClient } from "@/app/providers";
import { PairPhone, PersonAvatar, useSession } from "@/components/session";
import { APPS, type AppId } from "@/lib/desktop/routes";
import type { Win } from "@/lib/desktop/windows";
import { isActive } from "@/lib/events";
import { cn } from "@/lib/utils";
import { AppTile } from "./app-icons";
import { usePendingApprovals, useResources, useTasks } from "./hooks";
import { Mark } from "./logo";
import { Orb } from "./orb";
import { DOCK_APPS, KEYS } from "./shortcuts";

const subscribeClock = (tick: () => void) => {
  const t = setInterval(tick, 10_000);
  return () => clearInterval(t);
};
const clockNow = () => new Date().toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export interface MenuActions {
  spotlight: () => void;
  close: () => void;
  minimize: () => void;
  zoom: () => void;
  desktop: () => void;
  shortcuts: () => void;
  openApp: (app: AppId) => void;
  focusWindow: (key: string) => void;
  boot: () => void;
}

const content = "panel z-[7000] min-w-56 rounded-[12px] p-1 text-[13px] text-foreground";
const item =
  "flex cursor-default select-none items-center gap-2 rounded-[5px] px-2.5 py-1 outline-none data-[highlighted]:bg-brand data-[highlighted]:text-white data-[disabled]:opacity-40";

function Item({ label, keys, onSelect, disabled, icon }: { label: string; keys?: string; onSelect?: () => void; disabled?: boolean; icon?: React.ReactNode }) {
  return (
    <Menubar.Item className={item} onSelect={onSelect} disabled={disabled}>
      {icon}
      <span className="flex-1">{label}</span>
      {keys && <kbd className="font-mono text-[11px] opacity-60">{keys}</kbd>}
    </Menubar.Item>
  );
}

function Menu({ label, bold, children }: { label: React.ReactNode; bold?: boolean; children: React.ReactNode }) {
  return (
    <Menubar.Menu>
      <Menubar.Trigger className={cn("rounded-md px-2 py-0.5 outline-none hover:bg-surface-3 data-[state=open]:bg-surface-3", bold && "font-semibold")}>{label}</Menubar.Trigger>
      <Menubar.Portal>
        <Menubar.Content className={content} align="start" sideOffset={5}>
          {children}
        </Menubar.Content>
      </Menubar.Portal>
    </Menubar.Menu>
  );
}

const Sep = () => <Menubar.Separator className="mx-2 my-1 h-px bg-hairline" />;

/** The macOS-style menu bar: the system menu, the front app's name and its menus on the left; status items on the right. */
export function TopBar({ front, wins, actions, compact }: { front?: Win; wins: Win[]; actions: MenuActions; compact: boolean }) {
  const client = useClient();
  const { theme, setTheme } = useTheme();
  const pending = usePendingApprovals().data?.length ?? 0;
  const running = (useTasks().data ?? []).filter((t) => isActive(t.status)).length;
  const gpu = useResources().data?.gpu;
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => client.status(), refetchInterval: 15_000 });
  const clock = useSyncExternalStore(subscribeClock, clockNow, () => "");
  const appName = front ? (front.app === "task" ? "Task" : APPS[front.app].title) : "Desktop";
  // A shell-style path for the front window: ~/tasks/T-1c15, ~/knowledge?path=…
  const crumb = front ? `~${front.url.split("?")[0]}` : "~";
  const up = status.data?.ready;
  const { me, signOut, switchUser } = useSession();
  const [pairing, setPairing] = useState(false);

  return (
    <header className="chrome relative z-[5000] flex h-[30px] shrink-0 items-center gap-1 border-x-0 border-t-0 px-2.5 text-[13px] text-foreground">
      <Menubar.Root className="flex items-center gap-0.5">
        <Menu label={<span className="flex items-center gap-1.5"><Mark className="size-4" /><span className="font-mono text-[12px] font-semibold">kairos</span></span>}>
          <Item label="About KAIROS" disabled />
          {status.data && <Item label={`Kernel ${status.data.version} · contract ${status.data.contract_version}`} disabled />}
          <Sep />
          <Menubar.RadioGroup value={theme ?? "light"} onValueChange={setTheme}>
            {["light", "dark", "system"].map((t) => (
              <Menubar.RadioItem key={t} value={t} className={item}>
                <span className="w-3 text-center">{theme === t ? "•" : ""}</span>
                <span className="capitalize">{t} appearance</span>
              </Menubar.RadioItem>
            ))}
          </Menubar.RadioGroup>
          <Sep />
          <Item label="Keyboard shortcuts" keys={KEYS.shortcuts} onSelect={actions.shortcuts} />
          <Item label="Restart (boot screen)" onSelect={actions.boot} />
        </Menu>
        <span className="mx-1 hidden max-w-[28vw] truncate font-mono text-[12px] text-text-2 md:inline" title={front?.url}>{crumb}</span>
        <Menu label={appName} bold>
          <Item label={`About ${appName}`} disabled />
          <Sep />
          <Item label="Close window" keys={KEYS.close} onSelect={actions.close} disabled={!front} />
        </Menu>
        {!compact && (
          <>
            <Menu label="File">
              <Item label="New task…" keys={KEYS.spotlight} onSelect={actions.spotlight} />
              <Item label="Open…" keys="Ctrl K" onSelect={actions.spotlight} />
              <Sep />
              <Item label="Close window" keys={KEYS.close} onSelect={actions.close} disabled={!front} />
            </Menu>
            <Menu label="Go">
              {DOCK_APPS.map((a, i) => (
                <Item key={a} label={APPS[a].title} keys={`Alt ${i + 1}`} onSelect={() => actions.openApp(a)} icon={<AppTile app={a} size={16} />} />
              ))}
            </Menu>
            <Menu label="Window">
              <Item label="Minimise" keys={KEYS.minimize} onSelect={actions.minimize} disabled={!front} />
              <Item label="Zoom" keys={KEYS.zoom} onSelect={actions.zoom} disabled={!front} />
              <Item label="Show desktop" keys={KEYS.desktop} onSelect={actions.desktop} />
              <Item label="Switch windows" keys={KEYS.switch} disabled />
              {wins.length > 0 && <Sep />}
              {wins.map((w) => (
                <Item key={w.key} label={w.app === "task" ? `Task ${w.key.slice(5)}` : APPS[w.app].title} onSelect={() => actions.focusWindow(w.key)} icon={<AppTile app={w.app} size={16} />} />
              ))}
            </Menu>
            <Menu label="Help">
              <Item label="Keyboard shortcuts" keys={KEYS.shortcuts} onSelect={actions.shortcuts} />
            </Menu>
          </>
        )}
      </Menubar.Root>

      <div className="ml-auto flex items-center gap-1 font-mono text-[12px]">
        <span className="hidden items-center gap-1.5 px-1.5 text-text-2 lg:flex" title={up ? "kernel ready" : "kernel starting"}>
          <span className={cn("size-1.5 rounded-full", up ? "bg-st-running" : "bg-st-waiting")} aria-hidden />
          kernel {status.data?.version ?? ""}
        </span>
        <button type="button" onClick={actions.spotlight} className="bar-btn px-2" aria-label="Ask KAIROS (Alt Space)">
          <Search className="size-3.5" />
        </button>
        {running > 0 && (
          <Link href="/tasks" className="bar-btn gap-1.5 px-2" title="Running tasks">
            <Orb state="working" label="tasks running" />
            <span className="font-mono text-xs">{running}</span>
          </Link>
        )}
        {gpu && !compact && (
          <Link href="/system" className="bar-btn gap-1.5 px-2 font-mono text-xs tabular-nums" title={gpu.name}>
            GPU {gpu.utilization.toFixed(0)}% · {(gpu.memory_used_mb / 1024).toFixed(1)} GB
          </Link>
        )}
        <Link
          href="/approvals"
          aria-label={pending ? `${pending} approvals waiting` : "No approvals waiting"}
          className={cn("bar-btn gap-1 px-2", pending > 0 && "bg-st-waiting text-white hover:bg-st-waiting/90")}
        >
          <Bell className="size-3.5" />
          {pending > 0 && <span className="font-mono text-xs font-bold">{pending}</span>}
        </Link>
        <span className="whitespace-nowrap px-1.5 tabular-nums">{clock}</span>
        {me && (
          <Menubar.Root className="flex items-center">
            <Menubar.Menu>
              <Menubar.Trigger className="flex items-center gap-1.5 rounded-md py-0.5 pr-1.5 pl-0.5 font-sans outline-none hover:bg-surface-3 data-[state=open]:bg-surface-3" aria-label={`Signed in as ${me.user.email}`}>
                <PersonAvatar name={me.user.name} email={me.user.email} url={me.user.avatar_url} size={20} />
                {!compact && <span className="max-w-32 truncate text-[12.5px] font-medium">{me.org?.name ?? me.user.email}</span>}
              </Menubar.Trigger>
              <Menubar.Portal>
                <Menubar.Content className={content} align="end" sideOffset={5}>
                  <div className="flex items-center gap-2.5 px-2.5 py-2">
                    <PersonAvatar name={me.user.name} email={me.user.email} url={me.user.avatar_url} size={34} />
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{me.user.name || me.user.email}</p>
                      <p className="truncate text-xs text-text-2">{me.user.email}</p>
                    </div>
                  </div>
                  {me.org && (
                    <p className="mx-2.5 mb-1.5 flex items-center justify-between gap-3 rounded-md bg-surface-2 px-2 py-1 text-xs">
                      <span className="truncate font-medium">{me.org.name}</span>
                      <span className="font-mono text-text-2">{me.role}</span>
                    </p>
                  )}
                  <Sep />
                  <Item label="Organization" icon={<Users className="size-3.5" />} onSelect={() => actions.openApp("organization")} />
                  <Item label="Settings" keys={KEYS.settings} icon={<Settings2 className="size-3.5" />} onSelect={() => actions.openApp("settings")} />
                  <Sep />
                  <Item label="Sign in on your phone…" icon={<Smartphone className="size-3.5" />} onSelect={() => setPairing(true)} />
                  <Item label="Switch user…" icon={<UserRound className="size-3.5" />} onSelect={switchUser} />
                  <Item label={me.mode === "google" ? "Sign out" : "Sign out (lock)"} icon={<LogOut className="size-3.5" />} onSelect={signOut} />
                </Menubar.Content>
              </Menubar.Portal>
            </Menubar.Menu>
          </Menubar.Root>
        )}
      </div>
      {pairing && <PairPhone onClose={() => setPairing(false)} />}
    </header>
  );
}
