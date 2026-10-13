# Design decisions

Reference: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill at
7246805992a42b7bba37d4cac83b01416f0c6c44. Read its SKILL.md and searched the local
design-system, UX and React knowledge data. The Minimalism & Swiss recommendation fits
a professional workspace. The generated marketing-page pattern does not fit these
application surfaces and is not used. No external fonts or skill code are bundled.

Shared palette: primary #2563eb, hover #1d4ed8, text #172b4d, muted #52647a,
canvas #f5f7fb, surface #ffffff, divider #dce3ed. Use system and Chinese sans-serif
fonts, a 4/8px spacing rhythm, restrained 8-12px corners and shallow shadows.

M keeps its existing authoring and release controls, with route-aware navigation,
visible filter labels and responsive list/editor/drawer layouts. B keeps its existing
Chat and Flow renderers, making results and pending actions easier to distinguish
while keeping execution and technical details accessible. SVG icons replace text glyphs
in structural navigation where practical.

The UI may rearrange and style content but must not fabricate status, discard action
errors, replay input, change submission/continuation behavior or weaken card contracts.

Validation uses complete production frontend builds and local browser previews with
explicit synthetic read-only fixtures. Check keyboard focus, disabled states, mobile
and desktop widths. Fixture evidence is not proof of a new public deployment.
