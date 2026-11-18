import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../src/cart.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 } }).outputText;
const { mergeCart, restoreCart } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const line = { variant_id: 1, product_id: 1, title: 'Producto', quantity: 1, unit_cents: 2500, variant: 'M', stock: 3, image: null };

test('cart groups repeated variants and rejects overselling or too many variants', () => {
  assert.equal(mergeCart([line], line)[0].quantity, 2);
  assert.throws(() => mergeCart([{ ...line, quantity: 3 }], line), /stock/);
  assert.throws(() => mergeCart(Array.from({ length: 20 }, (_, index) => ({ ...line, variant_id: index + 1 })), { ...line, variant_id: 21 }), /20/);
});
test('cart restoration validates public data and handles malformed storage', () => {
  assert.deepEqual(restoreCart('{broken'), []);
  assert.deepEqual(restoreCart(JSON.stringify([{ ...line, quantity: -1 }])), []);
  assert.deepEqual(restoreCart(JSON.stringify([line, line])), []);
  assert.deepEqual(restoreCart(JSON.stringify([line])), [line]);
});
