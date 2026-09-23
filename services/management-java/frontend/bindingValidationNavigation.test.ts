import { strict as assert } from 'assert';
import { openBindingDebugPage, openBindingTracePage } from './bindingValidationNavigation';

const opened: Array<[string, string]> = [];
const recordWindowOpen = (url: string, target: string) => {
  opened.push([url, target]);
  return null;
};

openBindingDebugPage(recordWindowOpen);
openBindingTracePage(recordWindowOpen);

assert.deepEqual(opened, [
  ['/employee/', '_blank'],
  [
    '/employee/',
    '_blank',
  ],
]);

console.log('PASS binding validation navigation');
