# Findings

Every audit finding (code review, Playwright/visual QA, UX, a11y, design
detector) is one Markdown file: `findings/<type>/NNNN-<slug>.md`, numbered
across the whole folder. Evidence (screenshots, traces, logs) goes in
`findings/_evidence/<NNNN>/`.

Front matter:

```yaml
type: code | visual | ux | a11y | data | security | perf
severity: blocking | major | minor
status: open | fixed | wontfix
slice: <slice id or "baseline">
source: reviewer | playwright | impeccable | qa | human
evidence: [paths]
```

`blocking` stops a slice merging, `major` must be fixed before BETA_READY,
`minor` goes on the backlog. See AGENTS.md > Software-factory profile.
