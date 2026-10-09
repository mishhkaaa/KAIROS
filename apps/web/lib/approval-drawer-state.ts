// When the approval drawer is open: the logic of the dress-rehearsal fixes, kept as pure functions so it's tested.
//  - It opens by itself the first time each approval turns up pending.
//  - After a decision it lingers briefly: the next action agent often asks within a second, and closing then reopening
//    mid-animation flickered (and left the closing sheet's overlay over the new card).
//  - Only approvals whose card actually rendered count as seen when it closes: one that arrives while the drawer is
//    closing must still open it by itself.

export interface DrawerState {
  /** Pending approval ids for this task. */
  pending: string[];
  /** Ids the user has already seen and closed the drawer on. */
  seen: string[];
  /** Opened from the banner. */
  manualOpen: boolean;
  /** Just resolved one; stay open a moment. */
  lingering: boolean;
}

export function drawerOpen({ pending, seen, manualOpen, lingering }: DrawerState): boolean {
  const unseen = pending.some((id) => !seen.includes(id));
  return (pending.length > 0 && (manualOpen || unseen)) || (lingering && (manualOpen || pending.length === 0));
}

/** `seen` after the user closes the drawer: only the pending approvals whose cards were on screen. */
export function seenAfterClose(seen: string[], pending: string[], rendered: string[]): string[] {
  return [...new Set([...seen, ...pending.filter((id) => rendered.includes(id))])];
}
