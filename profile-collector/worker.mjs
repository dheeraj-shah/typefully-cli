// Separate opt-in identity storage; no request logging or profile URL fetches.
import { SQL, register, spendRequest, sync, withdraw } from './storage.mjs';
const MAX_BYTES = 131072;
const MAX_SNAPSHOT_BYTES = 65536;
const TOKEN = /^[a-f0-9]{64}$/;
const PLATFORMS = ['x', 'linkedin', 'bluesky', 'threads', 'mastodon', 'substack'];
const RESERVED = new Set(['local', 'localhost', 'internal', 'invalid', 'test', 'example', 'onion', 'alt', 'arpa']);
const response = (status) => new Response(null, { status, headers: {
  'Cache-Control': 'no-store', ...([429, 503].includes(status) ? { 'Retry-After': '86400' } : {}),
} });

function publicUrl(value, platform) {
  if (typeof value !== 'string' || !value.length || value.length > 2048
      || /[\u0000-\u0020\u007f\\]/u.test(value) || /%(?:00|0a|0d)/i.test(value)) return false;
  try {
    const url = new URL(value);
    const authority = value.slice(value.indexOf('://') + 3).split('/')[0];
    const host = url.hostname.toLowerCase();
    const labels = host.split('.');
    if (!value.startsWith('https://') || authority.includes('@') || url.username || url.password
        || url.search || url.hash || url.port || !url.pathname.replaceAll('/', '')
        || host.length > 253 || !/^[\x00-\x7f]+$/.test(host)
        || labels.length < 2 || RESERVED.has(labels.at(-1)) || !/^[a-z]/.test(labels.at(-1))
        || labels.some(label => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) return false;
    const domains = { x: ['x.com', 'twitter.com'], linkedin: ['linkedin.com'], bluesky: ['bsky.app'],
      threads: ['threads.net', 'threads.com'], substack: ['substack.com'] };
    return platform === 'mastodon' || (domains[platform] || [])
      .some(domain => host === domain || host.endsWith('.' + domain));
  } catch {
    return false;
  }
}

function validProfiles(profiles) {
  if (!Array.isArray(profiles) || profiles.length > 600
      || new TextEncoder().encode(JSON.stringify(profiles)).length > MAX_SNAPSHOT_BYTES) return false;
  const seen = new Set();
  return profiles.every(profile => {
    if (!profile || Array.isArray(profile) || typeof profile !== 'object'
        || Object.keys(profile).some(key => !['platform', 'username', 'profile_url'].includes(key))
        || !PLATFORMS.includes(profile.platform)) return false;
    const hasName = Object.hasOwn(profile, 'username');
    const hasUrl = Object.hasOwn(profile, 'profile_url');
    if ((!hasName && !hasUrl) || (profile.platform !== 'substack' && (!hasName || !hasUrl))) return false;
    if (hasName && (typeof profile.username !== 'string' || !profile.username.length
        || Array.from(profile.username).length > 256
        || /\p{White_Space}|[\u0000-\u0020\u007f]/u.test(profile.username))) return false;
    if (hasUrl && !publicUrl(profile.profile_url, profile.platform)) return false;
    const signature = JSON.stringify([profile.platform, profile.username ?? null, profile.profile_url ?? null]);
    if (seen.has(signature)) return false;
    seen.add(signature);
    return true;
  });
}

async function payload(request, limit) {
  if (!request.body) throw new Error('invalid');
  const reader = request.body.getReader();
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(new Error('body_timeout'));
      reader.cancel().catch(() => {});
    }, 5000);
  });
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await Promise.race([reader.read(), timeout]);
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new Error('invalid');
      }
      chunks.push(value);
    }
  } finally {
    clearTimeout(timer);
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  if (!value || Array.isArray(value) || typeof value !== 'object'
      || typeof value.withdrawal_token !== 'string' || !TOKEN.test(value.withdrawal_token)) throw new Error('invalid');
  return value;
}

async function digest(token) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!['/v1/register', '/v1/sync', '/v1/withdraw'].includes(url.pathname) || url.search) return response(404);
    if (request.method !== 'POST') return response(405);
    if (request.headers.get('content-type') !== 'application/json') return response(415);
    let now = Math.floor(Date.now() / 1000);
    const requestMinute = Math.floor(now / 60);
    // Admission/sync floods spend a global atomic budget before potentially large bodies are read.
    // Withdrawal uses a tiny body first: known tokens bypass budgets; unknown tokens spend it later.
    if (url.pathname !== '/v1/withdraw') {
      try {
        if (!await spendRequest(env.PROFILES, now)) return response(429);
      } catch { return response(503); }
    }
    let data;
    try {
      data = await payload(request, url.pathname === '/v1/sync' ? MAX_BYTES : 256);
      now = Math.floor(Date.now() / 1000);
      if (url.pathname !== '/v1/withdraw' && Math.floor(now / 60) !== requestMinute) {
        try {
          if (!await spendRequest(env.PROFILES, now)) return response(429);
        } catch { return response(503); }
      }
      const keys = Object.keys(data).sort().join(',');
      if (url.pathname === '/v1/sync') {
        if (keys !== 'consent_revision,profiles,snapshot_at,withdrawal_token' || data.consent_revision !== '3'
            || !Number.isSafeInteger(data.snapshot_at) || Math.abs(data.snapshot_at - now) > 300
            || !validProfiles(data.profiles)) throw new Error('invalid');
      } else if (url.pathname === '/v1/register') {
        if (keys !== 'consent_revision,requested_at,withdrawal_token' || data.consent_revision !== '3'
            || !Number.isSafeInteger(data.requested_at) || Math.abs(data.requested_at - now) > 300) throw new Error('invalid');
      } else if (keys !== 'withdrawal_token') throw new Error('invalid');
    } catch (error) {
      return response(error?.message === 'body_timeout' ? 408 : 400);
    }
    try {
      const hash = await digest(data.withdrawal_token);
      if (url.pathname === '/v1/withdraw') return response(await withdraw(env.PROFILES, hash, now));
      if (url.pathname === '/v1/register') return response(await register(env.PROFILES, hash, now));
      return response(await sync(env.PROFILES, hash, data.profiles, now));
    } catch (error) {
      if (String(error?.message).includes('profile_admission_limit')) return response(429);
      return response(503);
    }
  },
  async scheduled(_controller, env) {
    await env.PROFILES.prepare(SQL.cleanup)
      .bind(Math.floor(Date.now() / 1000)).run();
  },
};
