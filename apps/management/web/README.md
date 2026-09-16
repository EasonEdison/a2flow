# A2Flow management web

Minimal React/Vite console for the four registered management asset kinds.

## Publication workflow

- publication-plans only prepares a candidate and remains visibly PREPARED_NOT_PUBLISHED.
- Retained versions and the authoritative current/stable/gray selection come from GET .../versions. Version identifiers are lexical retained records, not a timestamped audit log.
- Administrators review an environment/channel/userId summary before explicit publication or configuration rollback.
- ONLINE STABLE warns that it clears gray routing. Rollback never compensates business effects.
- Mutations send the displayed serving digest as a CAS token. Stale state requires manual refresh and review; the client never retries automatically.
- Navigation and inputs lock while writes are pending. Draft or target edits invalidate a prepared candidate. A successful write clears the candidate before refresh; refresh failure is reported separately.

Trusted identity and environment come only from the same-origin HttpOnly session.

## Offline checks

    npm ci --offline --ignore-scripts --no-audit --no-fund
    npm test
    npm run build

Browser/runtime evidence is a separate coordinator-owned gate; these commands do not start a listener.
