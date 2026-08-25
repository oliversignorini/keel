import { Button, Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

export function ResetPasswordEmail(props: { resetUrl?: string }) {
  const resetUrl = props.resetUrl ?? "{{RESET_URL}}";
  return (
    <Layout preview="Reset your password" heading="Reset your password">
      <Text>We received a request to reset your password. Click below to choose a new one.</Text>
      <Button
        href={resetUrl}
        style={{ background: "#18181b", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}
      >
        Reset password
      </Button>
      <Text>Or paste this link into your browser: {resetUrl}</Text>
      <Text>If you didn&apos;t request this, you can ignore this email.</Text>
    </Layout>
  );
}

export default ResetPasswordEmail;
