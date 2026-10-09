import { folderOf } from "./kairos";

/** Folder colours: vivid jewel tones, one per /org folder, shared by the wallpaper's kairos and the run's document chips. */
export const FOLDER_HUES: Record<string, string> = {
  decisions: "#00b3c7",
  engineering: "#2f7cf6",
  finance: "#16b67a",
  inbox: "#ff5a5f",
  jira: "#7b61ff",
  meetings: "#c56cf0",
  people: "#f0628f",
  playbooks: "#14a89a",
  policies: "#7cc242",
  projects: "#ff8a3d",
  slack: "#f5a623",
  systems: "#5c6bc0",
  // What connectors, uploads and mounted folders bring in.
  github: "#57606a",
  calendar: "#1a73e8",
  uploads: "#e8590c",
  mnt: "#d9480f",
};

export const folderHue = (path: string) => FOLDER_HUES[folderOf(path)] ?? "#8a94a6";
