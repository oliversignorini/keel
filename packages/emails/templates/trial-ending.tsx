import { Button, Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

export function TrialEndingEmail(props: {
  organizationName?: string;
  billingUrl?: string;
  trialEndDate?: string;
}) {
  const organizationName = props.organizationName ?? "{{ORGANIZATION_NAME}}";
  const billingUrl = props.billingUrl ?? "{{BILLING_URL}}";
  const trialEndDate = props.trialEndDate ?? "{{TRIAL_END_DATE}}";
  return (
    <Layout preview="Your trial is ending soon" heading="Your trial is ending soon">
      <Text>
        {organizationName}&apos;s trial ends on {trialEndDate}. Add a payment method to keep access
        without interruption.
      </Text>
      <Button
        href={billingUrl}
        style={{ background: "#18181b", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}
      >
        Manage billing
      </Button>
    </Layout>
  );
}

export default TrialEndingEmail;
