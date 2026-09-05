# Privacy option reference

This reference lists the settings currently accepted by the Python bindings.
It does not imply that every upstream capability is implemented; see the
[coverage audit](wreq-coverage.md) for outstanding work.

Use `privacy_options={...}` on clients, transports, and module helpers. Use
`extensions={"private": {...}}` for request overrides. These are the only
Python names for native privacy configuration; unknown legacy names raise
`TypeError` and are not compatibility aliases.

## Types, defaults, and precedence

Mappings below must be dictionaries at the native boundary. Header collections
are sequences of pairs where indicated. Integers must fit their native widths;
`u16`, `u32`, and `u64` mean unsigned 16-, 32-, and 64-bit values. `usize` is a
nonnegative platform-sized integer. Durations are finite nonnegative seconds;
buffer sizes are bytes. `None` is accepted only where listed.

Omitting `privacy_options` preserves the ordinary Python defaults: certificate
verification enabled, HTTP/1 enabled and HTTP/2 disabled, Python redirects and
response decoding, Python cookie handling, and the client's timeouts/Limits.
Native redirects and decompression start disabled. Native options override the
values derived from Python constructor arguments. A custom transport owns its
own configuration; configure that transport directly. Native options passed to
a Client do not reconfigure a supplied custom transport.

Client emulation is applied first. Remaining client options are applied in
mapping order. Request options are also applied in mapping order. Request
settings override corresponding native client settings; request read timeout
is first derived from `timeout` and can then be overridden inside `private`.
WebSocket keyword options override values supplied inside `private`.

Unspecified nested TLS/HTTP fields take the pinned native library's defaults.
Supplying a nested mapping creates a fresh options object; it is not a deep
merge with a profile. Thus a nested override can replace a profile's protocol
settings. Browser headers and original-header ordering still need a complete
wire-level precedence audit. Privacy settings do not promise anonymity or an
exact browser fingerprint.

## Browser and client profiles

The separate sibling `scripts/wasm-harness` project contains a Vercel challenge
client that currently hard-codes a Chrome149 session and challenge-specific
logic. `httpxp` does not run that solver. Its Python API supports the reusable
client-emulation layer through `privacy_options={"emulation": ...}` for Chrome,
Firefox (including private and Android variants), and Safari/iOS profiles:

```python
chrome = httpxp.Client(privacy_options={"emulation": "Chrome149"})
firefox = httpxp.Client(privacy_options={"emulation": "FirefoxPrivate135"})
safari = httpxp.Client(privacy_options={"emulation": "Safari18_3"})
```

Profiles emulate request, TLS, and HTTP/2 characteristics. They do not launch
a browser, execute JavaScript, solve anti-bot challenges, or provide browser
storage. Multiple clients may use different profiles independently.

## Client settings

| Key(s) | Type and behavior |
| --- | --- |
| `tls_cert_verification`, `tls_verify_hostname`, `tls_sni` | bool; certificate chain, hostname, and SNI controls |
| `tls_info` | bool; expose peer leaf certificate in response extensions |
| `tcp_nodelay`, `tcp_reuse_address` | bool; TCP socket flags |
| `https_only` | bool; reject non-HTTPS destinations when enabled |
| `referer` | bool; native redirect Referer setting; Python redirects remain separate |
| `cookie_store` | bool; native in-memory jar, separate from Python cookie handling |
| `connection_verbose` | bool; native verbosity, currently no Python logging subscriber bridge |
| `timeout`, `read_timeout`, `connect_timeout` | seconds; native total request, read, and connection deadlines |
| `pool_idle_timeout` | seconds or None; idle connection expiry |
| `tcp_keepalive`, `tcp_keepalive_interval`, `tcp_user_timeout`, `tcp_linger`, `tcp_happy_eyeballs_timeout` | seconds or None; socket keepalive, retransmit lifetime, close linger, or address-race delay |
| `pool_max_idle_per_host`, `pool_max_size` | usize; native pool limits; Python Limits also applies |
| `tcp_keepalive_retries` | u32 or None; keepalive retry count |
| `tcp_send_buffer_size`, `tcp_recv_buffer_size` | usize or None; socket buffer sizes |
| `http1_only`, `http2_only` | bool; True applies the version restriction, False leaves it alone |
| `tls_min_version`, `tls_max_version` | TLS version string: 1.0, 1.1, 1.2, 1.3 (or TLS_1_0 through TLS_1_3) |
| `tls_options`, `http1_options`, `http2_options` | dict; protocol options documented below |
| `emulation` | profile string or mapping; see Emulation below |
| `tls_cert_store` | sequence of DER certificate byte strings; replaces trust store |
| `tls_cert_store_pem` | bytes containing a PEM certificate stack; replaces trust store |
| `tls_identity` | (certificate PEM bytes, private-key PEM bytes); unencrypted PEM identity |
| `dns_resolver` | synchronous callable(hostname) returning iterable of (IP string, u16 port); see guide |
| `resolve` | dict of hostname to list of socket-address strings, e.g. 127.0.0.1:8080 or [::1]:8080 |
| `proxy` | proxy URL string or mapping; see proxy fields below |
| `proxies` | ordered iterable of proxy configurations; first match wins, no rotation |
| `no_proxy` | bool; True clears native proxy rules at this point in mapping order |
| `tls_keylog` | string file path, or env to read SSLKEYLOGFILE |
| `tls_session_cache` | usize; per-host native LRU session capacity |
| `orig_headers` | list of original header name strings |
| `local_address` | IP address string or None; source bind address |
| `local_addresses` | (IPv4 string or None, IPv6 string or None) |
| `interface` | string interface name on supported operating systems |
| `uds` | Unix socket path string; Unix platforms only |

The underscore-prefixed fields used internally for cancellation and pool/write
accounting are implementation details, not public privacy settings.

## Request settings

These are the complete currently accepted keys inside `extensions["private"]`:

| Key(s) | Type and behavior |
| --- | --- |
| `default_headers` | bool; enable/disable native default headers; does not remove headers Python already added |
| `timeout`, `read_timeout` | seconds; native request/read deadlines |
| `version` | `"1.0"`, `"1.1"`, `"2"`, or `"HTTP/1.0"`, `"HTTP/1.1"`, `"HTTP/2"` |
| `orig_headers` | list of original header name strings |
| `emulation` | profile string or emulation mapping |
| `local_address`, `local_addresses`, `interface`, `proxy`, `uds` | Same forms as client settings |
| `group` | string or u64; partition native connection pool identity |

Top-level `tls_options`, `http1_options`, and `http2_options` are not currently
accepted at request scope. Supply them inside an `emulation` mapping instead.
Client-only settings in a request raise `ValueError`.

## Nested TLS settings

Use these inside `tls_options`, including `emulation["tls_options"]`.

| Key | Python type / values |
| --- | --- |
| `alpn_protocols` | list[str]: h2, http/1.1, h3 (None is not accepted) |
| `alps_protocols` | list[str] or None: h2, http/1.1, h3 |
| `alps_use_new_codepoint` | bool |
| `session_ticket` | bool |
| `min_tls_version` | TLS version string or None (same spellings as client TLS bounds) |
| `max_tls_version` | TLS version string or None (same spellings as client TLS bounds) |
| `pre_shared_key` | bool |
| `enable_ech_grease` | bool |
| `permute_extensions` | bool or None |
| `grease_enabled` | bool or None |
| `enable_ocsp_stapling` | bool |
| `enable_signed_cert_timestamps` | bool |
| `record_size_limit` | u16 or None |
| `psk_skip_session_ticket` | bool |
| `key_shares` | list[str] or None; named algorithms below |
| `psk_dhe_ke` | bool |
| `renegotiation` | bool |
| `delegated_credentials` | str or None |
| `curves_list` | str or None |
| `sigalgs_list` | str or None |
| `cipher_list` | str or None |
| `preserve_tls13_cipher_list` | bool or None |
| `certificate_compressors` | list[str] or None: brotli, zlib, zstd |
| `extension_permutation` | list[u16] or None; TLS extension IDs in desired order |
| `aes_hw_override` | bool or None |
| `random_aes_hw_override` | bool |

Key shares: `P256`, `P384`, `P521`, `X25519`, `X25519_MLKEM768`,
`X25519_KYBER768_DRAFT00`, `P256_KYBER768_DRAFT00`, `MLKEM1024`,
`FFDHE2048`, `FFDHE3072`.

TLS string lists (`curves_list`, `sigalgs_list`, `cipher_list`, and
`delegated_credentials`) use the underlying TLS library's syntax.
Advertising h3 through ALPN/ALPS does not implement an HTTP/3 transport.

## Nested HTTP/1 settings

Use inside `http1_options`, including in emulation.

| Key | Python type / values |
| --- | --- |
| `h09_responses` | bool |
| `h1_writev` | bool or None |
| `h1_max_headers` | usize or None |
| `h1_read_buf_exact_size` | usize or None |
| `h1_max_buf_size` | usize or None |
| `ignore_invalid_headers_in_responses` | bool |
| `allow_spaces_after_header_name_in_responses` | bool |
| `allow_obsolete_multiline_headers_in_responses` | bool |

Aliases: `http09_responses` = `h09_responses`, `writev` = `h1_writev`,
`max_headers` = `h1_max_headers`, `read_buf_exact_size` = `h1_read_buf_exact_size`,
`max_buf_size` = `h1_max_buf_size`. Use one spelling per setting.

## Nested HTTP/2 settings

Use inside `http2_options`, including in emulation.

| Key | Python type / values |
| --- | --- |
| `adaptive_window` | bool |
| `initial_stream_id` | u32 or None |
| `initial_conn_window_size` | u32 |
| `initial_window_size` | u32 |
| `initial_max_send_streams` | usize |
| `max_frame_size` | u32 or None |
| `keep_alive_interval` | seconds or None |
| `keep_alive_timeout` | seconds |
| `keep_alive_while_idle` | bool |
| `max_concurrent_reset_streams` | usize or None |
| `max_send_buffer_size` | usize |
| `max_concurrent_streams` | u32 or None |
| `max_header_list_size` | u32 or None |
| `max_pending_accept_reset_streams` | usize or None |
| `enable_push` | bool or None |
| `header_table_size` | u32 or None |
| `enable_connect_protocol` | bool or None |
| `no_rfc7540_priorities` | bool or None |
| `headers_pseudo_order` | list[str] or None: Method, Scheme, Authority, Path, Protocol, Status; case-insensitive, optional leading colon |
| `headers_stream_dependency` | (u32 stream ID, u8 weight, bool exclusive) or None |
| `settings_order` | list[str] or None; named settings below |
| `priorities` | list[(u32 stream ID, u32 dependency ID, u8 weight, bool exclusive)] or None |

Aliases: `initial_connection_window_size` = `initial_conn_window_size`,
`max_send_buf_size` = `max_send_buffer_size`.

Settings names: `HeaderTableSize`, `EnablePush`, `MaxConcurrentStreams`,
`InitialWindowSize`, `MaxFrameSize`, `MaxHeaderListSize`,
`EnableConnectProtocol`, `NoRfc7540Priorities`.

Stream/dependency IDs are at most 2^31-1. Priority stream IDs must be nonzero
and must differ from their dependency. Weights use the native encoded u8
representation (0–255). Protocol-specific constraints still apply to window,
frame, stream, and buffer sizes; acceptance by the binding does not make an
arbitrary combination a valid peer configuration.

## Emulation

A profile name string selects a built-in profile. A mapping accepts `profile`
(optional name), `tls_options`, `http1_options`, `http2_options`, `orig_headers`,
and `headers` (list of string name/value pairs). Without `profile`, the mapping
starts from an empty emulation. Protocol mappings replace the profile's
corresponding options object. Extra headers append to profile headers.

Accepted names and aliases in this build:

| Profile | Alias |
| --- | --- |
| `Chrome100` | `chrome_100` |
| `Chrome101` | `chrome_101` |
| `Chrome104` | `chrome_104` |
| `Chrome105` | `chrome_105` |
| `Chrome106` | `chrome_106` |
| `Chrome107` | `chrome_107` |
| `Chrome108` | `chrome_108` |
| `Chrome109` | `chrome_109` |
| `Chrome110` | `chrome_110` |
| `Chrome114` | `chrome_114` |
| `Chrome116` | `chrome_116` |
| `Chrome117` | `chrome_117` |
| `Chrome118` | `chrome_118` |
| `Chrome119` | `chrome_119` |
| `Chrome120` | `chrome_120` |
| `Chrome123` | `chrome_123` |
| `Chrome124` | `chrome_124` |
| `Chrome126` | `chrome_126` |
| `Chrome127` | `chrome_127` |
| `Chrome128` | `chrome_128` |
| `Chrome129` | `chrome_129` |
| `Chrome130` | `chrome_130` |
| `Chrome131` | `chrome_131` |
| `Chrome132` | `chrome_132` |
| `Chrome133` | `chrome_133` |
| `Chrome134` | `chrome_134` |
| `Chrome135` | `chrome_135` |
| `Chrome136` | `chrome_136` |
| `Chrome137` | `chrome_137` |
| `Chrome138` | `chrome_138` |
| `Chrome139` | `chrome_139` |
| `Chrome140` | `chrome_140` |
| `Chrome141` | `chrome_141` |
| `Chrome142` | `chrome_142` |
| `Chrome143` | `chrome_143` |
| `Chrome144` | `chrome_144` |
| `Chrome145` | `chrome_145` |
| `Chrome146` | `chrome_146` |
| `Chrome147` | `chrome_147` |
| `Chrome148` | `chrome_148` |
| `Chrome149` | `chrome_149` |
| `Edge101` | `edge_101` |
| `Edge122` | `edge_122` |
| `Edge127` | `edge_127` |
| `Edge131` | `edge_131` |
| `Edge134` | `edge_134` |
| `Edge135` | `edge_135` |
| `Edge136` | `edge_136` |
| `Edge137` | `edge_137` |
| `Edge138` | `edge_138` |
| `Edge139` | `edge_139` |
| `Edge140` | `edge_140` |
| `Edge141` | `edge_141` |
| `Edge142` | `edge_142` |
| `Edge143` | `edge_143` |
| `Edge144` | `edge_144` |
| `Edge145` | `edge_145` |
| `Edge146` | `edge_146` |
| `Edge147` | `edge_147` |
| `Edge148` | `edge_148` |
| `Opera116` | `opera_116` |
| `Opera117` | `opera_117` |
| `Opera118` | `opera_118` |
| `Opera119` | `opera_119` |
| `Opera120` | `opera_120` |
| `Opera121` | `opera_121` |
| `Opera122` | `opera_122` |
| `Opera123` | `opera_123` |
| `Opera124` | `opera_124` |
| `Opera125` | `opera_125` |
| `Opera126` | `opera_126` |
| `Opera127` | `opera_127` |
| `Opera128` | `opera_128` |
| `Opera129` | `opera_129` |
| `Opera130` | `opera_130` |
| `Opera131` | `opera_131` |
| `Firefox109` | `firefox_109` |
| `Firefox117` | `firefox_117` |
| `Firefox128` | `firefox_128` |
| `Firefox133` | `firefox_133` |
| `Firefox135` | `firefox_135` |
| `FirefoxPrivate135` | `firefox_private_135` |
| `FirefoxAndroid135` | `firefox_android_135` |
| `Firefox136` | `firefox_136` |
| `FirefoxPrivate136` | `firefox_private_136` |
| `Firefox139` | `firefox_139` |
| `Firefox142` | `firefox_142` |
| `Firefox143` | `firefox_143` |
| `Firefox144` | `firefox_144` |
| `Firefox145` | `firefox_145` |
| `Firefox146` | `firefox_146` |
| `Firefox147` | `firefox_147` |
| `Firefox148` | `firefox_148` |
| `Firefox149` | `firefox_149` |
| `Firefox150` | `firefox_150` |
| `Firefox151` | `firefox_151` |
| `SafariIos17_2` | `safari_ios_17.2` |
| `SafariIos17_4_1` | `safari_ios_17.4.1` |
| `SafariIos16_5` | `safari_ios_16.5` |
| `Safari15_3` | `safari_15.3` |
| `Safari15_5` | `safari_15.5` |
| `Safari15_6_1` | `safari_15.6.1` |
| `Safari16` | `safari_16` |
| `Safari16_5` | `safari_16.5` |
| `Safari17_0` | `safari_17.0` |
| `Safari17_2_1` | `safari_17.2.1` |
| `Safari17_4_1` | `safari_17.4.1` |
| `Safari17_5` | `safari_17.5` |
| `Safari17_6` | `safari_17.6` |
| `Safari18` | `safari_18` |
| `SafariIPad18` | `safari_ipad_18` |
| `Safari18_2` | `safari_18.2` |
| `SafariIos18_1_1` | `safari_ios_18.1.1` |
| `Safari18_3` | `safari_18.3` |
| `Safari18_3_1` | `safari_18.3.1` |
| `Safari18_5` | `safari_18.5` |
| `Safari26` | `safari_26` |
| `Safari26_1` | `safari_26.1` |
| `Safari26_2` | `safari_26.2` |
| `Safari26_3` | `safari_26.3` |
| `Safari26_4` | `safari_26.4` |
| `SafariIPad26` | `safari_ipad_26` |
| `SafariIpad26_2` | `safari_ipad_26.2` |
| `SafariIos26` | `safari_ios_26` |
| `SafariIos26_2` | `safari_ios_26.2` |
| `OkHttp3_9` | `okhttp_3.9` |
| `OkHttp3_11` | `okhttp_3.11` |
| `OkHttp3_13` | `okhttp_3.13` |
| `OkHttp3_14` | `okhttp_3.14` |
| `OkHttp4_9` | `okhttp_4.9` |
| `OkHttp4_10` | `okhttp_4.10` |
| `OkHttp4_12` | `okhttp_4.12` |
| `OkHttp5` | `okhttp_5` |

## Proxy and WebSocket settings

The [proxy guide](wreq.md#proxies-and-local-addresses) documents every proxy
mapping field: `url`, `scheme`, `basic_auth`, `custom_http_auth`,
`custom_http_headers`, and `no_proxy`.

WebSocket builder keyword options (also accepted inside `private` for an
upgrade) are:

| Key | Type / behavior |
| --- | --- |
| `version` | 1.1 or 2, with the HTTP/ prefix also accepted |
| `protocols` | list[str]; requested subprotocols |
| `accept_key` | str; custom Sec-WebSocket-Key nonce; the expected accept hash is derived from it |
| `max_frame_size`, `max_message_size` | usize or None; incoming size limits |
| `read_buffer_size` | positive usize; default 128 KiB |
| `write_buffer_size` | usize; default 128 KiB |
| `max_write_buffer_size` | usize; must exceed write_buffer_size; default platform maximum |
| `accept_unmasked_frames` | bool; native incoming frame validation option |

See the [WebSocket guide](wreq.md#websockets) for context managers, messages,
concurrency, and current handshake/cleanup limitations. Constructors, message
methods, and error behavior are part of the [API reference](../api.md).
