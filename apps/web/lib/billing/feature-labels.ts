/**
 * Human labels for `Plan.entitlements.features` codes (phase-7.md 7.3,
 * defect 1: the pricing page rendered raw codes like `api_access`
 * straight from the API). This is the one place a label is registered —
 * Phase 9's `/new-resource` adds entitlements and should add its label
 * here, not wherever the pricing page happens to render them.
 *
 * A code with no entry here still renders — humanised from its snake_case
 * form — so a plan is never missing a feature just because its label
 * hasn't been registered yet.
 */
const FEATURE_LABELS: Record<string, string> = {
  api_access: "API access",
  audit_log: "Audit log",
  custom_roles: "Custom roles",
};

export function featureLabel(code: string): string {
  return (
    FEATURE_LABELS[code] ??
    code
      .split("_")
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  );
}
