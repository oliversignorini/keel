/** A `<script type="application/ld+json">` block (phase-7.md 7.5). Server
 * component only — the data is fixed at render time, never user input, so
 * there is no XSS surface from `dangerouslySetInnerHTML` here. */
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    // eslint-disable-next-line no-restricted-syntax -- server component, data is fixed at render time, never user input.
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }} />
  );
}
