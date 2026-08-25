import { Text } from "@react-email/components";
import * as React from "react";
import { Layout } from "./Layout";

export function SeatAddedEmail(props: { organizationName?: string; memberEmail?: string }) {
  const organizationName = props.organizationName ?? "{{ORGANIZATION_NAME}}";
  const memberEmail = props.memberEmail ?? "{{MEMBER_EMAIL}}";
  return (
    <Layout preview="A seat was added to your plan" heading="A seat was added to your plan">
      <Text>
        {memberEmail} joined {organizationName}, and your subscription&apos;s seat count updated to
        match. You&apos;ll see this reflected on your next invoice.
      </Text>
    </Layout>
  );
}

export default SeatAddedEmail;
