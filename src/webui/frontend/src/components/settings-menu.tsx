import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Settings,
  PlugZap,
  Download,
  Upload,
  BookOpen,
  Loader2,
  AlertTriangle,
  RefreshCw,
  MessageSquare,
  BellRing,
} from "lucide-react";

import {
  downloadBackup,
  restoreBackup,
  endpoints,
  ApiError,
} from "@/api/client";
import { useNotifyHighFit, useSetNotifyHighFit } from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import {
  applyErrorMessage,
  checkMessage,
  classifyCheck,
  isTerminal,
  POLL_INTERVAL_MS,
  POLL_TIMEOUT_MS,
  progressLabel,
  shouldKeepPolling,
} from "@/lib/update-flow";

/* The high-fit notification toggle — a plain checkbox styled like the existing
 * inline Toggle idiom (tabs/companies/BuildListDialog.tsx), not a dropdown item
 * (a DropdownMenuItem's onSelect closes the menu, which fights a checkbox
 * click). Reads/writes GET+PUT /api/settings/notify via ui.settings on the
 * server, mirroring the theme toggle's persistence pattern exactly. */
function NotifyHighFitToggle() {
  const query = useNotifyHighFit();
  const mutation = useSetNotifyHighFit();
  const checked = query.data?.notify_high_fit ?? false;

  const onChange = (value: boolean) => {
    mutation.mutate(value, {
      onError: () =>
        toast.error("Couldn't save that setting", {
          description: "Please try again.",
        }),
    });
  };

  return (
    <div className="flex items-center gap-2 px-2 py-1.5 text-sm">
      <BellRing className="text-muted-foreground size-4 shrink-0" />
      <label
        htmlFor="notify-high-fit-toggle"
        className="flex flex-1 cursor-pointer items-center justify-between gap-3"
      >
        <span>Notify on high-fit matches (Windows)</span>
        <input
          id="notify-high-fit-toggle"
          type="checkbox"
          checked={checked}
          disabled={query.isLoading || mutation.isPending}
          onChange={(e) => onChange(e.target.checked)}
          className="accent-[var(--zg-accent)]"
        />
      </label>
    </div>
  );
}

/* The topbar gear menu — settings + data tools. Replaces the old single gear
 * that just navigated to Sources. Items:
 *   • Connect job sources  → /sources
 *   • Open the guide       → /guide
 *   • Download backup      → GET /api/backup/download (a zip of the data folder)
 *   • Restore from backup  → upload a zip, behind a SCARY confirm (destructive:
 *                            overwrites current data; the server snapshots first)
 *
 * Backup restore is the one destructive action in the app, so it's double-gated:
 * a file pick, then a ConfirmDialog that spells out the overwrite. The server
 * itself also requires confirm=true and takes a rollback snapshot. */

export function SettingsMenu() {
  const navigate = useNavigate();
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const [downloading, setDownloading] = React.useState(false);
  const [pendingFile, setPendingFile] = React.useState<File | null>(null);
  const [confirmRestore, setConfirmRestore] = React.useState(false);
  const [restoring, setRestoring] = React.useState(false);
  const [checkingUpdate, setCheckingUpdate] = React.useState(false);
  // Non-null while a Velopack download is in flight — drives the inline progress
  // line under the "Check for updates" item. null = nothing happening.
  const [updateLabel, setUpdateLabel] = React.useState<string | null>(null);
  const [updatePercent, setUpdatePercent] = React.useState(0);

  const onDownload = () => {
    setDownloading(true);
    downloadBackup()
      .then(() =>
        toast.success("Backup downloaded", {
          description:
            "Keep it somewhere safe — it can contain your saved API keys, so don't share it.",
        }),
      )
      .catch((e) =>
        toast.error("Couldn't build the backup", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setDownloading(false));
  };

  /* Poll /meta/update/progress until the download reaches a terminal phase, then
   * offer the restart. Resolves to true when the update is staged and ready.
   * Bounded by POLL_TIMEOUT_MS so a wedged download can't spin forever. */
  const pollUntilReady = React.useCallback(async (): Promise<boolean> => {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    for (;;) {
      const p = await endpoints.updateProgress();
      setUpdateLabel(progressLabel(p));
      setUpdatePercent(p.percent);
      if (isTerminal(p.phase)) return p.phase === "ready";
      if (!shouldKeepPolling(p.phase) || Date.now() > deadline) return false;
      await new Promise((r) => window.setTimeout(r, POLL_INTERVAL_MS));
    }
  }, []);

  /* "Restart to finish updating": the server replies 200 and THEN exits ~0.5s later,
   * so the window vanishes on purpose. Velopack's Update.exe swaps the app folder
   * and relaunches us with the same argv. Nothing to reload client-side. */
  const onApplyUpdate = React.useCallback(() => {
    endpoints
      .applyUpdate()
      .then((r) => {
        if (!r.ok) {
          toast.error("Couldn't apply the update", {
            description: applyErrorMessage(r),
          });
          return;
        }
        toast.success("Restarting to finish the update…", {
          description: "The window will close and reopen on the new version.",
          duration: 10_000,
        });
      })
      .catch((e) =>
        toast.error("Couldn't apply the update", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      );
  }, []);

  const offerRestart = React.useCallback(
    (version: string) => {
      toast.success(`Version ${version} is ready`, {
        description: "Restart to finish updating. Your data stays where it is.",
        duration: 30_000,
        action: { label: "Restart now", onClick: onApplyUpdate },
      });
    },
    [onApplyUpdate],
  );

  const startDownload = React.useCallback(
    (version: string) => {
      setUpdateLabel("Starting download…");
      setUpdatePercent(0);
      endpoints
        .downloadUpdate()
        .then(() => pollUntilReady())
        .then((ready) => {
          if (ready) offerRestart(version);
          else
            toast.error("The update didn't download", {
              description:
                "Your current version is untouched. Check your connection and try again.",
            });
        })
        .catch((e) =>
          toast.error("The update didn't download", {
            description:
              e instanceof ApiError ? e.message : "Please try again.",
          }),
        )
        .finally(() => {
          setUpdateLabel(null);
          setUpdatePercent(0);
        });
    },
    [offerRestart, pollUntilReady],
  );

  const onCheckUpdates = () => {
    setCheckingUpdate(true);
    endpoints
      .checkForUpdates()
      .then((r) => {
        const outcome = classifyCheck(r);
        switch (outcome.kind) {
          case "unmanaged":
            // A plain unzipped copy can't replace itself — send them to Releases.
            toast.success(`Version ${outcome.latest} is available`, {
              description: "Open the releases page to download the update.",
              action: {
                label: "Open releases",
                onClick: () =>
                  window.open(outcome.url, "_blank", "noopener,noreferrer"),
              },
            });
            break;
          case "update-ready-to-download":
            toast.success(`Version ${outcome.latest} is available`, {
              description:
                "Download it now? Nothing changes until you restart.",
              duration: 30_000,
              action: {
                label: "Download",
                onClick: () => startDownload(outcome.latest),
              },
            });
            break;
          case "already-downloaded":
            offerRestart(outcome.latest);
            break;
          case "up-to-date":
          case "unmanaged-current":
            toast.success("You're up to date", {
              description: checkMessage(outcome) ?? undefined,
            });
            break;
          case "unavailable":
            toast("Couldn't check for updates", {
              description: checkMessage(outcome) ?? undefined,
            });
            break;
        }
      })
      .catch((e) =>
        toast.error("Couldn't check for updates", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => setCheckingUpdate(false));
  };

  const onSendFeedback = () => {
    endpoints
      .feedbackTarget()
      .then((r) => {
        const body =
          "What happened (or what would help):\n\n\n" +
          "Steps to reproduce (if it's a bug):\n\n\n" +
          "—\nSent from Zaggregate.";
        const href =
          `mailto:${r.email}` +
          `?subject=${encodeURIComponent(r.subject)}` +
          `&body=${encodeURIComponent(body)}`;
        // Opens the user's own mail app — nothing is sent from the app itself.
        window.location.href = href;
      })
      .catch((e) =>
        toast.error("Couldn't open your mail app", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      );
  };

  const onPickFile = () => fileRef.current?.click();

  const onFileChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    // Reset the input so choosing the same file again re-fires change.
    e.target.value = "";
    if (!f) return;
    setPendingFile(f);
    setConfirmRestore(true);
  };

  const doRestore = () => {
    if (!pendingFile) return;
    const f = pendingFile;
    setRestoring(true);
    restoreBackup(f)
      .then((r) => {
        toast.success("Backup restored", {
          description: `${r.members} item${r.members === 1 ? "" : "s"} restored${
            r.rollback ? " (a rollback snapshot was saved first)" : ""
          }. Reloading…`,
        });
        // The whole data folder changed under the running app — the cleanest way
        // to reflect it everywhere is a reload (queries, active project, config).
        window.setTimeout(() => window.location.reload(), 1200);
      })
      .catch((e) =>
        toast.error("Couldn't restore that backup", {
          description: e instanceof ApiError ? e.message : "Please try again.",
        }),
      )
      .finally(() => {
        setRestoring(false);
        setPendingFile(null);
      });
  };

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={onFileChosen}
      />
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Settings and data"
              >
                <Settings className="size-4" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent>Settings &amp; data</TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="end" className="min-w-[15rem]">
          <DropdownMenuLabel>Settings</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => navigate("/sources")}>
            <PlugZap className="size-4 opacity-70" />
            Connect job sources
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => navigate("/guide")}>
            <BookOpen className="size-4 opacity-70" />
            Open the guide
          </DropdownMenuItem>
          <NotifyHighFitToggle />
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Your data</DropdownMenuLabel>
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              onDownload();
            }}
            disabled={downloading}
          >
            {downloading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4 opacity-70" />
            )}
            Download a backup
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              onPickFile();
            }}
          >
            <Upload className="size-4 opacity-70" />
            Restore from backup…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Help &amp; feedback</DropdownMenuLabel>
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              onCheckUpdates();
            }}
            disabled={checkingUpdate || updateLabel !== null}
          >
            {checkingUpdate || updateLabel !== null ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4 opacity-70" />
            )}
            Check for updates
          </DropdownMenuItem>
          {/* Inline download progress. Rendered outside a DropdownMenuItem so it is
              not focusable and a stray Enter can't re-trigger the check. */}
          {updateLabel !== null && (
            <div
              className="px-2 py-1.5"
              role="status"
              aria-live="polite"
              aria-label={updateLabel}
            >
              <div className="text-xs text-muted-foreground">{updateLabel}</div>
              <div
                className="mt-1 h-1 w-full overflow-hidden rounded bg-muted"
                role="progressbar"
                aria-valuenow={updatePercent}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full bg-primary transition-[width] duration-200"
                  style={{ width: `${updatePercent}%` }}
                />
              </div>
            </div>
          )}
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              onSendFeedback();
            }}
          >
            <MessageSquare className="size-4 opacity-70" />
            Send feedback
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirmRestore}
        onOpenChange={(o) => {
          setConfirmRestore(o);
          if (!o) setPendingFile(null);
        }}
        title="Restore and overwrite your data?"
        destructive
        description={
          <span className="flex flex-col gap-2">
            <span className="text-foreground flex items-center gap-2 font-medium">
              <AlertTriangle className="size-4 shrink-0 text-destructive" />
              This replaces your current inbox, tracker, and settings.
            </span>
            <span>
              Restoring from{" "}
              <span className="zg-num text-foreground">
                {pendingFile?.name}
              </span>{" "}
              overwrites everything with the backup's contents. We save a
              rollback snapshot of your current data first, but this can't be
              undone from the app. The page will reload when it's done.
            </span>
          </span>
        }
        confirmLabel={restoring ? "Restoring…" : "Overwrite my data"}
        cancelLabel="Cancel"
        onConfirm={doRestore}
      />
    </>
  );
}
