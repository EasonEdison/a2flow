import { basicCatalog, createComponentImplementation } from '@a2ui/react/v0_9';
import { Catalog, CommonSchemas } from '@a2ui/web_core/v0_9';
import { z } from 'zod';
import { MarkdownContent } from './MarkdownContent';
import { TextDownload } from './TextDownload';

const Markdown = createComponentImplementation({
  name: 'Markdown',
  schema: z.object({ content: CommonSchemas.DynamicString }).strict(),
}, ({ props }) => <MarkdownContent markdown={props.content || ''} />);

const TextDownloadComponent = createComponentImplementation({
  name: 'TextDownload',
  schema: z.object({
    ...CommonSchemas.Checkable.shape,
    label: CommonSchemas.DynamicString,
    filename: CommonSchemas.DynamicString,
    mediaType: CommonSchemas.DynamicString,
    content: CommonSchemas.DynamicString,
  }).strict(),
}, ({ props }) => <TextDownload {...props} />);

// Explicit renderer registrations, not a generic claim that every published Catalog is supported.
export const registeredCatalogs = [
  basicCatalog,
  new Catalog('https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json',
    [...basicCatalog.components.values()], [...basicCatalog.functions.values()], basicCatalog.themeSchema),
  new Catalog('a2flow.digital-employee.pc.v1',
    [...basicCatalog.components.values(), Markdown, TextDownloadComponent],
    [...basicCatalog.functions.values()], basicCatalog.themeSchema),
];
