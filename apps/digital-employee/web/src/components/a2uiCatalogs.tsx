import { basicCatalog, createComponentImplementation } from '@a2ui/react/v0_9';
import { Catalog, CommonSchemas } from '@a2ui/web_core/v0_9';
import { EqualsImplementation } from '@a2ui/web_core/v0_9/basic_catalog';
import { z } from 'zod';
import functionContract from '../catalogs/digital-employee-functions.json';
import {
  contractFunctionCodes,
  officialFunctionCodes,
  selectFunctionImplementations,
} from '../catalogFunctions.mjs';
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

const officialFunctions = selectFunctionImplementations(
  officialFunctionCodes(functionContract),
  basicCatalog.functions,
);
const projectFunctions = selectFunctionImplementations(
  contractFunctionCodes(functionContract),
  basicCatalog.functions,
  { equals: EqualsImplementation },
);

// The locked official renderer exposes 14 functions. The project Catalog adds only
// the Google SDK's existing equals implementation for declarative checks.
export const registeredCatalogs = [
  new Catalog(functionContract.baseCatalog.catalogId,
    [...basicCatalog.components.values()], officialFunctions, basicCatalog.themeSchema),
  new Catalog(functionContract.catalogId,
    [...basicCatalog.components.values(), Markdown, TextDownloadComponent],
    projectFunctions, basicCatalog.themeSchema),
];
