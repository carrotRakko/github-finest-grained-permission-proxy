---
name: General Issue
about: A general-purpose template that starts with "why"
title: ''
labels: ''
assignees: ''
---

<!--
=============================================================================
Philosophy of this template
=============================================================================

This template is based on patterns extracted from existing issues.

Core principle: **Start with Pain (Why)**

A good issue explains "why this matters" first.
The reader should think "yes, this is a problem worth solving."

=============================================================================
Writing tips
=============================================================================

1. Write background as "pain"
   - NG: "Implement XXX" (starts with What)
   - OK: "We can't do XXX and it's causing problems" (starts with Why)

2. Explicitly state non-goals
   - For scope defense
   - Writing "we won't do this" prevents scope creep

3. Proposals can have multiple options
   - Don't force a single solution
   - Provide materials for the reader to make decisions

4. Define "done"
   - Without clear acceptance criteria, issues never close

5. Acknowledge risks
   - Writing "what might break" helps during review

=============================================================================
Section usage
=============================================================================

- Small issues: Background + Proposal + Related is enough
- Medium/large issues: Fill all sections
- Bug-like issues: Write repro steps, expected vs actual in "Current State"

When in doubt, fill it in. Remove if unnecessary.
=============================================================================
-->

## Background (Pain / Why)

<!--
Why is this issue needed? What problem are we facing?
Write it as "pain". The reader should think "yes, this is a problem."

Examples:
- "Currently we can't do XXX and it's blocking us"
- "XXX is ambiguous, causing repeated discussions"
- "XXX creates risk of incidents"
-->

## Goal

<!--
What do we want to achieve with this issue?
Describe the state where the pain is resolved.

Examples:
- "Enable XXX"
- "Document XXX so there's no ambiguity"
-->

## Non-goals

<!--
What we explicitly won't do in this issue.
For scope defense. Optional for small issues, recommended for medium/large.

Examples:
- "Full automation of XXX is out of scope"
- "Design changes for XXX will be a separate issue"
-->

## Current State (Observations)

<!--
What's the current situation? Write facts.

For bugs:
- Reproduction steps
- Expected behavior
- Actual behavior
- Environment

For other issues:
- Current implementation/config/operation state
- Related code/file locations
-->

## Proposal (Approach)

<!--
How to solve it.

Multiple options are fine. Don't force a single solution.
Pros/cons for each option helps decision-making.

Example:
### Option A: XXX
- Pros: ...
- Cons: ...

### Option B: YYY
- Pros: ...
- Cons: ...
-->

## Acceptance Criteria

<!--
What does "done" look like? Checklist format recommended.

Example:
- [ ] XXX is possible
- [ ] Tests pass
- [ ] Documentation is updated
-->

## Risks / Notes

<!--
What might break? Points to watch out for. Optional.

Examples:
- "Depends on XXX, need to check that too"
- "Be careful about XXX when deploying to production"
-->

## Related

<!--
Related issues, PRs, docs, external links.

Examples:
- #123
- docs/foo.md
- https://example.com/...
-->
