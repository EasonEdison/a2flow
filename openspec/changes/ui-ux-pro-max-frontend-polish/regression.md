# Regression evidence

2026-10-13. These checks use actual candidate frontend builds with explicit synthetic
fixtures on loopback. They do not claim a new public deployment or model execution.

Source: management 3aa65bd plus 387024b; employee b1944ab.
Both complete production builds, including TypeScript checks, passed.
No backend, API, parser, dependency or execution-semantic changes.

## Management

- Before: the public Skill list at viewport 375 had document width 1304.
- Candidate Skill, capability, component/Application lists and a capability creation
  drawer fit a 375 viewport without page-level horizontal overflow.
- Current navigation and visible filter labels were verified.
- Initial preview found Workflow editor title compression and 468px overflow at 375.
  The follow-up corrects title wrapping and metadata columns. Final editor document
  widths equal 375, 768, 1024 and 1440 at those respective viewport widths.
- Component/Application lists were verified in the synthetic empty state; populated
  complex asset details and actual publish operations were not exercised.

## Employee

- Completed Chat result, pending temporary form, navigation and Flow completed history
  rendered at desktop size. Chat and pending form fit a 375 viewport.
- Pending Chat document widths equal 768, 1024 and 1440 at those widths.
- Tab from the temporary textarea focuses Submit with a visible 3px outline.
- Completed Flow card opens with disabled fieldset and disabled submit button.
- Employee owner's separate local interaction fixture passed validation rejection,
  corrected submission, draft isolation, history-only continuation and read-only refresh.
  That fixture reported two action posts, zero message posts and no console errors.
- Root's inspected M/B console warning/error lists were empty.

Shared tokens: white on primary 5.17:1, text on white 14.1:1, muted on white
6.06:1 and muted on canvas 5.65:1. These are token checks, not a full accessibility audit.

Exact outgoing source diff check and Gitleaks passed; added-line sensitive-pattern scan
found no matches. No model invocation or real business-data mutation was used here.

Management archive SHA256:
f481c81c4918d9773769e226fa446bf512d3e22f74cfa39cc7da0d53bff752aa
Employee archive SHA256:
20c1b58f6c89cc8e2ec95d72e76acb7d8b13db2a80ddd8e1192cce983600d90f
