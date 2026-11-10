import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../src/payments.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
}).outputText;
const {
  safeCheckoutUrl,
  safeValidationUrl,
  paymentTransaction,
  verifyTransaction,
  watchPayment,
  payoutPayload,
  settlementLabel,
} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const id = 'b2d8c790-22a4-4c81-8ef2-5c073dac3f81';

test('checkout redirects accept only exact Go HTTPS hosts without credentials or ports', () => {
  for (const host of ['checkout.dlocalgo.com', 'checkout-sbx.dlocalgo.com'])
    assert.equal(safeCheckoutUrl(`https://${host}/pay?id=1`), `https://${host}/pay?id=1`);
  for (const url of [
    'http://checkout.dlocalgo.com/pay',
    'https://checkout.dlocalgo.com:443/pay',
    'https://checkout.dlocalgo.com:8443/pay',
    'https://user@checkout.dlocalgo.com/pay',
    'https://checkout.dlocalgo.com.attacker.test/',
    'javascript:alert(1)',
    '//checkout.dlocalgo.com/',
    'https://checkout.dlocalgo.com\\@attacker.test/',
    ' https://checkout.dlocalgo.com/',
  ])
    assert.equal(safeCheckoutUrl(url), null, url);
});

test('identity verification opens only the approved verification host', () => {
  assert.equal(
    safeValidationUrl('https://verify.legaltalent.ai/s/123'),
    'https://verify.legaltalent.ai/s/123',
  );
  for (const url of [
    'https://verify.legaltalent.ai.attacker.test/',
    'https://attacker.test/',
    'https://verify.legaltalent.ai:443/s/1',
  ])
    assert.equal(safeValidationUrl(url), null);
});

test('payment returns accept one complete UUID and ignore callback success claims', () => {
  assert.equal(paymentTransaction(`?payment_transaction=${id}&status=success`), id);
  assert.equal(paymentTransaction('?status=success'), null);
  assert.equal(paymentTransaction('?payment_transaction=../../../auth/me'), null);
  assert.equal(paymentTransaction(`?payment_transaction=${id}&payment_transaction=${id}`), null);
  assert.throws(() =>
    verifyTransaction({ transaction_id: id, status: 'success', provider: 'dlocal_go' }, id),
  );
  assert.throws(() =>
    verifyTransaction({ transaction_id: 'other', status: 'SUCCEEDED', provider: 'dlocal_go' }, id),
  );
});

test('polling waits for an authoritative result and stops after success', async () => {
  const statuses = ['PROCESSING', 'UNKNOWN', 'SUCCEEDED'];
  const seen = [],
    delays = [];
  await watchPayment(
    async () => ({ status: statuses.shift() }),
    (value) => seen.push(value.status),
    new AbortController().signal,
    async (delay) => delays.push(delay),
  );
  assert.deepEqual(seen, ['PROCESSING', 'UNKNOWN', 'SUCCEEDED']);
  assert.deepEqual(delays, [1500, 3000]);
});

test('uncertain polling is bounded and a 401 is never retried', async () => {
  let calls = 0;
  await watchPayment(
    async () => {
      calls++;
      return { status: 'UNKNOWN' };
    },
    () => {},
    new AbortController().signal,
    async () => {},
  );
  assert.equal(calls, 6);
  calls = 0;
  const expired = { response: { status: 401 } };
  await assert.rejects(
    watchPayment(
      async () => {
        calls++;
        throw expired;
      },
      () => {},
      new AbortController().signal,
      async () => {},
    ),
    (error) => error === expired,
  );
  assert.equal(calls, 1);
});

test('leaving the return view cancels further polling', async () => {
  const controller = new AbortController();
  let calls = 0;
  await watchPayment(
    async () => {
      calls++;
      controller.abort();
      return { status: 'PROCESSING' };
    },
    () => assert.fail('must not publish after cancellation'),
    controller.signal,
    async () => {},
  );
  assert.equal(calls, 1);
});

function validProfile() {
  const form = new FormData();
  for (const [key, value] of Object.entries({
    first_name: ' Ana ',
    last_name: ' Pérez ',
    document_type: 'DNI',
    document: '12345678',
    bank_code: '002',
    account_number: '00200000000000000000',
    account_type: 'SAVINGS',
    accept_fees: 'on',
  }))
    form.set(key, value);
  return form;
}

test('seller onboarding requires explicit fees, full document and bank CCI', () => {
  const form = validProfile();
  assert.equal(payoutPayload(form, 'terms-1').first_name, 'Ana');
  assert.equal(payoutPayload(form, 'terms-1').accept_fees, true);
  assert.equal(payoutPayload(form, 'terms-1').fee_terms_hash, 'terms-1');
  assert.throws(() => payoutPayload(form, ''), /costos/);
  form.delete('accept_fees');
  assert.throws(() => payoutPayload(form, 'terms-1'), /costos/);
  form.set('accept_fees', 'on');
  form.set('bank_code', '003');
  assert.throws(() => payoutPayload(form, 'terms-1'), /CCI/);
  form.set('bank_code', '002');
  form.set('document', '123');
  assert.throws(() => payoutPayload(form, 'terms-1'), /documento/);
});

test('queued, uncertain and legacy settlement states do not claim a new bank payment', () => {
  assert.match(settlementLabel('QUEUED'), /pendiente/i);
  assert.match(settlementLabel('UNKNOWN'), /verific/i);
  assert.doesNotMatch(settlementLabel('BLOCKED'), /confirmado/i);
  assert.match(settlementLabel('SUCCEEDED', 'LEGACY_PAYOUT'), /anterior/i);
});
