import { Button, Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

export function PaymentFailedEmail(props: { organizationName?: string; billingUrl?: string }) {
  const organizationName = props.organizationName ?? "{{ORGANIZATION_NAME}}";
  const billingUrl = props.billingUrl ?? "{{BILLING_URL}}";
  return (
    <Layout preview="Your payment didn't go through" heading="Your payment didn't go through">
      <Text>
        We couldn&apos;t charge the card on file for {organizationName}. Update your payment method
        to avoid losing access.
      </Text>
      <Button
        href={billingUrl}
        style={{ background: "#dc2626", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}
      >
        Update payment method
      </Button>
    </Layout>
  );
}

export default PaymentFailedEmail;
