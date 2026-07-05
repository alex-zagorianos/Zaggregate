import * as React from "react";
import { toast } from "sonner";
import {
  Briefcase,
  ExternalLink,
  UserRound,
  CalendarPlus,
  Pencil,
  Trash2,
  Plus,
  StickyNote,
  Loader2,
  Clock,
} from "lucide-react";

import {
  useApplication,
  useAddApplication,
  useUpdateApplication,
  useAddAppNote,
  useAddRound,
  useUpdateRound,
  useDeleteRound,
} from "@/api/queries";
import {
  ApiError,
  downloadIcs,
  type InterviewRound,
  type TimelineEntry,
} from "@/api/client";
import {
  emptyForm,
  formFromJob,
  showOffer,
  dirtyFields,
  createBody,
  isDirty,
  type AppForm,
} from "@/lib/app-fields";
import { firstBadDate, isValidScheduledAt } from "@/lib/date-validate";
import { statusLabel } from "@/lib/status";
import { StatusChip } from "@/components/status-chip";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { LoadingState, ErrorState } from "@/components/states";
import { NetworkBlockView } from "@/components/network-block";
import { OutreachActions } from "@/components/outreach-actions";
import { cn } from "@/lib/utils";

/* JobDialog — the create/edit application editor, rendered as a RIGHT-SIDE SHEET.
 *
 * Why a sheet, not a centered Dialog: this form is long (14 fields + a conditional
 * offer section + an interview-rounds sub-table + a status timeline). A centered
 * modal at 1280 either overflows the viewport height (scroll-inside-a-box, cramped)
 * or forces a tiny two-column grid. A fixed-width right rail that scrolls its body
 * reads like a proper detail panel and keeps the field rhythm calm — so we use the
 * Sheet primitive (built on the same Radix Dialog, so focus-trap/Esc/overlay are
 * identical). The rounds sub-CRUD uses a small nested Dialog.
 *
 * Modes:
 *   - CREATE (id === null): a blank form; Save → POST /api/applications; the
 *     cycle sections (rounds/timeline/offer/referral) are hidden until the row
 *     exists, mirroring the tk dialog.
 *   - EDIT (id is a number): loads GET /api/applications/<id> (row + timeline +
 *     rounds + referral + status vocabulary); Save → PATCH only the changed
 *     fields; the offer section appears when status is offer/accepted; rounds +
 *     timeline + add-note are available.
 *
 * Unsaved-changes guard: closing (Esc, overlay, X, Cancel) while the form is dirty
 * asks to confirm. Date fields are validated client-side to the tk regex before
 * save. Every mutation invalidates the coherent view set via the query hooks. */

export interface JobDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null = create mode; a number = edit that application. */
  appId: number | null;
}

export function JobDialog({ open, onOpenChange, appId }: JobDialogProps) {
  const isEdit = appId !== null;
  const detail = useApplication(open ? appId : null);
  const add = useAddApplication();
  const update = useUpdateApplication();

  // Working copy of the form + the pristine snapshot to diff against.
  const [form, setForm] = React.useState<AppForm>(() => emptyForm());
  const [original, setOriginal] = React.useState<AppForm>(() => emptyForm());
  const [confirmClose, setConfirmClose] = React.useState(false);

  // Seed the form when the dialog opens / the loaded row arrives.
  React.useEffect(() => {
    if (!open) return;
    if (!isEdit) {
      const blank = emptyForm();
      setForm(blank);
      setOriginal(blank);
      return;
    }
    if (detail.data?.job) {
      const loaded = formFromJob(detail.data.job);
      setForm(loaded);
      setOriginal(loaded);
    }
  }, [open, isEdit, detail.data?.job]);

  const statuses = detail.data?.statuses;
  const labels = detail.data?.status_labels;
  const dirty = isDirty(original, form);

  const set = <K extends keyof AppForm>(key: K, value: AppForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Guarded close: confirm if there are unsaved edits.
  const requestClose = React.useCallback(
    (next: boolean) => {
      if (!next && dirty) {
        setConfirmClose(true);
        return;
      }
      onOpenChange(next);
    },
    [dirty, onOpenChange],
  );

  const validate = (): boolean => {
    if (!form.title.trim() || !form.company.trim()) {
      toast.error("Title and company are required");
      return false;
    }
    const bad = firstBadDate(form);
    if (bad) {
      toast.error("Check the date", {
        description: `${bad.label} must be YYYY-MM-DD${bad.value ? ` (got “${bad.value}”)` : ""}.`,
      });
      return false;
    }
    return true;
  };

  const onSave = () => {
    if (!validate()) return;
    if (isEdit) {
      const changed = dirtyFields(original, form);
      if (Object.keys(changed).length === 0) {
        onOpenChange(false); // nothing to do
        return;
      }
      update.mutate(
        { id: appId as number, fields: changed },
        {
          onSuccess: () => {
            toast.success("Saved", {
              description: `${form.title} · ${form.company} updated.`,
            });
            onOpenChange(false);
          },
          onError: (e) =>
            toast.error("Couldn't save", {
              description:
                e instanceof ApiError ? e.message : "Please try again.",
            }),
        },
      );
    } else {
      add.mutate(createBody(form), {
        onSuccess: () => {
          toast.success("Added", {
            description: `${form.title} · ${form.company} is now tracked.`,
          });
          onOpenChange(false);
        },
        onError: (e) =>
          toast.error("Couldn't add", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      });
    }
  };

  const saving = add.isPending || update.isPending;
  const loadFailed = isEdit && detail.isError;

  return (
    <>
      <Sheet open={open} onOpenChange={requestClose}>
        <SheetContent
          className="flex flex-col gap-0 p-0"
          onInteractOutside={(e) => {
            if (dirty) e.preventDefault();
          }}
          onEscapeKeyDown={(e) => {
            if (dirty) {
              e.preventDefault();
              setConfirmClose(true);
            }
          }}
        >
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2.5">
              <Briefcase className="text-primary size-5" strokeWidth={2} />
              {isEdit ? "Edit application" : "Add a job"}
            </SheetTitle>
            <SheetDescription>
              {isEdit
                ? "Update the details, log interview rounds, and track the funnel."
                : "Track a role you found elsewhere. Title and company are required."}
            </SheetDescription>
          </SheetHeader>

          {isEdit && detail.isLoading ? (
            <div className="flex-1">
              <LoadingState />
            </div>
          ) : loadFailed ? (
            <div className="flex-1">
              <ErrorState
                title="Couldn't load this application"
                message={
                  detail.error instanceof ApiError
                    ? detail.error.message
                    : "It may have been deleted."
                }
                onRetry={() => detail.refetch()}
              />
            </div>
          ) : (
            <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
              <CoreFields
                form={form}
                set={set}
                statuses={statuses}
                labels={labels}
              />

              {showOffer(form.status) && <OfferSection form={form} set={set} />}

              {isEdit && detail.data?.referral ? (
                <ReferralHint hint={detail.data.referral} />
              ) : null}

              {isEdit && (
                <NetworkBlockView
                  company={form.company}
                  network={detail.data?.network}
                  id={appId as number}
                  source="application"
                />
              )}

              {isEdit && (
                <OutreachActions
                  appId={appId as number}
                  status={detail.data?.job?.status ?? form.status}
                  roundCount={detail.data?.rounds?.length ?? 0}
                />
              )}

              {isEdit && (
                <>
                  <RoundsSection
                    appId={appId as number}
                    rounds={detail.data?.rounds ?? []}
                  />
                  <TimelineSection timeline={detail.data?.timeline ?? []} />
                  <AddNoteRow appId={appId as number} />
                </>
              )}
            </div>
          )}

          <SheetFooter className="justify-between">
            <div className="text-muted-foreground text-xs">
              {dirty && !saving ? "Unsaved changes" : ""}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                onClick={() => requestClose(false)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={onSave} disabled={saving || loadFailed}>
                {saving && <Loader2 className="size-4 animate-spin" />}
                {isEdit ? "Save changes" : "Add job"}
              </Button>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={confirmClose}
        onOpenChange={setConfirmClose}
        title="Discard unsaved changes?"
        description="You've edited this application but haven't saved. Close anyway?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        destructive
        onConfirm={() => onOpenChange(false)}
      />
    </>
  );
}

// ── Core fields ───────────────────────────────────────────────────────────────

function Field({
  label,
  htmlFor,
  hint,
  children,
  className,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor} className="text-muted-foreground text-xs">
        {label}
        {hint && (
          <span className="text-muted-foreground/60 ml-1 font-normal">
            {hint}
          </span>
        )}
      </Label>
      {children}
    </div>
  );
}

function CoreFields({
  form,
  set,
  statuses,
  labels,
}: {
  form: AppForm;
  set: <K extends keyof AppForm>(key: K, value: AppForm[K]) => void;
  statuses: string[] | undefined;
  labels: Record<string, string> | undefined;
}) {
  // In create mode the status vocabulary isn't loaded (no GET-one), so fall back
  // to the loaded set OR a minimal starter — the backend validates on save.
  const statusOptions = statuses ?? [
    "interested",
    "applied",
    "phone_screen",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "ghosted",
  ];
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Field label="Title" htmlFor="jd-title" className="sm:col-span-2">
        <Input
          id="jd-title"
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          placeholder="e.g. Senior Backend Engineer"
          autoFocus
        />
      </Field>
      <Field label="Company" htmlFor="jd-company">
        <Input
          id="jd-company"
          value={form.company}
          onChange={(e) => set("company", e.target.value)}
          placeholder="e.g. Acme Corp"
        />
      </Field>
      <Field label="Location" htmlFor="jd-location">
        <Input
          id="jd-location"
          value={form.location}
          onChange={(e) => set("location", e.target.value)}
          placeholder="Remote · City · Hybrid"
        />
      </Field>
      <Field label="Salary" htmlFor="jd-salary">
        <Input
          id="jd-salary"
          value={form.salary_text}
          onChange={(e) => set("salary_text", e.target.value)}
          placeholder="e.g. $140k–170k"
        />
      </Field>
      <Field label="Status" htmlFor="jd-status">
        <div className="flex items-center gap-2">
          <Select
            id="jd-status"
            value={form.status}
            onChange={(e) => set("status", e.target.value)}
            className="flex-1"
          >
            {statusOptions.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s, labels)}
              </option>
            ))}
          </Select>
          <StatusChip status={form.status} labels={labels} />
        </div>
      </Field>
      <Field label="Job URL" htmlFor="jd-url" className="sm:col-span-2">
        <div className="relative">
          <Input
            id="jd-url"
            value={form.url}
            onChange={(e) => set("url", e.target.value)}
            placeholder="https://…"
            className="pr-9"
          />
          {form.url.trim() && (
            <a
              href={form.url}
              target="_blank"
              rel="noopener noreferrer"
              tabIndex={-1}
              aria-label="Open URL"
              className="text-muted-foreground hover:text-primary absolute top-1/2 right-2.5 -translate-y-1/2 transition-colors"
            >
              <ExternalLink className="size-4" />
            </a>
          )}
        </div>
      </Field>
      <Field label="Date applied" htmlFor="jd-date-applied" hint="YYYY-MM-DD">
        <Input
          id="jd-date-applied"
          value={form.date_applied}
          onChange={(e) => set("date_applied", e.target.value)}
          placeholder="2026-07-04"
          className="zg-num"
        />
      </Field>
      <Field label="Follow-up" htmlFor="jd-followup" hint="YYYY-MM-DD">
        <Input
          id="jd-followup"
          value={form.follow_up_date}
          onChange={(e) => set("follow_up_date", e.target.value)}
          placeholder="2026-07-11"
          className="zg-num"
        />
      </Field>
      <Field label="Deadline" htmlFor="jd-deadline" hint="YYYY-MM-DD">
        <Input
          id="jd-deadline"
          value={form.deadline}
          onChange={(e) => set("deadline", e.target.value)}
          placeholder="2026-08-01"
          className="zg-num"
        />
      </Field>
      <Field label="Contact" htmlFor="jd-contact">
        <Input
          id="jd-contact"
          value={form.contact}
          onChange={(e) => set("contact", e.target.value)}
          placeholder="Recruiter, referral, …"
        />
      </Field>
      <Field label="Notes" htmlFor="jd-notes" className="sm:col-span-2">
        <Textarea
          id="jd-notes"
          value={form.notes}
          onChange={(e) => set("notes", e.target.value)}
          placeholder="Anything worth remembering about this role…"
          rows={4}
        />
      </Field>
    </div>
  );
}

// ── Offer section (conditional) ───────────────────────────────────────────────

function OfferSection({
  form,
  set,
}: {
  form: AppForm;
  set: <K extends keyof AppForm>(key: K, value: AppForm[K]) => void;
}) {
  return (
    <section className="rounded-lg border border-[color-mix(in_oklab,var(--zg-status-offer)_40%,transparent)] bg-[color-mix(in_oklab,var(--zg-status-offer)_8%,transparent)] p-4">
      <h3 className="zg-serif text-foreground mb-3 flex items-center gap-2 text-sm font-semibold">
        <span
          aria-hidden
          className="size-2 rounded-full"
          style={{ backgroundColor: "var(--zg-status-offer)" }}
        />
        Offer details
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Amount" htmlFor="jd-offer-amount">
          <Input
            id="jd-offer-amount"
            value={form.offer_amount}
            onChange={(e) => set("offer_amount", e.target.value)}
            placeholder="e.g. $165,000"
            className="zg-num"
          />
        </Field>
        <Field label="Decide by" htmlFor="jd-offer-deadline" hint="YYYY-MM-DD">
          <Input
            id="jd-offer-deadline"
            value={form.offer_deadline}
            onChange={(e) => set("offer_deadline", e.target.value)}
            placeholder="2026-08-15"
            className="zg-num"
          />
        </Field>
        <Field
          label="Offer notes"
          htmlFor="jd-offer-notes"
          className="sm:col-span-2"
        >
          <Input
            id="jd-offer-notes"
            value={form.offer_notes}
            onChange={(e) => set("offer_notes", e.target.value)}
            placeholder="Equity, sign-on, negotiation notes…"
          />
        </Field>
      </div>
    </section>
  );
}

// ── Referral hint ─────────────────────────────────────────────────────────────

function ReferralHint({ hint }: { hint: string }) {
  return (
    <div className="text-primary bg-accent flex items-start gap-2 rounded-md px-3 py-2 text-sm">
      <UserRound className="mt-0.5 size-4 shrink-0" />
      <span className="leading-snug">{hint}</span>
    </div>
  );
}

// ── Interview rounds sub-CRUD ─────────────────────────────────────────────────

const ROUND_KINDS = ["phone", "tech", "onsite", "final", "other"];

function RoundsSection({
  appId,
  rounds,
}: {
  appId: number;
  rounds: InterviewRound[];
}) {
  const [editing, setEditing] = React.useState<InterviewRound | "new" | null>(
    null,
  );
  const del = useDeleteRound();

  const onIcs = async (r: InterviewRound) => {
    try {
      await downloadIcs(appId, r.id);
      toast.success("Calendar file downloaded", {
        description: "Open the .ics to add this round to your calendar.",
      });
    } catch (e) {
      toast.error("Couldn't create the calendar file", {
        description:
          e instanceof ApiError ? e.message : "Add a scheduled date first.",
      });
    }
  };

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="zg-serif text-foreground text-sm font-semibold">
          Interview rounds
        </h3>
        <Button variant="outline" size="sm" onClick={() => setEditing("new")}>
          <Plus className="size-3.5" />
          Add round
        </Button>
      </div>
      {rounds.length === 0 ? (
        <p className="text-muted-foreground rounded-md border border-dashed border-border px-3 py-4 text-center text-sm">
          No rounds logged yet.
        </p>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-md border border-border">
          {rounds.map((r) => (
            <li
              key={r.id}
              className="flex items-center gap-3 px-3 py-2.5 text-sm"
            >
              <span className="zg-num text-muted-foreground w-6 shrink-0 text-center font-semibold">
                {r.round_no}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-foreground font-medium capitalize">
                    {r.kind || "round"}
                  </span>
                  {r.outcome ? (
                    <span className="text-muted-foreground text-xs">
                      · {r.outcome}
                    </span>
                  ) : null}
                </div>
                <div className="text-muted-foreground zg-num text-xs">
                  {r.scheduled_at || "unscheduled"}
                  {r.interviewer ? ` · ${r.interviewer}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-0.5">
                <IconBtn
                  label="Add to calendar"
                  onClick={() => onIcs(r)}
                  icon={<CalendarPlus className="size-4" />}
                />
                <IconBtn
                  label="Edit round"
                  onClick={() => setEditing(r)}
                  icon={<Pencil className="size-4" />}
                />
                <IconBtn
                  label="Delete round"
                  tone="danger"
                  onClick={() =>
                    del.mutate(
                      { id: appId, rid: r.id },
                      {
                        onError: (e) =>
                          toast.error("Couldn't delete round", {
                            description:
                              e instanceof ApiError
                                ? e.message
                                : "Please try again.",
                          }),
                      },
                    )
                  }
                  icon={<Trash2 className="size-4" />}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing !== null && (
        <RoundDialog
          appId={appId}
          round={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

function RoundDialog({
  appId,
  round,
  onClose,
}: {
  appId: number;
  round: InterviewRound | null;
  onClose: () => void;
}) {
  const isEdit = round !== null;
  const add = useAddRound();
  const update = useUpdateRound();
  const [kind, setKind] = React.useState(round?.kind ?? "phone");
  const [scheduledAt, setScheduledAt] = React.useState(
    round?.scheduled_at ?? "",
  );
  const [interviewer, setInterviewer] = React.useState(
    round?.interviewer ?? "",
  );
  const [outcome, setOutcome] = React.useState(round?.outcome ?? "");
  const [notes, setNotes] = React.useState(round?.notes ?? "");

  const onSave = () => {
    if (!isValidScheduledAt(scheduledAt)) {
      toast.error("Check the date", {
        description: "Scheduled must start with YYYY-MM-DD.",
      });
      return;
    }
    const fields = {
      kind,
      scheduled_at: scheduledAt.trim(),
      interviewer: interviewer.trim(),
      outcome: outcome.trim(),
      notes: notes.trim(),
    };
    const onError = (e: unknown) =>
      toast.error("Couldn't save round", {
        description: e instanceof ApiError ? e.message : "Please try again.",
      });
    if (isEdit) {
      update.mutate(
        { id: appId, rid: round.id, fields },
        { onSuccess: onClose, onError },
      );
    } else {
      add.mutate({ id: appId, fields }, { onSuccess: onClose, onError });
    }
  };

  const busy = add.isPending || update.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="zg-serif">
            {isEdit ? "Edit round" : "Add interview round"}
          </DialogTitle>
          <DialogDescription>
            Log when it's scheduled and who you're meeting.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Kind" htmlFor="rd-kind">
            <Select
              id="rd-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              {ROUND_KINDS.map((k) => (
                <option key={k} value={k} className="capitalize">
                  {k}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Scheduled"
            htmlFor="rd-when"
            hint="YYYY-MM-DD or …THH:MM"
          >
            <Input
              id="rd-when"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              placeholder="2026-07-20T14:00"
              className="zg-num"
            />
          </Field>
          <Field label="Interviewer" htmlFor="rd-who">
            <Input
              id="rd-who"
              value={interviewer}
              onChange={(e) => setInterviewer(e.target.value)}
              placeholder="Name / panel"
            />
          </Field>
          <Field label="Outcome" htmlFor="rd-outcome">
            <Input
              id="rd-outcome"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              placeholder="Pending · Passed · …"
            />
          </Field>
          <Field label="Notes" htmlFor="rd-notes">
            <Textarea
              id="rd-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />
          </Field>
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSave} disabled={busy}>
            {busy && <Loader2 className="size-3.5 animate-spin" />}
            Save round
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────

function TimelineSection({ timeline }: { timeline: TimelineEntry[] }) {
  return (
    <section>
      <h3 className="zg-serif text-foreground mb-2 flex items-center gap-2 text-sm font-semibold">
        <Clock className="text-muted-foreground size-4" />
        Timeline
      </h3>
      {timeline.length === 0 ? (
        <p className="text-muted-foreground text-sm">No history yet.</p>
      ) : (
        <ol className="space-y-2.5">
          {timeline.map((e, i) => (
            <TimelineRow key={i} entry={e} />
          ))}
        </ol>
      )}
    </section>
  );
}

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const when = (entry.changed_at ?? "").slice(0, 16).replace("T", " ");
  return (
    <li className="flex gap-3">
      <span className="zg-num text-muted-foreground/80 w-[8.5rem] shrink-0 pt-0.5 text-xs">
        {when || "—"}
      </span>
      <div className="min-w-0 flex-1 text-sm">
        {entry.kind === "note" ? (
          <p className="text-foreground flex items-start gap-1.5 leading-snug">
            <StickyNote className="text-muted-foreground/70 mt-0.5 size-3.5 shrink-0" />
            {entry.note}
          </p>
        ) : (
          <p className="flex flex-wrap items-center gap-1.5 leading-snug">
            {entry.old_status ? (
              <StatusChip status={entry.old_status} dot={false} />
            ) : (
              <span className="text-muted-foreground text-xs">created</span>
            )}
            <span className="text-muted-foreground/60">→</span>
            <StatusChip status={entry.new_status} dot={false} />
            {entry.note ? (
              <span className="text-muted-foreground text-xs">
                ({entry.note})
              </span>
            ) : null}
          </p>
        )}
      </div>
    </li>
  );
}

// ── Add-note quick action ─────────────────────────────────────────────────────

function AddNoteRow({ appId }: { appId: number }) {
  const [note, setNote] = React.useState("");
  const addNote = useAddAppNote();

  const submit = () => {
    const trimmed = note.trim();
    if (!trimmed) return;
    addNote.mutate(
      { id: appId, note: trimmed },
      {
        onSuccess: () => {
          setNote("");
          toast.success("Note added");
        },
        onError: (e) =>
          toast.error("Couldn't add note", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
      },
    );
  };

  return (
    <div className="flex items-end gap-2">
      <Field label="Add a note" htmlFor="jd-add-note" className="flex-1">
        <Input
          id="jd-add-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Timestamped, without changing status…"
        />
      </Field>
      <Button
        variant="outline"
        onClick={submit}
        disabled={addNote.isPending || !note.trim()}
      >
        {addNote.isPending ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <StickyNote className="size-4" />
        )}
        Add
      </Button>
    </div>
  );
}

// ── shared icon button ────────────────────────────────────────────────────────

function IconBtn({
  label,
  onClick,
  icon,
  tone = "muted",
}: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  tone?: "muted" | "danger";
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "text-muted-foreground size-8",
        tone === "danger" ? "hover:text-destructive" : "hover:text-primary",
      )}
    >
      {icon}
    </Button>
  );
}
