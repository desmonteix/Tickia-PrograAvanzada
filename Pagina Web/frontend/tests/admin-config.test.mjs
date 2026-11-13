import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/adminConfig.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
}).outputText;
const { campaignPayload, rewardPayload, settingsPayload, peruInput } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
);
const form = (values) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(values)) f.set(k, v);
  return f;
};
const values = {
  name: 'Campaña de prueba',
  starts_at: '2027-01-02T00:00',
  ends_at: '2027-02-02T00:00',
  enabled: 'on',
  listing_commission_rate: '5',
  registration_discount_rate: '7.5',
  seller_buyer_discount_rate: '10',
  seller_commission_rate: '0',
  reason: 'Campaña autorizada de prueba.',
};
test('admin campaign dates carry Peru timezone and displayed percentages become API fractions', () => {
  const payload = campaignPayload(form(values));
  assert.equal(payload.starts_at, '2027-01-02T00:00:00-05:00');
  assert.equal(payload.ends_at, '2027-02-02T00:00:00-05:00');
  assert.equal(payload.registration_discount_rate, 0.075);
  assert.equal(payload.seller_commission_rate, 0);
  assert.equal(payload.enabled, true);
  assert.equal(peruInput('2027-01-02T05:00:00Z'), '2027-01-02T00:00');
  for (const invalid of [
    { ends_at: values.starts_at },
    { listing_commission_rate: '100' },
    { seller_buyer_discount_rate: '51' },
    { reason: 'corta' },
    { name: 'AB' },
    { starts_at: '' },
  ])
    assert.throws(() => campaignPayload(form({ ...values, ...invalid })));
});
test('manual rewards require a selected existing user, reason and explicit optional seller commission', () => {
  const value = rewardPayload(
    form({
      user_id: 'b2d8c790-22a4-4c81-8ef2-5c073dac3f81',
      buyer_discount_rate: '10',
      seller_commission_rate: '',
      reason: values.reason,
    }),
  );
  assert.equal(value.buyer_discount_rate, 0.1);
  assert.equal(value.seller_commission_rate, null);
  assert.throws(() =>
    rewardPayload(form({ user_id: '../other', buyer_discount_rate: '10', reason: values.reason })),
  );
});
test('operation settings do not include provider credentials or payment enable flags', () => {
  const value = settingsPayload(
    form({
      registrations_enabled: 'on',
      maintenance_mode: 'on',
      announcement: '<b>Texto</b>',
      reason: values.reason,
      PAYMENT_ENABLED: 'true',
    }),
  );
  assert.deepEqual(value, {
    registrations_enabled: true,
    publications_enabled: false,
    purchases_enabled: false,
    maintenance_mode: true,
    announcement: '<b>Texto</b>',
    reason: values.reason,
  });
  assert.throws(() =>
    settingsPayload(form({ reason: values.reason, announcement: 'x'.repeat(501) })),
  );
});
