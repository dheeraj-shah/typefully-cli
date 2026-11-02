// Exact globally shared ceilings live in primary D1, not per-isolate memory or per-location counters.
export const LIMITS = Object.freeze({ minute: 30, day: 2000, admissions: 50, records: 1000,
  pendingSeconds: 3600, retentionSeconds: 90 * 86400, syncSeconds: 86400 });

export const SQL = Object.freeze({
  budget: `UPDATE profile_budget SET
    day_requests = CASE WHEN day = ? THEN day_requests + 1 ELSE 1 END,
    day_admissions = CASE WHEN day = ? THEN day_admissions ELSE 0 END,
    day = ?,
    minute_requests = CASE WHEN minute = ? THEN minute_requests + 1 ELSE 1 END,
    minute = ?
    WHERE id = 1
      AND (day < ? OR (day = ? AND day_requests < 2000))
      AND (minute < ? OR (minute = ? AND minute_requests < 30))`,
  lookup: `SELECT status, expires_at FROM profile_snapshots WHERE token_hash = ? AND expires_at > ?`,
  known: `SELECT status FROM profile_snapshots WHERE token_hash = ?`,
  cleanup: `DELETE FROM profile_snapshots WHERE expires_at <= ?`,
  register: `INSERT INTO profile_snapshots
    (token_hash, profiles_json, consent_revision, status, expires_at)
    VALUES (?, NULL, '3', 'pending', ?) ON CONFLICT(token_hash) DO NOTHING`,
  sync: `UPDATE profile_snapshots SET profiles_json = ?, status = 'active', expires_at = ?
    WHERE token_hash = ? AND status IN ('pending', 'active') AND expires_at > ?
      AND (status = 'pending' OR expires_at <= ?)`,
  withdraw: `UPDATE profile_snapshots SET profiles_json = NULL, status = 'revoked',
    expires_at = CASE WHEN expires_at > ? THEN ? ELSE expires_at END
    WHERE token_hash = ? AND status != 'revoked'`,
});

export async function spendRequest(db, now) {
  const day = Math.floor(now / 86400), minute = Math.floor(now / 60);
  const result = await db.prepare(SQL.budget)
    .bind(day, day, day, minute, minute, day, day, minute, minute).run();
  return result.meta.changes === 1;
}

export async function register(db, hash, now) {
  await db.prepare(SQL.cleanup).bind(now).run();
  const existing = await db.prepare(SQL.lookup).bind(hash, now).first();
  if (existing) return existing.status === 'revoked' ? 410 : 201;
  await db.prepare(SQL.register).bind(hash, now + LIMITS.pendingSeconds).run();
  // A concurrent withdrawal must not be reactivated by an idempotent registration.
  const current = await db.prepare(SQL.lookup).bind(hash, now).first();
  return current && current.status !== 'revoked' ? 201 : 410;
}

export async function sync(db, hash, profiles, now) {
  const result = await db.prepare(SQL.sync).bind(JSON.stringify(profiles),
    now + LIMITS.retentionSeconds, hash, now,
    now + LIMITS.retentionSeconds - LIMITS.syncSeconds).run();
  if (result.meta.changes === 1) return 201;
  const current = await db.prepare(SQL.lookup).bind(hash, now).first();
  if (!current) return 404; // Unknown/expired tokens cannot create data via sync.
  return current.status === 'revoked' ? 410 : 429;
}

export async function withdraw(db, hash, now) {
  const known = await db.prepare(SQL.known).bind(hash).first();
  // Unknown tokens allocate nothing and share the same strict request budget as admission/sync.
  if (!known) return await spendRequest(db, now) ? 204 : 429;
  // Known-token deletion bypasses shared quotas; repeat deletion does not write or renew expiry.
  if (known.status !== 'revoked') {
    await db.prepare(SQL.withdraw).bind(now, now + LIMITS.retentionSeconds, hash).run();
  }
  return 204;
}
