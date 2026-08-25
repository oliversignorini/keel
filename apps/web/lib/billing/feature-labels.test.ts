import { describe, expect, it } from "vitest";

import { featureLabel } from "./feature-labels";

describe("featureLabel", () => {
  it("maps a registered code to its human label", () => {
    expect(featureLabel("api_access")).toBe("API access");
    expect(featureLabel("audit_log")).toBe("Audit log");
    expect(featureLabel("custom_roles")).toBe("Custom roles");
  });

  it("humanises an unregistered code rather than showing it raw", () => {
    expect(featureLabel("sso_saml")).toBe("Sso Saml");
  });
});
