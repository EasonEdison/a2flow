# A2Flow Management frontend

Run `npm ci`, `npm test`, and `npm run build` (which includes strict TypeScript checking). `npm run dev` listens on loopback. The production `dist` directory needs SPA fallback to `index.html`; same-origin `/api/management` requests must reach the Java management service. No backend proxy or public deployment is configured by this package.

The `/management` shell mounts the migrated Skill, Ability, component, A2UI Catalog/Application and Workflow pages. The A2UI five-stage editor remains intact. Styles include only management selectors from the source page styles and use Ant Design's public prefix.

This delivery is manual authoring only. M-side Agent assistants, generation/chat and AI debug evidence are paused; their requests fail explicitly before network activity. Manual editing, deterministic validation/previews, binding and direct publishing remain available. Runtime A2UI confirmation is unaffected. Environments are PRT/ONLINE; existing Java method and field names containing preprod remain compatibility identifiers.

Component previews load trusted published JavaScript bundles in CommonJS, AMD, global, or top-level namespace format. The local loader is not a security sandbox. It reports failed downloads, unknown dependencies, missing component exports and render errors. Bundles receive React, ReactDOM, safe JSON helpers and `@a2flow/image` (`Image` and default export, native HTML image attributes). Private image/CDN modules are not provided: such bundles must be rebuilt against the public image interface. No private CDN rewriting or telemetry is carried over.

Employee debug selection requires `GET /api/management/employees?pageNo=1&pageSize=...` returning `{ "list": [{ "employeeId": "...", "employeeCode": "...", "content": { "name": "..." } }], "total": 1 }`. This is an integration contract, not evidence that the endpoint exists. HTTP and schema failures stay visible in the debug page. Existing employee binding APIs also require backend integration.

Build success proves source compilation only. API authoring, publication, dynamic bundle delivery and original-page interaction acceptance still require a running backend and browser verification. Exclude `node_modules` and `dist` from source transfer.

System identity uses decimal-string `userId` and `userIdWhitelist` values on the wire to preserve 64-bit integer precision. An optional Host-supplied `<meta name="a2flow-user-id" content="...">` provides a display/form default only; backend authorization must use its authenticated principal. No private login cookies are read. Cookie credentials cannot be entered in capability verification. Legacy Cookie auth and RPC bindings are explicitly rejected before save/execution instead of being converted to HTTP or unauthenticated execution. `LOCAL_METHOD` remains a plugin type and requires a real backend handler registered for its `actionCode`.

See `dependency-licenses.json` for all locked dependency license declarations, including optional platform packages. The inventory contains 264 entries: MIT 252, BSD-3-Clause 3, ISC 4, Apache-2.0 3, BlueOak-1.0.0 1, and 0BSD 1; no missing declarations. Preserve applicable upstream notices when redistributing dependency code.
