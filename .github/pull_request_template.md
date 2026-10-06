<Slice C10-02 -- issue #164 -- run hzb7c8>
<Why: one line. The problem and where it came from (contract, issue, run finding).>

## Summary
<!--
Visual menu (docs/04-commits-and-prs.md §4). Summary carries at least one
fenced visual, each next to the one or two lines of text it supports. Pick the
smallest view that makes the key point clear: one is normal, two is fine.

| visual         | use when                                                        | fence        |
|----------------|-----------------------------------------------------------------|--------------|
| pseudocode     | logic or an algorithm changed                                   | text         |
| call tree      | runtime control flow changed                                    | text         |
| component tree | UI structure changed (with state and module boundaries)         | text         |
| file tree      | file responsibilities moved, broad refactor                     | text         |
| Mermaid        | interaction, data flow or state machine                         | mermaid      |
| diff sketch    | what changes inside a shape that already exists (not code diff) | diff         |
| code           | mostly new, or a copyable target shape (CLI call, API, type)    | the language |
-->
<1-2 visuals from the menu above, each with one line of text>

## Evidence
- Before: <the test that failed, named, as pseudocode or its title> -- <absolute GitHub blob link to red.txt at the red commit>
- After: <same test passing> -- <absolute GitHub blob link to green.txt>
- Gates at HEAD: <local ci command> -> <result>

<details><summary>red -> green</summary>

```text
<the few failing lines from red.txt, then the passing lines from green.txt>
```
</details>

<UI changed (the diff touches the profile's ui_globs): before and after screenshots or a GIF, absolute links. Screenshots are the strongest evidence for a visual change.>

## Merge Danger
**Door:** two-way -- <reason>
**Blast radius:** module -- <who notices>

## Scope
<every changed path or glob, comma-separated; must match the slice scope + scope_implied + wiring_seams>

## Followups
- <deferred findings, leftovers, issues opened (#n)> or `None`

Closes #164
