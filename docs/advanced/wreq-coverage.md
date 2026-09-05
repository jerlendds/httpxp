# wreq API coverage audit

This is an implementation audit against the pinned wreq **0.16.1** sources,
not a claim of complete support. Method names below refer to the Rust API.
The source locations are `src/client.rs`, `src/client/request.rs`,
`src/dns/resolve.rs`, `src/proxy.rs`, `src/retry.rs`, and the TLS/HTTP option
modules in the Cargo registry. Native behavior and Python compatibility must
both be verified before the migration is complete.

## ClientBuilder

| Rust API | Python mapping / remaining work |
| --- | --- |
| `build` | Client/transport constructors build a native pooled client |
| `timer`, `executor` | Missing; Compio and background-runtime examples remain required |
| `user_agent`, `default_headers` | Python `headers` provides normal defaults; direct native setters and emulation precedence remain to be completed |
| `orig_headers` | Native option; on-wire ordering/signature audit remains |
| `cookie_store` | Native boolean option; normal Python cookies are also maintained |
| `cookie_provider` | Missing custom native provider |
| `gzip`, `brotli`, `zstd`, `deflate`, `no_gzip`, `no_brotli`, `no_zstd`, `no_deflate` | Native decoding disabled; Python decodes responses. Native configuration and precedence remain required |
| `redirect` | Python follow_redirects/max_redirects work; custom native policy parity remains required |
| `referer` | Native boolean option; Python redirect integration remains to be audited |
| `retry` | Missing native policy; transport connection retries already work |
| `proxy`, `no_proxy` | Native options; structured proxies and ordered lists have wire tests |
| `timeout`, `read_timeout`, `connect_timeout` | Native duration options; socket-only write and request-connect semantics remain to be audited |
| `connection_verbose` | Native boolean option |
| `pool_idle_timeout`, `pool_max_idle_per_host`, `pool_max_size` | Native options plus Python Limits/semaphore enforcement |
| `https_only`, `http1_only`, `http2_only` | Native options; Python http1/http2 constructor arguments |
| `http1_options`, `http2_options` | Native option mappings; fingerprint wire audit remains |
| `tcp_nodelay`, `tcp_keepalive`, `tcp_keepalive_interval`, `tcp_keepalive_retries`, `tcp_user_timeout`, `tcp_reuse_address`, `tcp_linger`, `tcp_send_buffer_size`, `tcp_recv_buffer_size`, `tcp_happy_eyeballs_timeout` | Native options; platform-specific behavior still needs coverage |
| `local_address`, `local_addresses`, `interface` | Native options; local bind/proxy tests exist; interface example remains |
| `tls_identity` | PEM certificate/key pair; PKCS12 and encrypted PEM compatibility remain |
| `tls_cert_store` | DER certificate list or PEM stack; complete store-builder parity remains |
| `tls_cert_verification`, `tls_verify_hostname`, `tls_sni`, `tls_min_version`, `tls_max_version` | Native options; full SSLContext compatibility remains |
| `tls_keylog` | Native path or environment selection; file output tested |
| `tls_info` | Native peer certificate metadata; complete peer chain/connection metadata remains |
| `tls_session_cache` | Native LRU capacity, resumption tested; custom provider missing |
| `tls_options` | Primitive fields and named key shares/compressors mapped; custom TLS hooks and wire signatures remain |
| `no_hickory_dns` | Not compiled: dependency feature is disabled |
| `resolve`, `resolve_to_addrs` | `resolve` mapping from hostname to socket-address strings |
| `dns_resolver` | Synchronous Python callback on a native blocking worker; routing, errors, timeout, cancellation, and static override tests |
| `layer`, `connector_layer` | Missing native middleware and background connector runtime |
| `emulation` | Profile names/custom mappings; header and TLS/H2 wire precedence still require full audit |

## RequestBuilder

| Rust API | Python mapping / remaining work |
| --- | --- |
| `from_parts`, `build`, `build_split`, `send`, `try_clone` | Python Request/build_request/send form the public request workflow; arbitrary native extensions and body clone semantics need audit |
| `header`, `headers`, `auth`, `basic_auth`, `bearer_auth` | Existing Python headers/auth APIs |
| `query`, `form`, `json`, `body`, `multipart` | Existing params/data/json/content/files APIs; streamed upload and serialization tests |
| `orig_headers`, `default_headers` | Request native options; full header/emulation precedence remains |
| `timeout`, `read_timeout`, `version` | Request native options |
| `redirect` | Python redirects work; custom policy missing |
| `cookie_provider` | Missing per-request custom native provider |
| `gzip`, `brotli`, `deflate`, `zstd` | Missing native overrides; Python currently decodes |
| `proxy`, `local_address`, `local_addresses`, `interface` | Request native options; HTTP/SOCKS/Unix proxy tests |
| `emulation` | Request native option; subsequent TLS/H1/H2 fine-tuning needs completion |
| `group` | String or unsigned 64-bit ID; wire test checks pooled-connection separation and reuse |

## Other surfaces

The audit must also cover all public fields/constructors in TLS, HTTP/1, HTTP/2,
emulation, certificate stores, cookie/session providers, retry classification,
redirect attempts, middleware, runtimes, proxy selection, WebSocket messages,
and response extensions. The two builder tables are an index for that work,
not a substitute for it. Feature-gated APIs must be evaluated explicitly instead
of silently excluded from the user's requested scope.

Current WebSocket tests include HTTP/1 upgrade, HTTP/2 extended CONNECT, builder
configuration, messages, subprotocols, cancellation, and runnable examples.
Authentication challenges, redirects, close-code/reason validation, and
client-owned cleanup remain. Response trailers, original response headers,
complete peer chains, and other extension metadata remain to be implemented.
