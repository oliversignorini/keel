import {
  Body,
  Container,
  Head,
  Heading,
  Html,
  Preview,
  Section,
  Text,
} from "@react-email/components";
import * as React from "react";

export function Layout(props: { preview: string; heading: string; children: React.ReactNode }) {
  return (
    <Html>
      <Head />
      <Preview>{props.preview}</Preview>
      <Body style={{ backgroundColor: "#f4f4f5", fontFamily: "sans-serif", padding: "24px 0" }}>
        <Container
          style={{
            backgroundColor: "#ffffff",
            borderRadius: "8px",
            padding: "32px",
            maxWidth: "480px",
          }}
        >
          <Heading as="h2" style={{ fontSize: "20px", marginBottom: "16px" }}>
            {props.heading}
          </Heading>
          <Section>{props.children}</Section>
          <Text style={{ color: "#71717a", fontSize: "12px", marginTop: "32px" }}>Keel</Text>
        </Container>
      </Body>
    </Html>
  );
}
