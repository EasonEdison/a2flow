import { strict as assert } from 'node:assert';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { evaluateComponent } from './DynamicComponent';

const cases = [
  'exports.Card = function Card(p) { return React.createElement("strong", null, p.title); };',
  'module.exports = function Card(p) { return require("react").createElement("strong", null, p.title); };',
  'exports.default = (p) => React.createElement("strong", null, p.title);',
  'define(["react"], function(R) { return { Card: p => R.createElement("strong", null, p.title) }; });',
  'window.Cards = { Card: p => React.createElement("strong", null, p.title) };',
  'const Cards = { Card: p => React.createElement("strong", null, p.title) };',
];
for (const source of cases) {
  const Card = evaluateComponent(source, 'Card', { React, react: React });
  assert.equal(renderToStaticMarkup(React.createElement(Card, { title: 'Loaded' })), '<strong>Loaded</strong>');
}
assert.throws(() => evaluateComponent('require("missing-module")', 'Card', {}), /dependency "missing-module" is not available/);
assert.throws(() => evaluateComponent('exports.Other = () => null;', 'Card', {}), /Component "Card" was not found/);
console.log('PASS dynamic bundle exports, rendering, missing dependency and missing component');
