# Structural redesign after visual review

The user found the first polish too subtle and selected a clean modern direction:
reorganize layout, reduce borders, emphasize content and actions. This supersedes the
first pass's container layout, while preserving its accessible focus and responsive fixes.

Management uses a fixed 208px desktop navigation column, white main canvas, inline
metrics, compact labeled filters and horizontal asset rows instead of a card wall.
Skill rows retain status, owner, domain, version, workspace identity and detail actions.
Capability and Workflow lists use the same row family; component tables remain tables.
On small screens navigation becomes a compact top region and rows stack with labels.

Employee uses a 76px application rail and a 240px conversation column, with an open
white conversation canvas. Replies and the composer share a centered reading width.
Temporary forms have a single document border; process and technical details are secondary.
Navigation, notification counts, account/logout, draft behavior and auto continuation remain.

The two desktop concepts were produced with the built-in image generator, following the
Frontend App Builder workflow and UI/UX Pro Max guidance. This is a code-native interface;
no generated screenshot is used as functional UI. No dependency or backend changes.

Tokens: white canvas, cool-gray navigation #f5f7fb, blue primary #2563eb, body #172b4d,
muted #52647a and hairline #e5e9ef. System Chinese sans fonts, 28px titles, 14-16px
content, 12-14px chrome, visible focus and 44px primary targets.

Intentional concept deviations: retain actual data, existing labels and permissions rather
than generated sample identities, made-up descriptions, timestamps, workspace IDs, counts
or status values. Do not add an unsupported character counter or conversation preview.
Keep the existing text brand and schema-driven form controls. Fixture-only banners are QA
annotations, not product UI. All execution contracts and failure handling are unchanged.
