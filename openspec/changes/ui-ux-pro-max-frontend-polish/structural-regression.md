# Structural redesign validation — 2026-10-13

Source candidates: management `837444b001257a72f18d74bca8ee7379f93ddd99`, employee
`82e6959f4eaa48717ab13ba9af531a600fa94a56`. Both complete TypeScript/Vite builds passed.
No unit tests were run, per the user instruction. No dependency or backend change.

## Rendered checks

- Root inspected the real built frontends in a local browser using synthetic fixtures.
  This does not establish public deployment or real model execution.
- Management Skill list and Workflow editor fit 375, 768, 1024 and 1440px viewports.
  Capability and Workflow populated lists retained labeled metadata and actions.
  Skill search narrowed the fixture correctly. Empty component/Application fixtures
  establish layout only, not complete authoring or publication acceptance.
- A lazy-loaded Workflow style initially restored metric cards. The final candidate
  raises the existing shared selector specificity; root reloaded and confirmed inline metrics.
- Employee pending Chat fits 375, 768, 1024 and 1440px. Mobile navigation exposes all
  five entries plus account/logout; selecting Workflow closes the drawer. Completed
  Flow history keeps inputs and submit disabled. Keyboard submit focus is visible.
- The final employee candidate displays the desktop New conversation label and retains
  the mobile icon/accessibility label. The composer stays below the separate message
  viewport, inside the visible screen. Both final desktop pages have no console errors.
- A separate local mutation fixture verified explicit validation failure remains editable,
  corrected submission succeeds, account-isolated drafts, completed read-only refresh
  and history-only continuation. It recorded two action requests (rejected and corrected)
  and zero message requests. This is synthetic UI evidence, not a real model resume.

## Concept-to-render fidelity ledger

Root opened both full-page concepts and both final browser screenshots with the image
viewer, comparing overall layout, scale, hierarchy, typography, color and content.

| Comparison | Final result / deliberate difference |
| --- | --- |
| M navigation and canvas | Fixed 208px pale navigation, white content and top-right actions match the chosen structure. |
| M statistics and filters | Inline metrics and one compact labeled toolbar replace separated boxes; lazy Workflow override fixed. |
| M asset presentation | Horizontal separated rows match the direction. Metadata uses three columns and two rows to preserve owner and both statuses omitted by the concept. |
| B workspace proportions | 76px rail, 240px conversations and centered reading/composer width replace the former boxed shell. |
| B interaction hierarchy | Single document border, subdued process details and persistent composer match the concept. Existing schema still controls body titles and full-width submit. |
| Type and palette | System Chinese sans, stronger headings, cool-gray navigation and blue primary actions retained. No screenshot-backed UI. |
| Labels and data | Existing brand, actual payload fields and permissions retained. Generated avatars, timestamps, counts and conversation previews were not invented. |
| Responsive behavior | Desktop columns become compact mobile navigation and stacked content; horizontal overflow checks passed. |

The yellow fixture banner is a preview annotation and is not shipped product UI.
No pixel-perfect equivalence is claimed; the documented differences preserve product data
and schema contracts. Public deployment and public post-deployment verification remain pending.
