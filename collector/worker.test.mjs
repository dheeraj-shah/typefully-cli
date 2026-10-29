import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './worker.mjs';
const CATEGORIES = ['account', 'drafts', 'publishing', 'media', 'tags', 'analytics', 'comments', 'queue'];

function database(fail = false) {
  const batches = [];
  return {
    batches,
    prepare(sql) { return { bind: (...values) => ({ sql, values }) }; },
    async batch(statements) {
      if (fail) throw new Error('private backend details');
      batches.push(statements);
    },
  };
}
function request(body = { version: '0.3.0', category: 'drafts' }, options = {}) {
  return new Request('https://collector.invalid/v1/count', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body), ...options,
  });
}

test('every category stores only daily aggregate dimensions; never headers', async () => {
  for (const category of CATEGORIES) {
    const db = database();
    const req = request({ version: '0.3.0', category });
    req.headers.set('CF-Connecting-IP', '192.0.2.1');
    req.headers.set('User-Agent', 'private-machine-name');
    req.headers.set('Authorization', 'Bearer secret');
    const res = await worker.fetch(req, { COUNTS: db });
    assert.equal(res.status, 204);
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(db.batches.length, 1);
    const [cleanup, increment] = db.batches[0];
    assert.match(cleanup.sql, /DELETE FROM daily_counts/);
    assert.match(cleanup.values[0], /^\d{4}-\d{2}-\d{2}$/);
    assert.match(increment.sql, /ON CONFLICT.*DO UPDATE SET count = count \+ 1/);
    assert.deepEqual(increment.values, [new Date().toISOString().slice(0, 10), '0.3.0', category]);
    assert.doesNotMatch(JSON.stringify(db.batches), /secret|private-machine-name|192\.0/);
  }
});

test('rejects malformed, unapproved, and extra fields before storage', async () => {
  for (const body of [
    'not json', 'null', '[]', '"text"', '{}',
    { version: '0.3.0', category: 'drafts', content: 'secret' },
    { version: '0.3.0', category: 'unknown' },
    { version: 'my-private-build', category: 'drafts' },
    { version: '99.99.99', category: 'drafts' },
    { version: 3, category: 'drafts' },
    { version: '0.3.0', category: ['drafts'] },
    ' '.repeat(257),
  ]) {
    const db = database();
    const res = await worker.fetch(request(body), { COUNTS: db });
    assert.equal(res.status, 400, JSON.stringify(body));
    assert.deepEqual(db.batches, []);
  }
});

test('bounded streamed body ignores forged Content-Length', async () => {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(' '.repeat(200)));
      controller.enqueue(new TextEncoder().encode(' '.repeat(200)));
      controller.close();
    },
  });
  const db = database();
  const req = request('', { body: stream, duplex: 'half', headers: {
    'Content-Type': 'application/json', 'Content-Length': '1',
  } });
  assert.equal((await worker.fetch(req, { COUNTS: db })).status, 400);
  assert.deepEqual(db.batches, []);
});

test('rejects invalid UTF-8, route, query, method and content type', async () => {
  const db = database();
  for (const [req, status] of [
    [request('', { body: new Uint8Array([0xff]) }), 400],
    [new Request('https://collector.invalid/'), 404],
    [new Request('https://collector.invalid/v1/count?secret=1'), 404],
    [new Request('https://collector.invalid/v1/count'), 405],
    [request('{}', { headers: { 'Content-Type': 'text/plain' } }), 415],
  ]) assert.equal((await worker.fetch(req, { COUNTS: db })).status, status);
  assert.deepEqual(db.batches, []);
});

test('storage errors do not expose backend details or fail open', async () => {
  const res = await worker.fetch(request(), { COUNTS: database(true) });
  assert.equal(res.status, 503);
  assert.equal(await res.text(), '');
});

test('deployment template keeps public routes and application logging disabled', async () => {
  const { readFile } = await import('node:fs/promises');
  const template = await readFile(new URL('./wrangler.example.jsonc', import.meta.url), 'utf8');
  const cfg = JSON.parse(template.replace(/\/\/.*$/gm, ''));
  assert.equal(cfg.workers_dev, false);
  assert.equal(cfg.preview_urls, false);
  assert.equal(cfg.logpush, false);
  assert.equal(cfg.observability.enabled, false);
  assert.equal(cfg.observability.logs.enabled, false);
  assert.equal(cfg.observability.logs.invocation_logs, false);
  assert.equal(cfg.observability.traces.enabled, false);
  assert.equal(cfg.routes, undefined);
  assert.equal(cfg.account_id, undefined);
  assert.equal(cfg.d1_databases, undefined);
});
