import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import worker from './worker.mjs';

const tokenA = 'a'.repeat(64);
const tokenB = 'b'.repeat(64);
const hash = (token) => createHash('sha256').update(token).digest('hex');

function database(fail = false) {
  const rows = new Map();
  const calls = [];
  const execute = ({ sql, values }) => {
    if (fail) throw new Error('private backend error');
    calls.push({ sql, values });
    if (sql.includes('WHERE expires_at')) {
      for (const [key, row] of rows) if (row.expires_at <= values[0]) rows.delete(key);
    } else if (sql.includes('DELETE')) {
      rows.delete(values[0]);
    } else if (!rows.has(values[0])) {
      rows.set(values[0], {
        token_hash: values[0], handle: values[1], consent_revision: values[2], expires_at: values[3],
      });
    }
    return { success: true };
  };
  return {
    rows, calls,
    prepare(sql) {
      return { bind: (...values) => ({ sql, values, run: async () => execute({ sql, values }) }) };
    },
    async batch(statements) { return statements.map(execute); },
  };
}

function request(path = '/v1/share', data = {
  handle: 'synthetic_test', withdrawal_token: tokenA, consent_revision: '1',
}, options = {}) {
  return new Request('https://handles.invalid' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: typeof data === 'string' ? data : JSON.stringify(data), ...options,
  });
}

test('share stores only a handle, token hash, consent revision and 90-day expiry', async () => {
  const db = database();
  const now = Math.floor(Date.now() / 1000);
  const req = request();
  req.headers.set('Authorization', 'secret');
  req.headers.set('CF-Connecting-IP', '192.0.2.1');
  req.headers.set('User-Agent', 'private-host');
  assert.equal((await worker.fetch(req, { HANDLES: db })).status, 201);
  const row = db.rows.get(hash(tokenA));
  assert.equal(row.handle, 'synthetic_test');
  assert.equal(row.consent_revision, '1');
  assert.ok(row.expires_at >= now + 90 * 86400 && row.expires_at <= now + 90 * 86400 + 1);
  assert.deepEqual(Object.keys(row).sort(), ['consent_revision', 'expires_at', 'handle', 'token_hash']);
  assert.doesNotMatch(JSON.stringify(db.calls), new RegExp(tokenA + '|secret|192\\.0|private-host'));
});

test('withdrawal removes only the capability holder entry and is idempotent', async () => {
  const db = database();
  await worker.fetch(request(), { HANDLES: db });
  await worker.fetch(request('/v1/share', {
    handle: 'synthetic_other', withdrawal_token: tokenB, consent_revision: '1',
  }), { HANDLES: db });
  const withdraw = () => worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { HANDLES: db });
  assert.equal((await withdraw()).status, 204);
  assert.ok(!db.rows.has(hash(tokenA)));
  assert.ok(db.rows.has(hash(tokenB)));
  assert.equal((await withdraw()).status, 204);
  assert.equal(db.rows.size, 1);
  assert.equal((await worker.fetch(request('/v1/withdraw', { handle: 'synthetic_other' }), { HANDLES: db })).status, 400);
});

test('a duplicate capability cannot change the handle or renew retention', async () => {
  const db = database();
  await worker.fetch(request(), { HANDLES: db });
  const before = { ...db.rows.get(hash(tokenA)) };
  await worker.fetch(request('/v1/share', {
    handle: 'synthetic_other', withdrawal_token: tokenA, consent_revision: '1',
  }), { HANDLES: db });
  assert.deepEqual(db.rows.get(hash(tokenA)), before);
});

test('daily scheduled cleanup and next share remove expired rows', async () => {
  const db = database();
  await worker.fetch(request(), { HANDLES: db });
  db.rows.get(hash(tokenA)).expires_at = Math.floor(Date.now() / 1000) - 1;
  await worker.scheduled({}, { HANDLES: db });
  assert.equal(db.rows.size, 0);
  await worker.fetch(request(), { HANDLES: db });
  db.rows.get(hash(tokenA)).expires_at = 0;
  await worker.fetch(request('/v1/share', {
    handle: 'synthetic_other', withdrawal_token: tokenB, consent_revision: '1',
  }), { HANDLES: db });
  assert.ok(!db.rows.has(hash(tokenA)));
  assert.ok(db.rows.has(hash(tokenB)));
});

test('unapproved fields, invalid handles/tokens/consent are rejected before storage', async () => {
  const valid = { handle: 'synthetic_test', withdrawal_token: tokenA, consent_revision: '1' };
  for (const data of [
    'null', '[]', 'not json', {},
    { ...valid, version: '0.4.0' }, { ...valid, category: 'drafts' },
    { ...valid, handle: '@synthetic' }, { ...valid, handle: 'UPPERCASE' },
    { ...valid, handle: 'a'.repeat(16) }, { ...valid, handle: 'éxample' },
    { ...valid, handle: ['synthetic'] }, { ...valid, withdrawal_token: 'short' },
    { ...valid, withdrawal_token: [tokenA] }, { ...valid, consent_revision: '2' },
    { ...valid, consent_revision: 1 },
  ]) {
    const db = database();
    assert.equal((await worker.fetch(request('/v1/share', data), { HANDLES: db })).status, 400);
    assert.deepEqual(db.calls, []);
  }
});

test('rejects route, query, method, type, invalid UTF-8 and streamed oversize', async () => {
  const db = database();
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode(' '.repeat(200)));
    controller.enqueue(new TextEncoder().encode(' '.repeat(200)));
    controller.close();
  } });
  const cases = [
    [new Request('https://handles.invalid/v1/share'), 405],
    [request('/v1/share?handle=synthetic'), 404],
    [request('/v1/list'), 404],
    [request('/v1/share', {}, { headers: { 'Content-Type': 'text/plain' } }), 415],
    [request('/v1/share', {}, { body: new Uint8Array([0xff]) }), 400],
    [request('/v1/share', {}, { body: stream, duplex: 'half', headers: {
      'Content-Type': 'application/json', 'Content-Length': '1',
    } }), 400],
  ];
  for (const [req, status] of cases) assert.equal((await worker.fetch(req, { HANDLES: db })).status, status);
  assert.deepEqual(db.calls, []);
});

test('storage errors return no private backend details', async () => {
  const response = await worker.fetch(request(), { HANDLES: database(true) });
  assert.equal(response.status, 503);
  assert.equal(await response.text(), '');
});

test('template is inactive and has no route, schedule, identity binding or logging', async () => {
  const raw = await readFile(new URL('./wrangler.example.jsonc', import.meta.url), 'utf8');
  const config = JSON.parse(raw.replace(/\/\/.*$/gm, ''));
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.logpush, false);
  assert.equal(config.observability.enabled, false);
  assert.equal(config.observability.logs.enabled, false);
  assert.equal(config.observability.logs.persist, false);
  assert.equal(config.observability.traces.enabled, false);
  assert.equal(config.observability.traces.persist, false);
  for (const key of ['account_id', 'routes', 'd1_databases', 'triggers', 'tail_consumers']) {
    assert.equal(config[key], undefined);
  }
});
