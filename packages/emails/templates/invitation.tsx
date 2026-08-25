import { Button, Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

export function InvitationEmail(props: { organizationName?: string; acceptUrl?: string }) {
  const organizationName = props.organizationName ?? "{{ORGANIZATION_NAME}}";
  const acceptUrl = props.acceptUrl ?? "{{ACCEPT_URL}}";
  return (
    <Layout
      preview={`You've been invited to ${organizationName}`}
      heading={`You've been invited to join ${organizationName}`}
    >
      <Text>Click below to accept the invitation and set up your account.</Text>
      <Button
        href={acceptUrl}
        style={{ background: "#18181b", color: "#fff", padding: "12px 20px", borderRadius: "6px" }}
      >
        Accept invitation
      </Button>
      <Text>Or paste this link into your browser: {acceptUrl}</Text>
    </Layout>
  );
}

export default InvitationEmail;
