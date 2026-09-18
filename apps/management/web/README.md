# A2Flow management web

Minimal React/Vite console for the four registered management asset kinds.

## Publication workflow

- publication-plans only prepares a candidate and remains visibly PREPARED_NOT_PUBLISHED.
- Retained versions and the authoritative current/stable/gray selection come from GET .../versions. Version identifiers are lexical retained records, not a timestamped audit log.
- Administrators review an environment/channel/userId summary before explicit publication or configuration rollback.
- ONLINE STABLE warns that it clears gray routing. Rollback never compensates business effects.
- Mutations send the displayed serving digest as a CAS token. Stale state requires manual refresh and review; the client never retries automatically.
- Navigation and inputs lock while writes are pending. Draft or target edits invalidate a prepared candidate. A successful write clears the candidate before refresh; refresh failure is reported separately.
- Complex field JSON is held in a per-asset pending buffer, separate from the canonical draft. Apply is the only operation that changes canonical data; discard requires confirmation. Pending text survives asset and mode switches, blocks save/validate/prepare, and overlapping full JSON edits surface a conflict instead of overwriting it.
- Revision conflicts retain canonical and pending input. Reload requires confirmation; cancellation or failure preserves both, while a successful reload adopts the server revision and clears pending state.

- The dependency and publication-check panel is read-only. It separates published facts from ADMIN-only saved-draft diagnostics, marks unsaved local edits as excluded, and requires explicit refresh after edits, saves, publication, rollback, or source changes.
- Missing or truncated dependency evidence is never presented as ready. Exact release references retain their requested version and do not fall back to a current version.

Trusted identity and environment come only from the same-origin HttpOnly session.

## Offline checks

    npm ci --offline --ignore-scripts --no-audit --no-fund
    npm test
    npm run typecheck
    npm run build

Permanent browser regression uses an installed Playwright module and Chrome without starting a listener. It serves `dist` and synthetic fixtures through request interception and blocks all external requests:

    PLAYWRIGHT_PATH=/path/to/node_modules/playwright CHROME_PATH=/path/to/chrome npm run test:browser

The command fails clearly when either prerequisite is absent. It uses checked-in synthetic fixtures, controllable intercepted responses, and no backend or external network. Passing proves browser behavior against those fixture contracts, not backend validation. Screenshots are written to candidate-root `qa-output/`.
