import { toast } from "sonner";
import { FileDown } from "lucide-react";

import { downloadBundleFile, ApiError, type BundleFile } from "@/api/client";
import { cn } from "@/lib/utils";

/* A list of generated-file download buttons (resume / cover DOCX) — the web
 * replacement for the tk "reveal in explorer" (repo rule: all file handoffs are
 * gated HTTP downloads, never a shell-out). Each button fetches the file through the
 * output-dir-locked download route and triggers a browser save. Shared by the Apply
 * Queue (per-job + batch bundles) and the Resume tab. */

export interface FileDownloadsProps {
  files: BundleFile[];
  className?: string;
  /** A short label above the list (e.g. "Documents ready"). */
  label?: string;
}

export function FileDownloads({ files, className, label }: FileDownloadsProps) {
  if (files.length === 0) return null;

  const onDownload = (f: BundleFile) => {
    downloadBundleFile(f.download_url, f.name).catch((e) =>
      toast.error("Download failed", {
        description: e instanceof ApiError ? e.message : "Please try again.",
      }),
    );
  };

  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <p className="text-muted-foreground text-xs font-medium">{label}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {files.map((f) => (
          <button
            key={f.name}
            type="button"
            onClick={() => onDownload(f)}
            className="border-border hover:border-ring/40 hover:bg-secondary/50 inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors"
          >
            <FileDown className="text-primary size-4 shrink-0" />
            <span className="zg-num max-w-[16rem] truncate">{f.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
