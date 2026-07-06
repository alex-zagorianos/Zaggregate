/* Project-name → slug + client-side validation for the New Project dialog.
 *
 * `slugify` mirrors workspace.slugify EXACTLY (lowercase, non-alnum runs → "-",
 * trim leading/trailing "-", empty → "project") so the dialog can (a) show the
 * derived slug as a live hint and (b) catch an empty name or a name that
 * collides with an existing project BEFORE the round-trip. The server re-checks
 * both (400 / 409) — this is a UX pre-check, never the authority.
 *
 * Pure + UI-free so the dialog just renders what these return.
 */

/** Mirror of workspace.slugify: `re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")`
 * with the same "" → "project" fallback. */
export function slugify(name: string): string {
  const s = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return s || "project";
}

export interface NameCheck {
  /** OK to submit (non-empty name that doesn't collide with an existing slug). */
  valid: boolean;
  /** The derived slug (always present, for the live hint). */
  slug: string;
  /** A short reason when !valid, else "". */
  reason: string;
}

/** Validate a typed name against the existing project slugs. Empty/whitespace →
 * invalid ("name required"); a name mapping to an existing slug → invalid
 * ("already exists"). Otherwise valid. */
export function checkProjectName(
  name: string,
  existingSlugs: readonly string[],
): NameCheck {
  const trimmed = name.trim();
  if (!trimmed) {
    return { valid: false, slug: "", reason: "Enter a name for the campaign." };
  }
  const slug = slugify(trimmed);
  if (existingSlugs.includes(slug)) {
    return {
      valid: false,
      slug,
      reason: "A project with that name already exists.",
    };
  }
  return { valid: true, slug, reason: "" };
}
