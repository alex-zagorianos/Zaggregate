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
} from "lucide-react";

import {
  downloadBackup,
  restoreBackup,
  endpoints,
  ApiError,
} from "@/api/client";
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

  const onCheckUpdates = () => {
    setCheckingUpdate(true);
    endpoints
      .checkForUpdates()
      .then((r) => {
        if (r.latest && r.newer) {
          toast.success(`Version ${r.latest} is available`, {
            description: "Open the releases page to download the update.",
            action: {
              label: "Open releases",
              onClick: () =>
                window.open(r.url, "_blank", "noopener,noreferrer"),
            },
          });
        } else if (r.latest) {
          toast.success("You're up to date", {
            description: `You're running the latest version (${r.current}).`,
          });
        } else {
          // latest=null: the check couldn't complete (offline / no releases yet).
          toast("Couldn't check for updates", {
            description: "No connection, or there are no releases yet.",
          });
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
            disabled={checkingUpdate}
          >
            {checkingUpdate ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4 opacity-70" />
            )}
            Check for updates
          </DropdownMenuItem>
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
