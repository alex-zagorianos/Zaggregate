import * as React from "react";
import { Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useCreateProject } from "@/api/queries";
import { ApiError } from "@/api/client";
import { checkProjectName } from "@/lib/project-name";

/* New Project dialog — the web twin of gui.App._new_project / _new_person.
 *
 * Name (required) + Person (optional, "who is this search for?") + a "Switch to
 * it now" checkbox (default on). Submit POSTs /api/project/create; on success
 * WITH switch we route to /inbox — the app-level onboarding gate then re-reads
 * (the create mutation invalidated it) and the setup wizard appears for the
 * empty project, which IS the intended new-project flow. No resume is ever
 * copied (identity/PII isolation — the dad-data bug the tk flow guards against).
 *
 * A duplicate name (409) or empty name (400) is caught client-side first (live
 * hint) and, as a backstop, surfaced from the server error via a toast. */

export function NewProjectDialog({
  open,
  onOpenChange,
  existingSlugs,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existingSlugs: readonly string[];
}) {
  const [name, setName] = React.useState("");
  const [person, setPerson] = React.useState("");
  const [doSwitch, setDoSwitch] = React.useState(true);
  const navigate = useNavigate();
  const createProject = useCreateProject();

  // Reset the form each time the dialog opens so a prior attempt never lingers.
  React.useEffect(() => {
    if (open) {
      setName("");
      setPerson("");
      setDoSwitch(true);
    }
  }, [open]);

  const check = checkProjectName(name, existingSlugs);
  // Only nag once the user has typed something (don't flash "name required" on
  // an untouched field).
  const showError = name.trim().length > 0 && !check.valid;

  const submit = () => {
    if (!check.valid || createProject.isPending) return;
    createProject.mutate(
      {
        name: name.trim(),
        person: person.trim() || undefined,
        switch: doSwitch,
      },
      {
        onSuccess: (res) => {
          onOpenChange(false);
          if (doSwitch && res.active === res.slug) {
            if (res.pending_pinned) {
              // The switch is persisted but a run holds another project; it goes
              // live once that run finishes. Explain rather than look broken.
              toast.success("Project created", {
                description:
                  "It'll become active once the current run finishes.",
              });
            } else {
              toast.success("Project created — let's set it up");
              navigate("/inbox");
            }
          } else {
            toast.success("Project created", {
              description: "Pick it from the Project menu when you're ready.",
            });
          }
        },
        onError: (err) => {
          const msg =
            err instanceof ApiError
              ? err.message
              : "Couldn't create the project.";
          toast.error(msg);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="zg-serif">New project</DialogTitle>
          <DialogDescription>
            A project is one job search. Start a fresh one for a different role,
            location, or person.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-name">Name</Label>
            <Input
              id="np-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="e.g. Senior Product Roles"
              aria-invalid={showError || undefined}
              autoFocus
            />
            {showError ? (
              <span className="text-destructive text-xs">{check.reason}</span>
            ) : (
              name.trim() && (
                <span className="text-muted-foreground text-xs">
                  Saved as <span className="zg-num">{check.slug}</span>
                </span>
              )
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="np-person">Person (optional)</Label>
            <Input
              id="np-person"
              value={person}
              onChange={(e) => setPerson(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
              }}
              placeholder="Who is this search for?"
            />
            <span className="text-muted-foreground text-xs">
              Tag a name if you run searches for more than one person.
            </span>
          </div>

          <Label htmlFor="np-switch" className="cursor-pointer">
            <input
              id="np-switch"
              type="checkbox"
              className="accent-primary size-4"
              checked={doSwitch}
              onChange={(e) => setDoSwitch(e.target.checked)}
            />
            Switch to it now
          </Label>
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!check.valid || createProject.isPending}
            onClick={submit}
          >
            {createProject.isPending && (
              <Loader2 className="size-3.5 animate-spin" />
            )}
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
