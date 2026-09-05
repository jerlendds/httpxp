# wreq migration work log

The task is **not complete**. Preserve the full objective in
`/home/jerlendds/.codex/attachments/38378646-771a-4417-997d-ab7ae50523d6/goal-objective.md`
and all ten accompanying pasted files. All were read on the initial goal turn.
The requirement is to expose all wreq configuration through the existing Python
API and recreate every supplied example, including WebSockets, custom connector
middleware, runtime selection, certificates, emulation, and request overrides.

## Current implementation

- Maturin builds `httpxp._native`, a PyO3 extension using wreq 0.16.1 and
  wreq-util 0.2.0. Cargo requires Rust >=1.98, matching these dependencies.
- Rust owns pooled clients and streamed response bodies, releases the GIL while
  doing network work, and translates network errors into httpxp exceptions.
- Default sync and async transports use the extension; async uses AnyIO workers
  and works under both asyncio and Trio. Custom transports remain Python APIs.
- `Client`, `AsyncClient`, both HTTP transports, and module-level request helpers
  accept `privacy_options`. Request overrides use `extensions={"private": {...}}`.
- `src/options.rs` implements many client and request options, every primitive
  public TLS/HTTP1/HTTP2 field, TLS key shares/compressors/extensions, HTTP/2
  pseudo-header/settings/priority ordering, profile names, and custom emulation.
  Unknown keys fail explicitly. This is NOT yet full configuration coverage.
- Python still handles its usual auth, redirects, cookies, encodings, multipart,
  request/response hooks, etc. Native redirects/decompression are disabled by
  default to preserve that behavior.
- Response streams retain a semaphore permit until closed/exhausted; Python
  pool timeout and max_connections are enforced separately from wreq's pool.
- Client connect timeout is forwarded. Per-request read/pool/write timeouts are
  forwarded. `src/upload.rs` streams Python iterators in <=64KiB wire chunks,
  preserves original Python exceptions, and uses an upload progress watchdog.
  The write watchdog currently includes time spent waiting on the Python producer;
  audit its exact compatibility with socket-only write deadlines before completion.
- `src/cancel.rs` supplies a native cancellation signal for queued pool acquisition,
  waiting for response headers, and streamed response reads. Async worker calls
  can be abandoned; cancellation wakes Rust and releases the held permit.
- Async uploads use an AnyIO BlockingPortal with explicit error capture (avoids
  wrapping user errors in ExceptionGroup) and close async generators. Early
  responses stop pending upload tasks via an atomic stop signal, turning an
  interrupted producer into clean EOF rather than a response-breaking body error.
  Known-empty bodies use a native empty body. Already-cached bytes/JSON/form bodies
  stay in Rust and finish their declared content length after an early response;
  they do not use a Python portal or get stopped early. Iterators remain streamed.
- Both transports implement nonnegative connection retries with exponential
  backoff. A local delayed-listener test proves retries do not consume the body
  before a connection succeeds.
- CLI header output uses request/response hooks rather than httpcore trace events.
  CLI verbose output describes sending a request without inventing connection events.

## Verification and environment

- Current populated test environment: `.venv` (Python 3.12.11). The former
  `/tmp/httpxp-rename-venv` and old logs disappeared when the environment reset.
  System Python lacks the Python dependencies. `.venv/` is ignored by git.
- Native source: Cargo registry under
  `/home/jerlendds/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/`.
- Stable Rust here is 1.97.1. Initial compilation and wheel build succeeded using
  `--ignore-rust-version`; installed nightly is 1.99.0. A normal nightly check was
  completed successfully with `cargo +nightly check --locked` after removal of
  the unused scaffold src/main.rs.
- For local tests, the built `target/debug/lib_native.so` was copied to
  `httpxp/_native.abi3.so` (ignored in git). Rebuild and replace it after Rust changes.
  Never overwrite a shared library while a Python process has it loaded.
- `maturin build --interpreter python --profile dev --ignore-rust-version` built
  an abi3 Python >=3.9 wheel. It predates the latest changes and must be rebuilt.
- Initial full suite: 1372 passed, 49 failed, 1 skipped. Log:
  `/tmp/httpxp-suite.log`. Most failures inspected obsolete httpcore internals;
  others were CLI output, pool limits, and write timeout.
- After fixes: 104 focused tests passed, 2 write-timeout tests deselected.
  Log: `/tmp/httpxp-targeted.log`.
- Initial dedicated native suite: **7 passed**, including custom emulation at
  both scopes and local TLS/CA store/peer-certificate checks.
- Added `tests/test_wreq.py` exercises real local sync/async I/O, streamed
  downloads, form/JSON uploads, option rejection, module-level forwarding,
  custom emulation, local BoringSSL TLS and certificate stores.
- Ruff, mypy, and git diff whitespace checks passed before the final added tests.
- Local sockets need sandbox escalation. Cargo fetch was approved and completed.
- The worktree had extensive existing httpx-to-httpxp rename changes on entry;
  preserve those. User also formatted `src/*.rs` during this work.

## Required remaining work (not an exhaustive substitute for the objective)

1. Inventory ALL builder/options/proxy/retry/redirect/WebSocket/cookie/DNS/TLS
   hooks in the pinned Rust sources; map each to actual implemented Python
   behavior. Include generic trait APIs (timer/executor, resolver, cookie store,
   session cache, Tower layer and connector_layer), not just scalar setters.
2. Further audit streaming/cancellation edge cases: correct per-request connect
   timeout, socket-only write deadline semantics, client close while requests are
   active, synchronous producer cancellation limits, and early responses on a
   keep-alive connection with a known nonzero Content-Length. Initial streaming,
   write timeout, cancellation, source exception and early rejection tests pass.
3. Implement native wreq retry policies (distinct from transport connection
   retries, which now work), custom proxy TLS config and multi-proxy rotation,
   encrypted client keys and the necessary SSLContext compatibility semantics.
4. Complete client/request option coverage, including custom redirect policies
   with Python auth/history/cookie semantics, cookie providers, runtime selection,
   DNS callbacks, custom TLS session-cache providers, middleware, compression options,
   group, defaults, browser platform/header precedence, and request-local custom
   TLS/HTTP protocol options. Verify emulation actually controls on-wire headers
   and TLS/H2 settings, not only constructor acceptance.
5. Finish WebSocket auth challenges/redirects, close-code/reason validation,
   client-owned socket cleanup, and header/emulation precedence. Sync/async
   upgrade/message APIs and HTTP/1+HTTP/2 example execution now pass local tests.
6. Expose response trailers, original headers, peer chain, connection metadata,
   and other response/extension functionality needed by wreq examples.
7. Replace obsolete httpcore-specific tests with meaningful native on-wire tests
   (especially actual HTTP/SOCKS/Unix proxies, TLS/H2 signatures, redirects,
   pooling/reuse, cancellation, retries). Do not count configuration inspection
   alone as proof of network behavior.
8. Add runnable Python equivalents of ALL pasted examples and documentation
   for full option coverage, types, units, precedence, and build prerequisites.
   Update obsolete httpcore dependency/docs/extras/workflows/scripts as needed.
9. Rebuild the final wheel/sdist, test isolated installation/import (without
   httpcore), normal supported-toolchain compilation, full suite, static checks,
   and all example/coverage gates. Audit every objective requirement against
   current authoritative evidence before calling the goal complete.

## Second goal turn verification

The preceding goal turn was progress (native backend implementation and tests).
This turn added upload streaming, write deadlines, cancellation, async cleanup,
connection retries, and empty-body handling. Nothing narrows the original scope.

- Streaming/cancellation/timeout/early-response suite: **33 passed** before retry
  and empty-body regressions were added. Log `/tmp/httpxp-streaming-final.log`.
- Full suite with retries: **1442 passed, 1 failed, 1 skipped** in 25.87s;
  `/tmp/httpxp-full-streaming.log`. Failure was an async OPTIONS empty-body race.
- Fixed that race with native empty-body handling and added repeated GET/OPTIONS/
  DELETE wire tests. The rerun log is `/tmp/httpxp-full-streaming-v2.log`; inspect
  its terminal result before counting it as passing.
- Current native binary was built normally with `cargo +nightly build --lib --locked`
  and copied into the source package after build completion.
- Keep using Rust nightly here (>=1.98 required) to avoid rebuilding all dependencies
  back and forth between the system's old stable and nightly toolchains.
- `test` appeared untracked before this continuation; it contains an OpenSSL TLS
  secrets-log banner. It was not created or removed by this turn.

### Early-response follow-up

- Full rerun v2: 1444 passed, 1 failed, 1 skipped. Streaming POST exposed another
  cleanup race. Added upload stop flag and repeated early-response regression.
- Focused v3: 90 passed, 2 failed; both failures involved cached bodies truncated
  at their declared Content-Length when a server replied early.
- Fixed cached-body handling by keeping those bytes entirely in Rust. Final full
  rerun `/tmp/httpxp-full-streaming-v3.log` completed: **1447 passed, 1 skipped**
  in 27.54s. This includes streaming backpressure, source errors, write deadlines,
  cancellation at headers/body/pool/upload, early responses, retries, and repeated
  empty requests, under both asyncio and Trio.
- Ruff/mypy/Rust check passed before the final rebuild. No claim of full goal
  completion: WebSockets, trait hooks/runtime selection, complete option coverage,
  on-wire protocol validation, examples/docs, and final packaging remain required.

- Final Rust `cargo +nightly check --locked`, Ruff lint/format, mypy, and
  `git diff --check` all pass. No native test/build processes remain live.

## WebSocket and proxy continuation

- Added native split WebSocket send/receive with independent locks, cancellation,
  connection permits, handshake metadata, subprotocols, and the wreq WebSocket
  builder options. Exposed `WebSocket`, `AsyncWebSocket`, `WebSocketMessage`,
  top-level `websocket`, and client methods. Async sending and receiving can run
  concurrently. The HTTP version string for HTTP/2 is normalized to `HTTP/2`.
- WebSocket auth currently applies only the initial auth request. Native upgrade
  errors occur before a failed handshake response can enter Python auth/redirect
  flows. Full challenge/redirect semantics and close validation remain required.
- Added structured native proxies at client/request scopes: scheme selection,
  basic/custom authorization, custom headers, exclusions, Unix sockets. Added
  ordered client proxy lists, native rule clearing, and nullable IPv4/IPv6 bind
  pairs. Ordered rules select the first match; they are not proxy rotation.
- Ordinary Python `Proxy.headers` now reaches native CONNECT requests. Tests
  confirm credentials/custom headers are absent from tunneled origin requests.
- Added native TLS file/environment key logging and LRU session-cache capacity.
  A local TLS 1.2 server proves session resumption on a new connection and checks
  CLIENT_RANDOM output. This does not yet expose custom session-cache callbacks.
- Real network tests cover authenticated HTTP proxy requests, TLS CONNECT,
  request overrides, exclusions, ordered scheme rules, SOCKS5 auth, SOCKS5H
  remote DNS, and client/request Unix socket proxies. Updated the deprecated
  Click download test helper and the oversized WebSocket message expectation
  (native wreq maps it to ReadError).
- Removed the final test import of httpcore. Public transport exception exports
  are checked directly; real network exception tests remain in place.
- Added `examples/private_websocket.py` and `examples/private_proxy.py`. Tests invoke
  their CLI entry points: ten echo messages in sync/async HTTP/1 and HTTP/2
  modes, plus client/request proxy examples. Remaining pasted examples are still
  required, especially middleware/background connector runtime and Compio.
- Added `docs/advanced/wreq.md` and navigation. The page explicitly documents
  this implemented subset and current WebSocket limitations. Examples/docs/work
  log are included in the sdist; a rebuilt archive was inspected for the expected
  Rust sources, lockfile, examples, docs, and absence of caches/native binaries.
- Native build/check and Rust formatting pass. Ruff lint/format and mypy pass
  for 68 source files. Full suite before additional proxy/example regressions:
  **1472 passed, 1 skipped** in 41.09s. A test-server cleanup traceback seen in
  that run was fixed. Focused final proxy+WebSocket+example suite: **35 passed**
  in 19.38s, no server traceback. Final full-suite log:
  `/tmp/httpxp-full-final.log`: **1482 passed, 1 skipped** in 46.87s, terminal
  exit 0 with no server cleanup traceback.
- Packaging validation here covers sdist contents only. A fresh wheel, isolated
  install, all configuration coverage, and the complete example inventory are
  still required. This continuation does not complete or narrow the objective.

## DNS callbacks and request groups

- Added `src/dns.rs`: native wreq Resolve implementation invokes a synchronous
  Python callback with the hostname on a Tokio blocking worker. It accepts an
  iterable of `(IP string, u16 port)` pairs. Static overrides retain precedence;
  URL-explicit ports retain wreq precedence. Numeric IPs bypass resolution.
- Native error conversion now walks the source chain to preserve original
  Python callback exceptions, including object identity. No shared error slot
  is used, so concurrent resolver failures cannot overwrite one another.
- Async clients support the same synchronous resolver. Connect deadlines and
  cancellation abandon waiting and release pool capacity while an already
  executing Python callback finishes independently. Async callable resolvers
  are not supported yet; this limitation is documented.
- Exposed request `group` as a string or unsigned 64-bit integer, retaining
  distinct string/numeric identities. On-wire peer-port tests prove same-group
  connection reuse and different-group separation, including `"1"` versus `1`.
  This partitions native connections, not the Python client's cookies/auth.
- Added `docs/advanced/wreq-coverage.md`, auditing all ClientBuilder and
  RequestBuilder method names in the pinned source, with explicit missing or
  partially covered behavior. This is a builder inventory, not a full audit of
  every nested type/trait or feature-gated API. Broader completion is still due.
- DNS focused tests: **10 passed**, including sync/async routing, original
  callback exceptions, invalid results, static overrides, connect timeout, and
  cancellation while the worker is blocked. Full native regression suite:
  **1495 passed, 1 skipped** in 51.86s, terminal exit 0;
  `/tmp/httpxp-dns-group-suite.log`.
- Rust native build/check and formatting pass. Mypy initially found a missing
  annotation on the new group test helper; the annotation was added and static
  checks rerun. The native library was rebuilt and copied only between test runs.
- Next required implementations remain native middleware/connector runtime,
  Compio timer/executor, retry/redirect callbacks, custom cookie/session stores,
  complete header/emulation/compression precedence, TLS identities, response
  metadata, remaining examples, and isolated packaging validation.
- Python-facing names were normalized: clients, transports, helpers, and request
  extensions use `privacy_options` and `extensions={"private": ...}`. Example
  modules were renamed to `examples/private_proxy.py` and
  `examples/private_websocket.py`; Rust dependency references remain `wreq`.
- Audited `/home/jerlendds/Projects/uiray/scripts/wasm-harness/src/chrome.rs` and
  `src/lib.rs`: it is a separate Rust/wasm Vercel challenge client with a fixed
  Chrome149 profile, cookies, challenge headers, and solver integration. It is
  not part of httpxp and does not represent generic browser support. httpxp now
  documents the supported Chrome, Firefox/private/Android, and Safari/iOS
  emulation profiles and supports independent clients with different profiles.
