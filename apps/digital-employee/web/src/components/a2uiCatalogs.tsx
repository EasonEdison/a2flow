import { basicCatalog, createComponentImplementation } from '@a2ui/react/v0_9';
import { Catalog, CommonSchemas } from '@a2ui/web_core/v0_9';
import { z } from 'zod';
import { MarkdownContent } from './MarkdownContent';

const Markdown = createComponentImplementation({
  name: 'Markdown',
  schema: z.object({ content: CommonSchemas.DynamicString }).strict(),
}, ({ props }) => <MarkdownContent markdown={props.content || ''} />);

// Explicit renderer registrations, not a generic claim that every published Catalog is supported.
export const registeredCatalogs = [
  basicCatalog,
  new Catalog('https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json',
    [...basicCatalog.components.values()], [...basicCatalog.functions.values()], basicCatalog.themeSchema),
  new Catalog('a2flow.digital-employee.pc.v1',
    [...basicCatalog.components.values(), Markdown], [...basicCatalog.functions.values()], basicCatalog.themeSchema),
];
