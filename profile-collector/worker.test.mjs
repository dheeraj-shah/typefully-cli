import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import worker from './worker.mjs';
import { SQL, LIMITS } from './storage.mjs';

const tokenA = 'a'.repeat(64), tokenB = 'b'.repeat(64);
const hash = value => createHash('sha256').update(value).digest('hex');
const RETENTION = 90 * 86400;
const profiles = [
  ['x', 'https://x.com/synthetic_test'], ['linkedin', 'https://www.linkedin.com/in/synthetic_test'],
  ['bluesky', 'https://bsky.app/profile/synthetic.example.org'], ['threads', 'https://threads.net/@synthetic_test'],
  ['mastodon', 'https://social.example.org/@synthetic_test'], ['substack', 'https://substack.com/@synthetic_test'],
].map(([platform, profile_url]) => ({ platform, username: 'synthetic_test', profile_url }));

function database(fail = false) {
  const rows = new Map(), calls = [];
  const budget = { day: -1, day_requests: 0, day_admissions: 0, minute: -1, minute_requests: 0 };
  const execute = ({ sql, values }) => {
    if (fail) throw new Error('PRIVATE_BACKEND_ERROR');
    calls.push({ sql, values });
    let changes = 1;
    if (sql === SQL.budget) {
      const day = values[0], minute = values[3];
      if ((day < budget.day || (day === budget.day && budget.day_requests >= LIMITS.day))
          || minute < budget.minute || (minute === budget.minute && budget.minute_requests >= LIMITS.minute)) {
        changes = 0;
      } else {
        budget.day_requests = day === budget.day ? budget.day_requests + 1 : 1;
        budget.day_admissions = day === budget.day ? budget.day_admissions : 0;
        budget.minute_requests = minute === budget.minute ? budget.minute_requests + 1 : 1;
        budget.day = day; budget.minute = minute;
      }
    } else if (sql === SQL.cleanup) {
      changes = 0;
      for (const [key, row] of rows) if (row.expires_at <= values[0]) { rows.delete(key); changes++; }
    } else if (sql === SQL.register) {
      if (rows.has(values[0])) return { success: true, meta: { changes: 0 } };
      if (budget.day_admissions >= LIMITS.admissions) throw new Error('profile_admission_limit');
      if (rows.size >= LIMITS.records) throw new Error('profile_capacity');
      rows.set(values[0], { token_hash: values[0],
        consent_revision: '3', status: 'pending', profiles_json: null, expires_at: values[1] });
      budget.day_admissions++;
    } else if (sql === SQL.sync) {
      const row = rows.get(values[2]);
      if (!row || row.status === 'revoked' || row.expires_at <= values[3]
          || (row.status === 'active' && row.expires_at > values[4])) changes = 0;
      else Object.assign(row, { profiles_json: values[0], status: 'active', expires_at: values[1] });
    } else if (sql === SQL.withdraw) {
      const row = rows.get(values[2]);
      if (!row || row.status === 'revoked') changes = 0;
      else Object.assign(row, { profiles_json: null, status: 'revoked',
        expires_at: row.expires_at > values[0] ? values[1] : row.expires_at });
    } else {
      throw new Error('Unexpected SQL in test binding');
    }
    return { success: true, meta: { changes } };
  };
  return { rows, calls, budget,
    prepare(sql) { return { bind: (...values) => ({ sql, values, run: async () => execute({ sql, values }),
      first: async () => {
        if (fail) throw new Error('PRIVATE_BACKEND_ERROR');
        assert.ok([SQL.lookup, SQL.known].includes(sql));
        calls.push({ sql, values });
        const row = rows.get(values[0]);
        return row && (sql === SQL.known || row.expires_at > values[1])
          ? { status: row.status, expires_at: row.expires_at } : null;
      } }) }; },
  };
}

function body(values = {}) {
  return { profiles, withdrawal_token: tokenA, consent_revision: '3',
    snapshot_at: Math.floor(Date.now() / 1000), ...values };
}
function request(path = '/v1/sync', data = body(), options = {}) {
  return new Request('https://profiles.invalid' + path, { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: typeof data === 'string' ? data : JSON.stringify(data), ...options });
}

function registration(token = tokenA) {
  return request('/v1/register', { withdrawal_token: token, consent_revision: '3',
    requested_at: Math.floor(Date.now() / 1000) });
}
async function admit(db, token = tokenA) {
  assert.equal((await worker.fetch(registration(token), { PROFILES: db })).status, 201);
}

test('stores only current public profile snapshot, hash, revision, rolling expiry; never headers or raw capability', async () => {
  const db = database(), now = Math.floor(Date.now() / 1000);
  await admit(db);
  const req = request();
  req.headers.set('Authorization', 'PRIVATE_AUTH');
  req.headers.set('CF-Connecting-IP', '192.0.2.1');
  req.headers.set('User-Agent', 'PRIVATE_HOST');
  const response = await worker.fetch(req, { PROFILES: db });
  assert.equal(response.status, 201);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  const row = db.rows.get(hash(tokenA));
  assert.deepEqual(Object.keys(row).sort(), ['consent_revision', 'expires_at', 'profiles_json', 'status', 'token_hash']);
  assert.equal(row.status, 'active');
  assert.deepEqual(JSON.parse(row.profiles_json), profiles);
  assert.ok(row.expires_at >= now + RETENTION && row.expires_at <= now + RETENTION + 1);
  assert.doesNotMatch(JSON.stringify(db.calls), new RegExp(tokenA + '|PRIVATE_|192\\.0'));
});

test('later sync replaces complete snapshot and advances rolling expiry without history', async () => {
  const db = database(), original = Date.now;
  let clock = 1800000000000;
  Date.now = () => clock;
  try {
    await admit(db);
    await worker.fetch(request(), { PROFILES: db });
    const firstExpiry = db.rows.get(hash(tokenA)).expires_at;
    clock += 86400000;
    const updated = [{ platform: 'linkedin', username: 'synthetic_new_client',
      profile_url: 'https://www.linkedin.com/in/synthetic_new_client' }];
    assert.equal((await worker.fetch(request('/v1/sync', body({ profiles: updated })), { PROFILES: db })).status, 201);
    assert.equal(db.rows.size, 1);
    assert.deepEqual(JSON.parse(db.rows.get(hash(tokenA)).profiles_json), updated);
    assert.equal(db.rows.get(hash(tokenA)).expires_at, firstExpiry + 86400);
    clock += 86400000;
    assert.equal((await worker.fetch(request('/v1/sync', body({ profiles: [] })), { PROFILES: db })).status, 201);
    assert.equal(db.rows.get(hash(tokenA)).profiles_json, '[]');
  } finally { Date.now = original; }
});

test('withdrawal clears every profile, retains hash-only tombstone and prevents late resurrection', async () => {
  const db = database();
  await admit(db);
  await admit(db, tokenB);
  await worker.fetch(request(), { PROFILES: db });
  await worker.fetch(request('/v1/sync', body({ withdrawal_token: tokenB })), { PROFILES: db });
  const withdraw = () => worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { PROFILES: db });
  assert.equal((await withdraw()).status, 204);
  assert.equal(db.rows.get(hash(tokenA)).profiles_json, null);
  assert.ok(db.rows.get(hash(tokenB)).profiles_json);
  assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 410);
  assert.equal(db.rows.get(hash(tokenA)).profiles_json, null);
  assert.equal((await withdraw()).status, 204);
});

test('withdraw-before-first-upload is safe and stale delayed payload cannot recreate expired tombstone', async () => {
  const db = database(), old = Date.now;
  let clock = 1800000000000;
  Date.now = () => clock;
  try {
    await admit(db);
    const delayed = body();
    assert.equal((await worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { PROFILES: db })).status, 204);
    assert.equal((await worker.fetch(request('/v1/sync', delayed), { PROFILES: db })).status, 410);
    clock += (RETENTION + 1) * 1000;
    await worker.scheduled({}, { PROFILES: db });
    assert.equal(db.rows.size, 0);
    assert.equal((await worker.fetch(request('/v1/sync', delayed), { PROFILES: db })).status, 400);
    assert.equal(db.rows.size, 0);
  } finally { Date.now = old; }
});

test('daily cleanup removes expired snapshots and withdrawal hashes', async () => {
  const db = database();
  await admit(db);
  await admit(db, tokenB);
  await worker.fetch(request(), { PROFILES: db });
  await worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenB }), { PROFILES: db });
  for (const row of db.rows.values()) row.expires_at = 0;
  await worker.scheduled({}, { PROFILES: db });
  assert.equal(db.rows.size, 0);
});

test('rejects private/unapproved fields, wrong consent, invalid times, duplicate profiles and malformed payloads', async () => {
  const invalid = ['null', '[]', 'not json', {}, body({ email: 'PRIVATE_EMAIL' }), body({ version: '0.5.0' }),
    body({ consent_revision: '1' }), body({ consent_revision: '2' }), body({ snapshot_at: 0 }),
    body({ snapshot_at: Date.now() }), body({ withdrawal_token: 'short' }), body({ withdrawal_token: [tokenA] }),
    body({ profiles: [profiles[0], profiles[0]] }), body({ profiles: [{ ...profiles[0], name: 'PRIVATE_NAME' }] }),
    body({ profiles: [{ ...profiles[0], platform: 'unknown' }] }), body({ profiles: [{ platform: 'x' }] }),
    body({ profiles: [{ ...profiles[0], username: null }] }), body({ profiles: [{ ...profiles[0], username: 'a b' }] }),
    body({ profiles: Array.from({ length: 601 }, (_, i) => ({ platform: 'substack', username: 'synthetic_' + i })) })];
  for (const data of invalid) {
    const db = database();
    assert.equal((await worker.fetch(request('/v1/sync', data), { PROFILES: db })).status, 400);
    assert.equal(db.rows.size, 0);
  }
});

test('Substack can have only a documented username or URL; neither is rejected', async () => {
  for (const profile of [{ platform: 'substack', username: 'synthetic' },
    { platform: 'substack', profile_url: 'https://substack.com/@synthetic' }]) {
    const db = database();
    await admit(db);
    assert.equal((await worker.fetch(request('/v1/sync', body({ profiles: [profile] })), { PROFILES: db })).status, 201);
  }
  assert.equal((await worker.fetch(request('/v1/sync', body({ profiles: [{ platform: 'substack' }] })), { PROFILES: database() })).status, 400);
});

test('unsafe profile URLs are rejected without DNS, fetching, redirects or scraping', async () => {
  const old = globalThis.fetch;
  globalThis.fetch = () => { throw new Error('No profile URL may be fetched'); };
  try {
    for (const profile_url of ['http://social.example.org/@test', 'https://127.0.0.1/@test',
      'https://0x7f000001/@test', 'https://2130706433/@test', 'https://[::1]/@test', 'https://localhost/@test',
      'https://host.internal/@test', 'https://social.example.org:8443/@test', 'https://user:pass@social.example.org/@test',
      'https://@social.example.org/@test', 'https://social.example.org/@test?token=private',
      'https://social.example.org/@test#private', 'https://social.example.org/%0a', 'https://social.example.org/']) {
      const db = database();
      const data = body({ profiles: [{ platform: 'mastodon', username: 'synthetic', profile_url }] });
      assert.equal((await worker.fetch(request('/v1/sync', data), { PROFILES: db })).status, 400, profile_url);
      assert.equal(db.rows.size, 0);
    }
    const db = database();
    await admit(db);
    assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 201);
  } finally { globalThis.fetch = old; }
});

test('rejects routes, queries, methods, content types, invalid UTF-8 and bounded streamed oversize', async () => {
  const db = database();
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new Uint8Array(70000)); controller.enqueue(new Uint8Array(70000)); controller.close();
  } });
  const cases = [[new Request('https://profiles.invalid/v1/sync'), 405], [request('/v1/sync?private=1'), 404],
    [request('/v1/list'), 404], [request('/v1/sync', {}, { headers: { 'Content-Type': 'text/plain' } }), 415],
    [request('/v1/sync', {}, { body: new Uint8Array([0xff]) }), 400],
    [request('/v1/sync', {}, { body: stream, duplex: 'half', headers: {
      'Content-Type': 'application/json', 'Content-Length': '1' } }), 400]];
  for (const [req, status] of cases) assert.equal((await worker.fetch(req, { PROFILES: db })).status, status);
  assert.equal(db.rows.size, 0);
});

test('storage errors do not expose backend details', async () => {
  const response = await worker.fetch(request(), { PROFILES: database(true) });
  assert.equal(response.status, 503);
  assert.equal(await response.text(), '');
});

test('fresh-token uploads cannot allocate storage without admission', async () => {
  const db = database(), original = Date.now;
  let clock = 1800000000000;
  Date.now = () => clock;
  try {
    for (let i = 0; i < 80; i++) {
      if (i % 20 === 0) clock += 60000;
      const token = i.toString(16).padStart(64, '0');
      assert.equal((await worker.fetch(request('/v1/sync', body({ withdrawal_token: token })), { PROFILES: db })).status, 404);
    }
    assert.equal(db.rows.size, 0);
    assert.equal(db.budget.day_admissions, 0);
  } finally { Date.now = original; }
});

test('fresh registrations hit the global daily admission cap even after request windows reset', async () => {
  const db = database(), original = Date.now;
  let clock = 1800000000000;
  Date.now = () => clock;
  try {
    for (let i = 0; i < LIMITS.admissions; i++) {
      if (i % 20 === 0) clock += 60000;
      await admit(db, i.toString(16).padStart(64, '0'));
    }
    assert.equal(db.rows.size, LIMITS.admissions);
    clock += 60000;
    const denied = await worker.fetch(registration(tokenB), { PROFILES: db });
    assert.equal(denied.status, 429);
    assert.equal(denied.headers.get('Retry-After'), '86400');
    assert.equal(db.rows.size, LIMITS.admissions);
    assert.equal(db.budget.day_admissions, LIMITS.admissions);
    clock += 86400000;
    await admit(db, tokenB);
    assert.equal(db.rows.size, 1); // Expired one-hour empty reservations were reclaimed.
    assert.equal(db.budget.day_admissions, 1);
  } finally { Date.now = original; }
});

test('request quota is checked before reading large bodies and cannot be bypassed with fresh tokens', async () => {
  const db = database(), now = Math.floor(Date.now() / 1000);
  Object.assign(db.budget, { day: Math.floor(now / 86400), minute: Math.floor(now / 60),
    day_requests: LIMITS.day, minute_requests: 0 });
  const req = request();
  Object.defineProperty(req, 'body', { get() { throw new Error('Quota rejection must not parse the body'); } });
  assert.equal((await worker.fetch(req, { PROFILES: db })).status, 429);
  assert.equal((await worker.fetch(registration(tokenB), { PROFILES: db })).status, 429);
  assert.equal(db.budget.day_requests, LIMITS.day);
  assert.equal(db.rows.size, 0);
  db.budget.day_requests = 0;
  db.budget.minute_requests = LIMITS.minute;
  assert.equal((await worker.fetch(registration(), { PROFILES: db })).status, 429);
  assert.equal(db.rows.size, 0);
});

test('repeated known-token writes cannot renew a pending lease or bypass the daily sync ceiling', async () => {
  const db = database();
  await admit(db);
  const pendingExpiry = db.rows.get(hash(tokenA)).expires_at;
  await admit(db);
  assert.equal(db.rows.get(hash(tokenA)).expires_at, pendingExpiry);
  assert.equal(db.budget.day_admissions, 1);
  assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 201);
  const row = structuredClone(db.rows.get(hash(tokenA)));
  for (let i = 0; i < 3; i++) assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 429);
  assert.deepEqual(db.rows.get(hash(tokenA)), row);
});

test('unknown withdrawal abuse is request-limited and creates no tombstones or per-token storage', async () => {
  const db = database();
  for (let i = 0; i < 500; i++) {
    const token = i.toString(16).padStart(64, '0');
    assert.equal((await worker.fetch(request('/v1/withdraw', { withdrawal_token: token }), { PROFILES: db })).status,
      i < LIMITS.minute ? 204 : 429);
  }
  assert.equal(db.rows.size, 0);
  assert.equal(db.budget.day_admissions, 0);
  assert.equal(db.budget.minute_requests, LIMITS.minute);
  assert.ok(db.calls.every(call => [SQL.known, SQL.budget].includes(call.sql)));
});

test('legitimate withdrawal bypasses exhausted request/admission quotas and full storage', async () => {
  const db = database(), now = Math.floor(Date.now() / 1000);
  for (let i = 0; i < LIMITS.records; i++) {
    const key = i === 0 ? hash(tokenA) : hash('synthetic-seed-' + i);
    db.rows.set(key, { token_hash: key, profiles_json: JSON.stringify(profiles), status: 'active',
      consent_revision: '3', expires_at: now + RETENTION - 86401 });
  }
  assert.equal((await worker.fetch(registration(tokenB), { PROFILES: db })).status, 503);
  assert.equal(db.rows.size, LIMITS.records);
  assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 201); // Existing record can still update.
  Object.assign(db.budget, { day: Math.floor(now / 86400), minute: Math.floor(now / 60),
    day_requests: LIMITS.day, day_admissions: LIMITS.admissions, minute_requests: LIMITS.minute });
  const withdraw = () => worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { PROFILES: db });
  assert.equal((await withdraw()).status, 204);
  assert.equal(db.rows.get(hash(tokenA)).profiles_json, null);
  assert.equal(db.rows.get(hash(tokenA)).status, 'revoked');
  const expiry = db.rows.get(hash(tokenA)).expires_at;
  const budget = structuredClone(db.budget);
  assert.equal((await withdraw()).status, 204);
  assert.equal(db.rows.get(hash(tokenA)).expires_at, expiry);
  assert.deepEqual(db.budget, budget);
  assert.equal(db.rows.size, LIMITS.records);
});

test('withdrawal cannot revive expired pending records and its tiny body is independently bounded', async () => {
  const db = database();
  await admit(db);
  db.rows.get(hash(tokenA)).expires_at = 1;
  assert.equal((await worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { PROFILES: db })).status, 204);
  assert.equal(db.rows.get(hash(tokenA)).expires_at, 1);
  const calls = db.calls.length;
  assert.equal((await worker.fetch(request('/v1/withdraw', ' '.repeat(257)), { PROFILES: db })).status, 400);
  assert.equal(db.calls.length, calls);
});

test('known-token deletion works even if the request-budget table is unavailable', async () => {
  const db = database();
  await admit(db);
  assert.equal((await worker.fetch(request(), { PROFILES: db })).status, 201);
  const originalPrepare = db.prepare.bind(db);
  db.prepare = sql => sql === SQL.budget ? { bind: () => ({ run: async () => { throw new Error('budget unavailable'); } }) }
    : originalPrepare(sql);
  assert.equal((await worker.fetch(registration(tokenB), { PROFILES: db })).status, 503);
  assert.equal((await worker.fetch(request('/v1/withdraw', { withdrawal_token: tokenA }), { PROFILES: db })).status, 204);
  assert.equal(db.rows.get(hash(tokenA)).profiles_json, null);
});

test('review template has no account, bindings, route, cron, or application logging', async () => {
  const raw = await readFile(new URL('./wrangler.example.jsonc', import.meta.url), 'utf8');
  const config = JSON.parse(raw.replace(/\/\/.*$/gm, ''));
  for (const key of ['account_id', 'd1_databases', 'routes', 'triggers', 'tail_consumers']) assert.equal(config[key], undefined);
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.logpush, false);
  assert.equal(config.observability.enabled, false);
  assert.equal(config.observability.logs.enabled, false);
  assert.equal(config.observability.logs.persist, false);
  assert.equal(config.observability.traces.enabled, false);
  assert.equal(config.observability.traces.persist, false);
});
