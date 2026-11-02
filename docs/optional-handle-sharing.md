# Optional X handle sharing — review draft

This feature is **unpublished and inactive**. `HANDLE_ENDPOINT` is empty. No
identity service, database, cron, credentials or public route has been created.
Published PyPI/Homebrew 0.4.0 has no handle-sharing feature. The existing usage
collector and its exclusions are unchanged.

## Proposed user experience

Nothing prompts for a handle during normal CLI commands. Sharing is off by
default and cannot be enabled through an API key, connected account, operating
system username or analytics preference. The user chooses:

```sh
typefully community privacy
typefully community share-handle
```

Before asking for input, the CLI explains the recipient (Dheeraj Shah, the CLI
maintainer), purpose (understand who voluntarily uses the tool), exact fields,
network IP visibility, retention and withdrawal. The user types their own handle,
then answers a separate default-no confirmation naming that handle and recipient.
There is no `--yes`, automatic prompt, account discovery, background submission or
retry queue. Sharing requires an interactive terminal; CI, JSON, quiet and debug
sharing are refused. The handle is prompted rather than placed in shell history.

The command sends only the entered normalized handle, consent revision `1` and a
random 256-bit withdrawal token. The token is a separate removal capability, never
sent with anonymous command counts or Typefully requests. No release version,
command category, API credentials, post content or installation ID is included.
The dedicated transport disables environment/proxy credentials, redirects and
automatic retries and does not read a response body or log transport errors.

The CLI saves `handle-sharing.json` alongside its config before sending, with
mode 0600 on Unix. The receipt holds the handle, fixed recipient and raw token.
It does not change authentication configuration. If submission fails or its
outcome is uncertain, the receipt remains and further sharing is blocked until
withdrawal. The CLI never claims that an uncertain request succeeded.

```sh
typefully community withdraw-handle
```

Withdrawal sends only the token to the same recipient, immediately deletes its
entry, and then removes the local receipt on a confirmed 204. It is idempotent
and can be explicitly retried; failures retain the receipt. A receipt cannot be
redirected to a different endpoint. Keep the receipt until withdrawal; losing it
loses the automated removal capability. Expiry remains a fallback. Handle changes
require withdrawing the old entry and opting in again.

## Proposed storage and retention checkpoint

Review this choice before activation: a **separate Worker and dedicated D1**,
separate from the `daily_counts` database and with no join or event linkage.
Exactly four fields per entry:

| Field | Purpose |
| --- | --- |
| `handle` | Voluntarily entered X handle, lowercased, no `@` |
| `token_hash` | SHA-256 of the withdrawal capability; raw token is not stored |
| `consent_revision` | The disclosure revision the user confirmed |
| `expires_at` | 90 days from initial receipt, used only for retention |

Entries become ineligible for maintainer viewing after 90 days. A daily scheduled
cleanup removes expired rows within the next 24 hours; accepted shares also
trigger cleanup. The operator view must filter `expires_at > unixepoch()`.
Withdrawal deletes the live row immediately. Provider backups may retain deleted
data temporarily; no unsupported claim of immediate backup erasure is made.
Duplicates do not renew expiry. A new opt-in after expiry requires a new token.

There is no public roster/list API, automatic contact, marketing consent, public
issue submission or social posting. Reads use the maintainer's existing authorized
D1 access. Access is limited to the maintainer. Avoid exporting a permanent list;
90-day retention and withdrawal must apply to any later authorized export too.
Do not enable request logging, invocation logging, traces, Logpush or tail consumers.
Provider infrastructure still sees transport metadata; this is personal data,
not anonymous analytics.

## Security limits and activation gates

Handles are **self-reported and unverified**. The service does not prove ownership,
deduplicate people, or establish unique-user counts; malicious submissions are
possible. Token-authenticated removal prevents deletion merely by knowing someone
else's handle. There is no API that reveals handles or confirms their presence.
X handles can change or be reassigned. Syntax follows
[X's documented character set and 15-character maximum](https://help.x.com/en/managing-your-account/change-x-handle);
existing short handles remain accepted without claiming they can be newly registered.

The draft Worker rejects extra fields, queries, non-JSON content types, wrong
routes and bodies over 256 bytes, hashes tokens before database access and returns
empty responses without backend details. Scheduled cleanup and SQL semantics are
covered by local mocked tests; no network or real person's handle is used.

Before production deployment, obtain owner review/approval of:

1. The proposed recipient, separate personal-account Worker/D1 and four-field
   schema, 90-day expiry/daily cleanup, withdrawal and lost-receipt behavior.
2. The publicly writable service's abuse/quota behavior and any provider rate
   limiting needed, without storing IPs in application data, adding identity
   tracking or changing billing/credentials without authorization.
3. Effective logging/exports, backup retention and maintainer-only data access.
4. A real fixed HTTPS endpoint plus a daily cleanup trigger. The checked-in
   template intentionally supplies no account, binding, route or cron. Preserve
   withdrawal access for existing receipts if the endpoint ever changes.

Only after that approval should an operator deploy and verify the dedicated
service, then bind its fixed endpoint and update the disclosure together. That
configuration change, final review and separately approved package publication
are required before this feature reaches users. Do not reuse or migrate the
existing anonymous telemetry database. No real-handle production test is authorized.
