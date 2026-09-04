# Packrat account and sync service exploration

Status: exploratory; no application behavior depends on this document.

## Recommendation

Build a small, separate sync service with managed social login. Keep Packrat
fully usable without an account and store each user's validated library as
revisioned JSON. Use normal SaaS security—HTTPS, provider-managed authentication,
encrypted infrastructure, authorization checks, backups, and minimal logging—
rather than end-to-end encryption and user-managed recovery keys.

The first release should synchronize one whole library with optimistic revision
checks. It should not attempt record-level merging, collaboration, sharing, a
web editor, custom passwords, or billing.

This keeps the product promise straightforward:

- Sign in with an existing account.
- Sync inventory and trips across Packrat installations.
- Continue working locally and offline.
- Never silently replace changes from another device.
- Export or delete the user's data on request.

The service will be technically able to read library content. That is an
acceptable and much simpler boundary for ordinary backpacking inventory, as long
as it is disclosed honestly and access is appropriately controlled.

## Why a separate repository

The Packrat repository should retain its current separation between pure core
logic, local persistence, and the Textual UI. A service adds HTTP routing,
authentication, authorization, database migrations, deployment, backups, abuse
controls, and operational monitoring. Keeping those concerns in their own
repository avoids adding server dependencies to the terminal application.

This repository should eventually contain only a small sync client and the UI
needed to sign in, show sync state, and resolve conflicts.

## Proposed product experience

### First device

1. The user chooses **Enable Sync**.
2. Packrat opens the system browser to a hosted login page.
3. The user signs in with Google or GitHub.
4. The browser returns authorization to Packrat.
5. Packrat uploads the current library or downloads an existing one.

Use Authorization Code Flow with PKCE for the desktop client. A loopback
redirect to a temporary localhost listener is the best default when a browser is
available. A short code/device flow is a useful fallback for remote shells or
systems where the browser is on another device.

Start with Google and GitHub:

- Google is familiar to a broad consumer audience.
- GitHub is convenient for Packrat's likely early technical users and supports
  a documented device flow for command-line applications.
- Avoid adding more providers until demand is demonstrated; each one adds
  configuration, review, account-linking, and support work.

The app requests identity scopes only (`openid`, email, and basic profile). It
does not need access to Google Drive, GitHub repositories, contacts, or social
data. Packrat should store the managed authentication session, not the upstream
Google or GitHub access token.

### Additional devices

The user signs in with the same identity. Packrat shows the existing cloud
library and asks whether to open it or replace it with the current local library
if both contain data. Once selected, the device records the remote revision and
normal synchronization begins.

### Normal operation

- Pull on startup, when returning online, before publishing a local change, and
  on an explicit **Sync now** action.
- Push after a successful local save, with a short debounce for clustered saves.
- Show `Local only`, `Synced`, `Syncing`, `Offline`, `Conflict`, or `Error`, plus
  the last successful sync time.
- Never block viewing or local editing because the service is unavailable.
- Queue only the latest local snapshot, not an unbounded operation log.
- A one-launch `--data` override defaults to sync disabled so a test library is
  never attached to the account accidentally.

## Whole-library revisions are the right v1

Packrat already validates and atomically saves a single `gear_data.json`. Its
file signature rejects stale local writes, but records do not have modification
versions, tombstones, or merge rules. Sequential IDs such as `G001` can also be
created independently on two offline devices.

Snapshot synchronization maps directly onto the existing safety model:

1. A client fetches remote metadata and its current revision.
2. It uploads validated JSON with `base_revision` and a unique request ID.
3. In one transaction, the service accepts the upload only if `base_revision`
   is still current, stores the next immutable revision, and advances the
   library pointer.
4. A stale upload receives HTTP `409` and changes neither copy.

For a personal inventory application, simultaneous editing should be rare. A
visible conflict is safer than an automatic merge that can change quantities,
weights, notes, or trip membership.

### Conflict experience

On `409`, preserve the last common version, local unsynced version, and current
remote version. Do not overwrite `gear_data.json`. Offer:

- **Use this device**—publish the local snapshot after explicit confirmation;
- **Use other device**—archive local and install the remote snapshot; or
- **Save both**—write both JSON files locally and defer the decision.

Record-level merging can be considered later if conflict telemetry or support
requests show it is needed. That work should first migrate records to globally
unique IDs and define field-level merge and deletion semantics.

## Authentication and account identity

Use a managed OpenID Connect/OAuth provider rather than implementing passwords,
email verification, password reset, refresh-token rotation, and provider
integration in the sync service. Supabase Auth is a strong default candidate for
the spike because it combines social login, JWT sessions, and PostgreSQL without
requiring Packrat to use its database API directly. Auth0 is a reasonable
alternative if identity features become more important than an integrated data
stack.

The Packrat service remains the authorization boundary:

- It validates the managed provider's JWT issuer, audience, signature, and
  expiry.
- It maps the stable auth subject to an internal Packrat account ID.
- Every library query is scoped by that internal account ID.
- It never trusts an account or library ID supplied by the client without
  applying that scope.
- Administrative access is separate, least-privileged, and audited.

Do not use email as the durable account key; providers may change or hide it.
Store `(issuer, subject)` identities. If multiple login providers can be linked
to one Packrat account, require the user to be actively authenticated before
linking. Never merge accounts solely because two providers return the same email
address.

Desktop refresh tokens belong in the operating system credential store, not in
`preferences.json` or `gear_data.json`. Logging out removes the local token but
does not delete local data. Account deletion is a distinct, explicit action.

## Minimal service architecture

Use one stateless HTTP application and PostgreSQL. For the fastest prototype,
Supabase can provide managed authentication and PostgreSQL while a small Packrat
API owns all sync logic. Keeping that API between the client and database gives
Packrat one clear place for validation, revision transactions, limits, and
future migration away from a vendor.

Store JSON directly in PostgreSQL initially. Packrat libraries should be small,
and object storage creates another consistency and deletion boundary. Revisit
blob storage only after measuring real library sizes and database cost.

Suggested tables:

```text
accounts(id, created_at, disabled_at)
account_identities(id, account_id, issuer, subject, created_at, last_login_at)
devices(id, account_id, label, created_at, last_seen_at, revoked_at)
libraries(id, account_id, current_revision, created_at, updated_at)
library_revisions(library_id, revision, data_json, content_hash,
                  data_schema_version, created_at, device_id, request_id)
```

Important constraints:

- unique `(issuer, subject)` on identities;
- one initial library per account;
- unique `(library_id, revision)`;
- unique `(library_id, request_id)` for idempotent retries;
- foreign keys with deliberate deletion behavior;
- maximum request and JSON size;
- a bounded revision-retention policy.

### Minimal API

```text
GET    /v1/me                         account and devices
GET    /v1/library                    current revision metadata and JSON
PUT    /v1/library                    conditional snapshot upload
GET    /v1/library/revisions          limited recovery history
POST   /v1/library/revisions/{n}/restore
POST   /v1/devices                    register this installation
DELETE /v1/devices/{id}               revoke a device
GET    /v1/export                     download account data
DELETE /v1/account                    delete the account and cloud data
GET    /healthz                       deployment health
```

The upload body contains `base_revision`, `request_id`, `data_schema_version`,
and the library JSON. The service validates the complete Packrat model (ideally
through a small shared schema package or contract fixtures), applies size and
rate limits, and commits the new revision in one transaction. Replaying a
request ID returns the original result. A stale base revision returns `409` with
current metadata and no write.

Do not expose generic CRUD endpoints for individual gear and trip records in
v1. They duplicate domain logic, enlarge the API, and imply merge behavior the
client does not yet support.

## Reasonable privacy and security

Removing end-to-end encryption does not mean ignoring privacy. Packrat should:

- collect only login identity, basic profile, device metadata, library content,
  operational logs, and subscription state if billing is later introduced;
- use HTTPS everywhere and encryption at rest from the hosting provider;
- avoid advertising, tracking pixels, and third-party behavioral analytics;
- never log request bodies, authorization headers, trip names, or gear data;
- use short log retention and aggregate operational metrics;
- provide account export and deletion;
- document subprocessors, backup retention, and when deleted data ages out of
  backups;
- restrict production database access and audit administrative access;
- test restore and deletion procedures, not merely backup creation;
- publish a short plain-language privacy policy.

This protects users against common mistakes and unauthorized access while
avoiding recovery codes, client cryptography, encrypted revision inspection,
device-to-device key transfer, and permanent data loss when a secret is lost.

## Client boundary in this repository

Likely modules:

```text
packrat_sync.py       revisions, retries, offline state, conflicts
packrat_accounts.py   browser login, PKCE/device flow, secure session storage
```

`gear_core.py` should continue owning data validation and atomic local
persistence. `gear_tui.py` should call a coordinator and display its state; it
should not contain HTTP or OAuth protocol logic. Network operations must be
asynchronous or run in a Textual worker so the interface stays responsive.

Local non-secret sync metadata can live beside preferences:

```json
{
  "version": 1,
  "service_url": "https://sync.example.com",
  "account_id": "...",
  "library_id": "...",
  "device_id": "...",
  "last_remote_revision": 17,
  "last_synced_content_hash": "..."
}
```

The session token is stored separately in the system keychain.

## Service-repository boundary

The separate repository should contain:

- API application and explicit OpenAPI contract;
- database migrations and authorization policies;
- managed-auth configuration and callback pages;
- rate and payload limits;
- revision retention and account-deletion jobs;
- deployment, monitoring, database backup, and restore configuration;
- contract, authorization-isolation, concurrency, restore, and deletion tests;
- operational runbooks and privacy policy source.

Avoid billing, teams, sharing, public links, custom passwords, web CRUD, and push
notifications until basic roaming is reliable.

## Delivery sequence

### Phase 0: local protocol spike

- Specify the HTTP contract and revision behavior.
- Build an in-memory fake service and a small sync coordinator.
- Add headless two-client tests for first upload, download, offline edits,
  idempotent retry, stale upload, corrupt response, and service outage.
- Do not change normal Packrat startup or saving yet.

Exit criterion: two temporary libraries can roam through the fake server
without losing either side of a conflict.

### Phase 1: hosted private alpha

- Create the separate service repository.
- Configure managed Google and GitHub login.
- Deploy the API and PostgreSQL with backups.
- Add browser login, secure token storage, manual sync, visible state, conflict
  handling, device revocation, export, and account deletion.
- Keep registration invite-only with conservative payload and request limits.

Exit criterion: authorization isolation, restore, and deletion have end-to-end
tests, and an operator has completed a real backup restore drill.

### Phase 2: reliability

- Add background sync with jittered retries.
- Add revision history and restore UI.
- Add narrowly scoped aggregate reliability metrics.
- Measure conflicts, payload sizes, request rates, and support burden before
  considering record-level sync or paid plans.

## Decisions before implementation

1. Which managed authentication service should the spike use? Supabase is the
   default recommendation, but the protocol should depend only on standard JWT
   validation so it remains replaceable.
2. Is Google plus GitHub the right initial provider set for Packrat's audience?
3. Should a new account upload its local example library automatically, or ask
   the user to choose between local and cloud explicitly?
4. How many revisions and backup days should be retained?
5. What library-size, device-count, and request-rate limits define the alpha?
6. Is a browser loopback callback sufficient for the supported environments,
   or is device flow required in the first alpha?

## Go/no-go assessment

This reduced design is a good fit for Packrat. The hard correctness problem is
still conflict handling, but authentication, recovery, inspection, migrations,
and support are substantially simpler without end-to-end encryption. The next
useful step is a local protocol spike—not deployment—to prove two-device
revision behavior against the current `gear_data.json` model.

## References

- Auth0, *Authentication and Authorization Flows* (native applications and
  Authorization Code Flow with PKCE):
  https://auth0.com/docs/get-started/authentication-and-authorization-flow
- GitHub, *Authorizing OAuth apps* (device flow for headless/CLI applications):
  https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps
- Supabase, *Auth* (social providers, JWTs, and PostgreSQL authorization):
  https://supabase.com/docs/guides/auth
- Supabase, *Login with Google* (Google social login and PKCE exchange):
  https://supabase.com/docs/guides/auth/social-login/auth-google
