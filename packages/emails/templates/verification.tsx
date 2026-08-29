import { Button, Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

/**
 * Rendered to static HTML at build time with these defaults left as literal ``{{TOKEN}}`` placeholders in the
 * output — Django substitutes them per-recipient at send time
 * (keel/notifications/emails.py). Do not pass real props when building;
 * the defaults *are* the template.
 */
export function VerificationEmail(props: { verifyUrl?: string }) {
  const verifyUrl = props.verifyUrl ?? "{{VERIFY_URL}}";
  return (
    <Layout preview="Confirm your email address" heading="Confirm your email address">
      <Text>Click the button below to confirm your email address and finish signing up.</Text>
      <Button
        href={verifyUrl}
        style={{ background: "#18181b", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}
      >
        Confirm email
      </Button>
      <Text>Or paste this link into your browser: {verifyUrl}</Text>
      <Text>If you didn&apos;t request this, you can ignore this email.</Text>
    </Layout>
  );
}

export default VerificationEmail;
