/**
 * Permission code constants, mirroring `Perm` in
 * apps/api/keel/organizations/permissions.py — the actual source of truth
 * (PRD §4 invariant 2: "Authorization is expressed only in
 * organizations/permissions.py"). This file holds no logic and enforces
 * nothing; it exists so `<Can code={Perm.ORG_UPDATE}>` reads the same way
 * on both sides instead of every call site spelling out a string literal
 * that could typo silently. `GET /api/v1/permissions/`
 * (getPermissionsRegistry in ./api.ts) is the runtime source of truth for
 * which codes exist — the role editor (settings/roles) reads from that
 * endpoint rather than from this file, precisely so it can never drift.
 */
export const Perm = {
  ORG_VIEW: "org.view",
  ORG_UPDATE: "org.update",
  ORG_DELETE: "org.delete",
  ORG_TRANSFER: "org.transfer",
  MEMBERS_VIEW: "members.view",
  MEMBERS_INVITE: "members.invite",
  MEMBERS_REMOVE: "members.remove",
  MEMBERS_CHANGE_ROLE: "members.change_role",
  ROLES_MANAGE: "roles.manage",
  BILLING_VIEW: "billing.view",
  BILLING_MANAGE: "billing.manage",
  AUDIT_VIEW: "audit.view",
  WIDGETS_VIEW: "widgets.view",
  WIDGETS_MANAGE: "widgets.manage",
} as const;
