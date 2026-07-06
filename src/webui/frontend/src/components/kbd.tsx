import * as React from "react";

/* The single-letter keyboard-shortcut hint chip (t / d / o / …), shown inline in
 * a tab's subtitle sentence ("Every match, ready to triage. t track, d
 * dismiss…") and reused verbatim across Inbox, Top Picks, Search, and Apply
 * Queue — the same four tabs whose triage shortcuts it documents. */
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="border-border bg-secondary text-foreground zg-num mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 text-[0.7rem]">
      {children}
    </kbd>
  );
}

/** One t/d/o triage action for ShortcutHint: the key letter + its verb label
 * (e.g. {key:"t", label:"track"} → "t track"). */
export interface ShortcutAction {
  key: string;
  label: string;
}

/** The standardized shortcut-hint sentence shape shared by Inbox, Top Picks,
 * Search, and Apply Queue's subtitle line:
 *
 *   {lead} {verb} {Kbd}action1, {Kbd}action2, {Kbd}action3 {tail}
 *
 * `verb` carries each tab's own lead-in ("Triage with", "Make tailored docs,
 * then", …) so the four tabs keep their exact original wording while sharing
 * one sentence template; `actions` and `tail` vary per tab (Queue's actions
 * are mark-applied/dismiss/open, not track/dismiss/open). */
export function ShortcutHint({
  lead,
  verb,
  actions,
  tail,
}: {
  /** The sentence's opening clause, e.g. "Every match, ready to triage." */
  lead: string;
  /** The clause introducing the shortcuts, e.g. "Triage with" or "" to omit. */
  verb?: string;
  actions: ShortcutAction[];
  /** Trailing clause after the last action, e.g. "— or use the buttons." */
  tail?: string;
}) {
  return (
    <>
      {lead}
      {verb ? ` ${verb} ` : " "}
      {actions.map((a, i) => (
        <React.Fragment key={a.key}>
          <Kbd>{a.key}</Kbd> {a.label}
          {i < actions.length - 1 ? ", " : " "}
        </React.Fragment>
      ))}
      {tail}
    </>
  );
}
