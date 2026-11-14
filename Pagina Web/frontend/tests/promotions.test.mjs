import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../src/promotions.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
}).outputText;
const {
  referralCode,
  rememberReferral,
  clearReferral,
  previewAmount,
  verifyQuote,
  inviteUrl,
  reservationReleased,
} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const id = 'b2d8c790-22a4-4c81-8ef2-5c073dac3f81';

test('referral attribution accepts one public code and survives navigation until signup commits', () => {
  const values = new Map();
  const storage = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
    removeItem: (k) => values.delete(k),
  };
  assert.equal(rememberReferral('?ref=Invite_123', storage), 'Invite_123');
  assert.equal(rememberReferral('', storage), 'Invite_123');
  assert.equal(rememberReferral('?ref=Other123', storage), 'Invite_123');
  clearReferral(storage);
  assert.equal(rememberReferral('', storage), '');
  for (const value of ['short', '../escape', 'a'.repeat(65), '<script>'])
    assert.equal(referralCode(value), '');
  assert.equal(rememberReferral('?ref=Invite_123&ref=Other123', storage), '');
  assert.equal(
    rememberReferral('?ref=Invite_123', {
      getItem() {
        throw new Error();
      },
      setItem() {
        throw new Error();
      },
    }),
    'Invite_123',
  );
});

test('preview only uses an available reward and rounds half up in cents', () => {
  assert.equal(
    previewAmount(123.45, { reward_status: 'AVAILABLE', discount_rate: 0.05, choice: 'BUY' }),
    11728,
  );
  assert.equal(
    previewAmount(100, { reward_status: 'AVAILABLE', discount_rate: 0.1, choice: 'BUY' }),
    9000,
  );
  assert.equal(
    previewAmount(100, { reward_status: 'AVAILABLE', discount_rate: 0.1, choice: 'SELL' }),
    10000,
  );
  assert.equal(
    previewAmount(100, { reward_status: 'AVAILABLE', discount_rate: 0.1, choice: null }),
    10000,
  );
  assert.equal(
    previewAmount(100, { reward_status: 'USED', discount_rate: 0.05, choice: 'BUY' }),
    10000,
  );
  assert.equal(previewAmount(100, null), 10000);
});

test('a quote validates cents, listed price, discount and reservation identity', () => {
  const quote = {
    reservation_id: id,
    listed_amount: 100,
    buyer_discount: 5,
    buyer_discount_rate: 0.05,
    amount_total: 95,
    amount_total_cents: 9500,
    commission_rate: 0.05,
    reserved_until: '2099-01-01T00:00:00Z',
  };
  assert.equal(verifyQuote(quote, 100).amount_total_cents, 9500);
  for (const invalid of [
    { amount_total_cents: 10000 },
    { buyer_discount: -1 },
    { listed_amount: 101 },
    { reservation_id: '../other' },
    { buyer_discount: 10, amount_total: 90, amount_total_cents: 9000 },
    { amount_total: 95.001 },
    { commission_rate: 1 },
    { buyer_discount_rate: 0.1 },
  ])
    assert.throws(() => verifyQuote({ ...quote, ...invalid }, 100));
  assert.equal(
    verifyQuote(
      {
        ...quote,
        commission_rate: 0,
        buyer_discount_rate: 0.1,
        buyer_discount: 10,
        amount_total: 90,
        amount_total_cents: 9000,
      },
      100,
    ).commission_rate,
    0,
  );
  assert.equal(verifyQuote({ ...quote, commission_rate: 0.075 }, 100).commission_rate, 0.075);
});

test('invitation URLs remain on the app origin and carry only the validated code', () => {
  assert.equal(
    inviteUrl('https://tickia.lat', 'Invite_123'),
    'https://tickia.lat/?ref=Invite_123#login',
  );
  assert.equal(inviteUrl('https://tickia.lat', '../evil'), '');
});

test('only an explicit definitive rejection releases the local reservation', () => {
  assert.equal(
    reservationReleased({ response: { status: 402, data: { reservation_released: true } } }),
    true,
  );
  for (const value of [
    null,
    {},
    { response: { status: 502, data: { reservation_released: true } } },
    { response: { status: 402, data: { reservation_released: 'true' } } },
    { response: { status: 402, data: {} } },
  ])
    assert.equal(reservationReleased(value), false);
});
