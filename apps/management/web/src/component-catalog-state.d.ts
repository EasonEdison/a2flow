export type PublishedComponentCatalogInspection =
  | { ok: true; catalogKey: string; protocolProfileRef: string; components: string[] }
  | { ok: false; error: string };

export function inspectPublishedComponentCatalog(
  detail: unknown,
  expectedKey: string,
): PublishedComponentCatalogInspection;
