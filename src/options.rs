use crate::{duration, value_error};
use pyo3::{prelude::*, types::PyDict};
use std::net::IpAddr;
use wreq::{ClientBuilder, RequestBuilder, header::OrigHeaderMap, tls::TlsVersion};
fn tls_version(v: &Bound<'_, PyAny>) -> PyResult<TlsVersion> {
    match v.extract::<String>()?.as_str() {
        "1.0" | "TLS_1_0" => Ok(TlsVersion::TLS_1_0),
        "1.1" | "TLS_1_1" => Ok(TlsVersion::TLS_1_1),
        "1.2" | "TLS_1_2" => Ok(TlsVersion::TLS_1_2),
        "1.3" | "TLS_1_3" => Ok(TlsVersion::TLS_1_3),
        _ => Err(value_error("invalid TLS version")),
    }
}
fn orig_headers(v: &Bound<'_, PyAny>) -> PyResult<OrigHeaderMap> {
    let mut h = OrigHeaderMap::new();
    for name in v.extract::<Vec<String>>()? {
        h.insert(name);
    }
    Ok(h)
}
fn tls(d: &Bound<'_, PyAny>) -> PyResult<wreq::tls::TlsOptions> {
    let mut o = wreq::tls::TlsOptions::default();
    for (k, v) in d.cast::<PyDict>()?.iter() {
        match k.extract::<String>()?.as_str() {
            "alps_use_new_codepoint" => o.alps_use_new_codepoint = v.extract()?,
            "session_ticket" => o.session_ticket = v.extract()?,
            "min_tls_version" => {
                o.min_tls_version = if v.is_none() {
                    None
                } else {
                    Some(tls_version(&v)?)
                }
            }
            "max_tls_version" => {
                o.max_tls_version = if v.is_none() {
                    None
                } else {
                    Some(tls_version(&v)?)
                }
            }
            "pre_shared_key" => o.pre_shared_key = v.extract()?,
            "enable_ech_grease" => o.enable_ech_grease = v.extract()?,
            "permute_extensions" => o.permute_extensions = v.extract()?,
            "grease_enabled" => o.grease_enabled = v.extract()?,
            "enable_ocsp_stapling" => o.enable_ocsp_stapling = v.extract()?,
            "enable_signed_cert_timestamps" => o.enable_signed_cert_timestamps = v.extract()?,
            "record_size_limit" => o.record_size_limit = v.extract()?,
            "psk_skip_session_ticket" => o.psk_skip_session_ticket = v.extract()?,
            "psk_dhe_ke" => o.psk_dhe_ke = v.extract()?,
            "renegotiation" => o.renegotiation = v.extract()?,
            "delegated_credentials" => {
                o.delegated_credentials = v.extract::<Option<String>>()?.map(Into::into)
            }
            "curves_list" => o.curves_list = v.extract::<Option<String>>()?.map(Into::into),
            "sigalgs_list" => o.sigalgs_list = v.extract::<Option<String>>()?.map(Into::into),
            "cipher_list" => o.cipher_list = v.extract::<Option<String>>()?.map(Into::into),
            "preserve_tls13_cipher_list" => o.preserve_tls13_cipher_list = v.extract()?,
            "aes_hw_override" => o.aes_hw_override = v.extract()?,
            "random_aes_hw_override" => o.random_aes_hw_override = v.extract()?,
            "alpn_protocols" => {
                o.alpn_protocols = Some(
                    v.extract::<Vec<String>>()?
                        .iter()
                        .map(|p| match p.as_str() {
                            "h2" => Ok(wreq::tls::AlpnProtocol::HTTP2),
                            "http/1.1" => Ok(wreq::tls::AlpnProtocol::HTTP1),
                            "h3" => Ok(wreq::tls::AlpnProtocol::HTTP3),
                            _ => Err(value_error("invalid ALPN protocol")),
                        })
                        .collect::<PyResult<Vec<_>>>()?
                        .into(),
                )
            }
            "alps_protocols" => {
                o.alps_protocols = if v.is_none() {
                    None
                } else {
                    Some(
                        v.extract::<Vec<String>>()?
                            .iter()
                            .map(|p| match p.as_str() {
                                "h2" => Ok(wreq::tls::AlpsProtocol::HTTP2),
                                "http/1.1" => Ok(wreq::tls::AlpsProtocol::HTTP1),
                                "h3" => Ok(wreq::tls::AlpsProtocol::HTTP3),
                                _ => Err(value_error("invalid ALPS protocol")),
                            })
                            .collect::<PyResult<Vec<_>>>()?
                            .into(),
                    )
                }
            }
            "extension_permutation" => {
                o.extension_permutation = v.extract::<Option<Vec<u16>>>()?.map(|a| {
                    a.into_iter()
                        .map(wreq::tls::ExtensionType::from)
                        .collect::<Vec<_>>()
                        .into()
                })
            }
            "certificate_compressors" => {
                o.certificate_compressors = if v.is_none() {
                    None
                } else {
                    Some(
                        v.extract::<Vec<String>>()?
                            .iter()
                            .map(|a| {
                                use wreq_util::emulate::compress::*;
                                let c: &'static dyn wreq::tls::compress::CertificateCompressor =
                                    match a.as_str() {
                                        "brotli" => &BrotliCompressor,
                                        "zlib" => &ZlibCompressor,
                                        "zstd" => &ZstdCompressor,
                                        _ => {
                                            return Err(value_error(
                                                "invalid certificate compressor",
                                            ));
                                        }
                                    };
                                Ok(c)
                            })
                            .collect::<PyResult<Vec<_>>>()?
                            .into(),
                    )
                }
            }
            "key_shares" => {
                o.key_shares = if v.is_none() {
                    None
                } else {
                    Some(
                        v.extract::<Vec<String>>()?
                            .iter()
                            .map(|a| {
                                use wreq::tls::KeyShare;
                                match a.as_str() {
                                    "P256" => Ok(KeyShare::P256),
                                    "P384" => Ok(KeyShare::P384),
                                    "P521" => Ok(KeyShare::P521),
                                    "X25519" => Ok(KeyShare::X25519),
                                    "X25519_MLKEM768" => Ok(KeyShare::X25519_MLKEM768),
                                    "X25519_KYBER768_DRAFT00" => {
                                        Ok(KeyShare::X25519_KYBER768_DRAFT00)
                                    }
                                    "P256_KYBER768_DRAFT00" => Ok(KeyShare::P256_KYBER768_DRAFT00),
                                    "MLKEM1024" => Ok(KeyShare::MLKEM1024),
                                    "FFDHE2048" => Ok(KeyShare::FFDHE2048),
                                    "FFDHE3072" => Ok(KeyShare::FFDHE3072),
                                    _ => Err(value_error("invalid key share")),
                                }
                            })
                            .collect::<PyResult<Vec<_>>>()?
                            .into(),
                    )
                }
            }
            _ => return Err(value_error(format!("unknown tls option: {k}"))),
        }
    }
    Ok(o)
}
fn http1(d: &Bound<'_, PyAny>) -> PyResult<wreq::http1::Http1Options> {
    let mut o = wreq::http1::Http1Options::default();
    for (k, v) in d.cast::<PyDict>()?.iter() {
        match k.extract::<String>()?.as_str() {
            "h09_responses" => o.h09_responses = v.extract()?,
            "h1_writev" => o.h1_writev = v.extract()?,
            "h1_max_headers" => o.h1_max_headers = v.extract()?,
            "h1_read_buf_exact_size" => o.h1_read_buf_exact_size = v.extract()?,
            "h1_max_buf_size" => o.h1_max_buf_size = v.extract()?,
            "ignore_invalid_headers_in_responses" => {
                o.ignore_invalid_headers_in_responses = v.extract()?
            }
            "allow_spaces_after_header_name_in_responses" => {
                o.allow_spaces_after_header_name_in_responses = v.extract()?
            }
            "allow_obsolete_multiline_headers_in_responses" => {
                o.allow_obsolete_multiline_headers_in_responses = v.extract()?
            }
            "http09_responses" => o.h09_responses = v.extract()?,
            "writev" => o.h1_writev = v.extract()?,
            "max_headers" => o.h1_max_headers = v.extract()?,
            "read_buf_exact_size" => o.h1_read_buf_exact_size = v.extract()?,
            "max_buf_size" => o.h1_max_buf_size = v.extract()?,
            _ => return Err(value_error(format!("unknown http1 option: {k}"))),
        }
    }
    Ok(o)
}
fn http2(d: &Bound<'_, PyAny>) -> PyResult<wreq::http2::Http2Options> {
    let mut o = wreq::http2::Http2Options::default();
    for (k, v) in d.cast::<PyDict>()?.iter() {
        match k.extract::<String>()?.as_str() {
            "adaptive_window" => o.adaptive_window = v.extract()?,
            "initial_stream_id" => o.initial_stream_id = v.extract()?,
            "initial_conn_window_size" => o.initial_conn_window_size = v.extract()?,
            "initial_window_size" => o.initial_window_size = v.extract()?,
            "initial_max_send_streams" => o.initial_max_send_streams = v.extract()?,
            "max_frame_size" => o.max_frame_size = v.extract()?,
            "keep_alive_interval" => {
                o.keep_alive_interval = if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                }
            }
            "keep_alive_timeout" => o.keep_alive_timeout = duration(&v)?,
            "keep_alive_while_idle" => o.keep_alive_while_idle = v.extract()?,
            "max_concurrent_reset_streams" => o.max_concurrent_reset_streams = v.extract()?,
            "max_send_buffer_size" => o.max_send_buffer_size = v.extract()?,
            "max_concurrent_streams" => o.max_concurrent_streams = v.extract()?,
            "max_header_list_size" => o.max_header_list_size = v.extract()?,
            "max_pending_accept_reset_streams" => {
                o.max_pending_accept_reset_streams = v.extract()?
            }
            "enable_push" => o.enable_push = v.extract()?,
            "header_table_size" => o.header_table_size = v.extract()?,
            "enable_connect_protocol" => o.enable_connect_protocol = v.extract()?,
            "no_rfc7540_priorities" => o.no_rfc7540_priorities = v.extract()?,
            "initial_connection_window_size" => o.initial_conn_window_size = v.extract()?,
            "max_send_buf_size" => o.max_send_buffer_size = v.extract()?,
            "headers_pseudo_order" => {
                o.headers_pseudo_order = if v.is_none() {
                    None
                } else {
                    Some(
                        wreq::http2::PseudoOrder::builder()
                            .extend(
                                v.extract::<Vec<String>>()?
                                    .iter()
                                    .map(|a| {
                                        use wreq::http2::PseudoId;
                                        match a.trim_start_matches(':').to_lowercase().as_str() {
                                            "method" => Ok(PseudoId::Method),
                                            "path" => Ok(PseudoId::Path),
                                            "authority" => Ok(PseudoId::Authority),
                                            "scheme" => Ok(PseudoId::Scheme),
                                            "protocol" => Ok(PseudoId::Protocol),
                                            "status" => Ok(PseudoId::Status),
                                            _ => Err(value_error("invalid pseudo-header")),
                                        }
                                    })
                                    .collect::<PyResult<Vec<_>>>()?,
                            )
                            .build(),
                    )
                }
            }
            "headers_stream_dependency" => {
                o.headers_stream_dependency = if v.is_none() {
                    None
                } else {
                    Some(dependency(v.extract()?)?)
                }
            }
            "priorities" => {
                o.priorities = if v.is_none() {
                    None
                } else {
                    Some(
                        wreq::http2::Priorities::builder()
                            .extend(
                                v.extract::<Vec<(u32, u32, u8, bool)>>()?
                                    .into_iter()
                                    .map(|(id, dep, weight, exclusive)| {
                                        if id == 0 || id > 0x7fff_ffff || id == dep {
                                            return Err(value_error("invalid priority stream id"));
                                        }
                                        Ok(wreq::http2::Priority::new(
                                            id.into(),
                                            dependency((dep, weight, exclusive))?,
                                        ))
                                    })
                                    .collect::<PyResult<Vec<_>>>()?,
                            )
                            .build(),
                    )
                }
            }
            "settings_order" => {
                o.settings_order = if v.is_none() {
                    None
                } else {
                    Some(
                        wreq::http2::SettingsOrder::builder()
                            .extend(
                                v.extract::<Vec<String>>()?
                                    .iter()
                                    .map(|a| {
                                        use wreq::http2::SettingId;
                                        match a.as_str() {
                                            "HeaderTableSize" => Ok(SettingId::HeaderTableSize),
                                            "EnablePush" => Ok(SettingId::EnablePush),
                                            "MaxConcurrentStreams" => {
                                                Ok(SettingId::MaxConcurrentStreams)
                                            }
                                            "InitialWindowSize" => Ok(SettingId::InitialWindowSize),
                                            "MaxFrameSize" => Ok(SettingId::MaxFrameSize),
                                            "MaxHeaderListSize" => Ok(SettingId::MaxHeaderListSize),
                                            "EnableConnectProtocol" => {
                                                Ok(SettingId::EnableConnectProtocol)
                                            }
                                            "NoRfc7540Priorities" => {
                                                Ok(SettingId::NoRfc7540Priorities)
                                            }
                                            _ => Err(value_error("invalid HTTP/2 setting")),
                                        }
                                    })
                                    .collect::<PyResult<Vec<_>>>()?,
                            )
                            .build(),
                    )
                }
            }
            _ => return Err(value_error(format!("unknown http2 option: {k}"))),
        }
    }
    Ok(o)
}
pub fn client_options(mut b: ClientBuilder, d: &Bound<'_, PyDict>) -> PyResult<ClientBuilder> {
    if let Some(v) = d.get_item("emulation")? {
        b = b.emulation(emulation(&v)?);
    }
    for (k, v) in d.iter() {
        match k.extract::<String>()?.as_str() {
            "tls_cert_verification" => b = b.tls_cert_verification(v.extract()?),
            "tls_verify_hostname" => b = b.tls_verify_hostname(v.extract()?),
            "tls_sni" => b = b.tls_sni(v.extract()?),
            "tls_info" => b = b.tls_info(v.extract()?),
            "tcp_nodelay" => b = b.tcp_nodelay(v.extract()?),
            "tcp_reuse_address" => b = b.tcp_reuse_address(v.extract()?),
            "https_only" => b = b.https_only(v.extract()?),
            "referer" => b = b.referer(v.extract()?),
            "cookie_store" => b = b.cookie_store(v.extract()?),
            "connection_verbose" => b = b.connection_verbose(v.extract()?),
            "timeout" => b = b.timeout(duration(&v)?),
            "read_timeout" => b = b.read_timeout(duration(&v)?),
            "connect_timeout" => b = b.connect_timeout(duration(&v)?),
            "pool_idle_timeout" => {
                b = b.pool_idle_timeout(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "tcp_keepalive" => {
                b = b.tcp_keepalive(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "tcp_keepalive_interval" => {
                b = b.tcp_keepalive_interval(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "tcp_user_timeout" => {
                b = b.tcp_user_timeout(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "tcp_linger" => {
                b = b.tcp_linger(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "tcp_happy_eyeballs_timeout" => {
                b = b.tcp_happy_eyeballs_timeout(if v.is_none() {
                    None
                } else {
                    Some(duration(&v)?)
                })
            }
            "pool_max_idle_per_host" => b = b.pool_max_idle_per_host(v.extract::<usize>()?),
            "pool_max_size" => b = b.pool_max_size(v.extract::<usize>()?),
            "tcp_keepalive_retries" => b = b.tcp_keepalive_retries(v.extract::<Option<u32>>()?),
            "tcp_send_buffer_size" => b = b.tcp_send_buffer_size(v.extract::<Option<usize>>()?),
            "tcp_recv_buffer_size" => b = b.tcp_recv_buffer_size(v.extract::<Option<usize>>()?),
            "http1_only" => {
                if v.extract::<bool>()? {
                    b = b.http1_only();
                }
            }
            "http2_only" => {
                if v.extract::<bool>()? {
                    b = b.http2_only();
                }
            }
            "tls_min_version" => b = b.tls_min_version(tls_version(&v)?),
            "tls_max_version" => b = b.tls_max_version(tls_version(&v)?),
            "tls_options" => b = b.tls_options(tls(&v)?),
            "http1_options" => b = b.http1_options(http1(&v)?),
            "http2_options" => b = b.http2_options(http2(&v)?),
            "emulation" => {}
            "tls_cert_store" => {
                b = b.tls_cert_store(
                    wreq::tls::trust::CertStore::from_der_certs(
                        v.extract::<Vec<Vec<u8>>>()?.iter().map(Vec::as_slice),
                    )
                    .map_err(value_error)?,
                )
            }
            "tls_cert_store_pem" => {
                b = b.tls_cert_store(
                    wreq::tls::trust::CertStore::from_pem_stack(&v.extract::<Vec<u8>>()?)
                        .map_err(value_error)?,
                )
            }
            "tls_identity" => {
                let (cert, key) = v.extract::<(Vec<u8>, Vec<u8>)>()?;
                b = b.tls_identity(
                    wreq::tls::trust::Identity::from_pkcs8_pem(&cert, &key).map_err(value_error)?,
                );
            }
            "dns_resolver" => {
                if !v.is_callable() {
                    return Err(value_error("dns_resolver must be callable"));
                }
                b = b.dns_resolver(crate::dns::PythonResolver(std::sync::Arc::new(v.unbind())));
            }
            "resolve" => {
                for (domain, addrs) in v.cast::<PyDict>()?.iter() {
                    let addrs = addrs
                        .extract::<Vec<String>>()?
                        .iter()
                        .map(|a| a.parse().map_err(value_error))
                        .collect::<PyResult<Vec<std::net::SocketAddr>>>()?;
                    b = b.resolve_to_addrs(domain.extract::<String>()?, addrs);
                }
            }
            "proxies" => {
                for item in v.try_iter()? {
                    b = b.proxy(proxy(&item?)?);
                }
            }
            "no_proxy" => {
                if v.extract::<bool>()? {
                    b = b.no_proxy();
                }
            }
            "tls_keylog" => {
                let path = v.extract::<String>()?;
                b = b.tls_keylog(if path == "env" {
                    wreq::tls::keylog::KeyLog::from_env()
                } else {
                    wreq::tls::keylog::KeyLog::from_file(path)
                });
            }
            "tls_session_cache" => {
                b = b.tls_session_cache(wreq::tls::session::LruTlsSessionCache::new(v.extract()?))
            }
            "orig_headers" => b = b.orig_headers(orig_headers(&v)?),
            "local_address" => {
                b = b.local_address(
                    v.extract::<Option<String>>()?
                        .map(|a| a.parse::<IpAddr>().map_err(value_error))
                        .transpose()?,
                )
            }
            "local_addresses" => {
                let (ipv4, ipv6) = v.extract::<(Option<String>, Option<String>)>()?;
                b = b.local_addresses(
                    ipv4.map(|a| a.parse::<std::net::Ipv4Addr>().map_err(value_error))
                        .transpose()?,
                    ipv6.map(|a| a.parse::<std::net::Ipv6Addr>().map_err(value_error))
                        .transpose()?,
                );
            }
            "interface" => b = b.interface(v.extract::<String>()?),
            "proxy" => b = b.proxy(proxy(&v)?),
            #[cfg(unix)]
            "uds" => b = b.proxy(wreq::Proxy::unix(v.extract::<String>()?).map_err(value_error)?),
            _ => return Err(value_error(format!("unknown client option: {k}"))),
        }
    }
    Ok(b)
}
pub fn request_options(mut b: RequestBuilder, d: &Bound<'_, PyDict>) -> PyResult<RequestBuilder> {
    for (k, v) in d.iter() {
        match k.extract::<String>()?.as_str() {
            "default_headers" => b = b.default_headers(v.extract()?),
            "timeout" => b = b.timeout(duration(&v)?),
            "read_timeout" => b = b.read_timeout(duration(&v)?),
            "version" => {
                b = b.version(match v.extract::<String>()?.as_str() {
                    "HTTP/1.0" | "1.0" => wreq::Version::HTTP_10,
                    "HTTP/1.1" | "1.1" => wreq::Version::HTTP_11,
                    "HTTP/2" | "2" => wreq::Version::HTTP_2,
                    _ => return Err(value_error("invalid HTTP version")),
                })
            }
            "emulation" => b = b.emulation(emulation(&v)?),
            "orig_headers" => b = b.orig_headers(orig_headers(&v)?),
            "local_address" => {
                b = b.local_address(
                    v.extract::<Option<String>>()?
                        .map(|a| a.parse::<IpAddr>().map_err(value_error))
                        .transpose()?,
                )
            }
            "local_addresses" => {
                let (ipv4, ipv6) = v.extract::<(Option<String>, Option<String>)>()?;
                b = b.local_addresses(
                    ipv4.map(|a| a.parse::<std::net::Ipv4Addr>().map_err(value_error))
                        .transpose()?,
                    ipv6.map(|a| a.parse::<std::net::Ipv6Addr>().map_err(value_error))
                        .transpose()?,
                );
            }
            "interface" => b = b.interface(v.extract::<String>()?),
            "proxy" => b = b.proxy(proxy(&v)?),
            #[cfg(unix)]
            "uds" => b = b.proxy(wreq::Proxy::unix(v.extract::<String>()?).map_err(value_error)?),
            "group" => {
                b = b.group(if let Ok(name) = v.extract::<String>() {
                    wreq::Group::new(name)
                } else {
                    wreq::Group::new(v.extract::<u64>()?)
                });
            }
            _ => return Err(value_error(format!("unknown request option: {k}"))),
        }
    }
    Ok(b)
}
fn profile(v: &Bound<'_, PyAny>) -> PyResult<wreq_util::Profile> {
    match v.extract::<String>()?.as_str() {
        "Chrome100" | "chrome_100" => Ok(wreq_util::Emulation::Chrome100),
        "Chrome101" | "chrome_101" => Ok(wreq_util::Emulation::Chrome101),
        "Chrome104" | "chrome_104" => Ok(wreq_util::Emulation::Chrome104),
        "Chrome105" | "chrome_105" => Ok(wreq_util::Emulation::Chrome105),
        "Chrome106" | "chrome_106" => Ok(wreq_util::Emulation::Chrome106),
        "Chrome107" | "chrome_107" => Ok(wreq_util::Emulation::Chrome107),
        "Chrome108" | "chrome_108" => Ok(wreq_util::Emulation::Chrome108),
        "Chrome109" | "chrome_109" => Ok(wreq_util::Emulation::Chrome109),
        "Chrome110" | "chrome_110" => Ok(wreq_util::Emulation::Chrome110),
        "Chrome114" | "chrome_114" => Ok(wreq_util::Emulation::Chrome114),
        "Chrome116" | "chrome_116" => Ok(wreq_util::Emulation::Chrome116),
        "Chrome117" | "chrome_117" => Ok(wreq_util::Emulation::Chrome117),
        "Chrome118" | "chrome_118" => Ok(wreq_util::Emulation::Chrome118),
        "Chrome119" | "chrome_119" => Ok(wreq_util::Emulation::Chrome119),
        "Chrome120" | "chrome_120" => Ok(wreq_util::Emulation::Chrome120),
        "Chrome123" | "chrome_123" => Ok(wreq_util::Emulation::Chrome123),
        "Chrome124" | "chrome_124" => Ok(wreq_util::Emulation::Chrome124),
        "Chrome126" | "chrome_126" => Ok(wreq_util::Emulation::Chrome126),
        "Chrome127" | "chrome_127" => Ok(wreq_util::Emulation::Chrome127),
        "Chrome128" | "chrome_128" => Ok(wreq_util::Emulation::Chrome128),
        "Chrome129" | "chrome_129" => Ok(wreq_util::Emulation::Chrome129),
        "Chrome130" | "chrome_130" => Ok(wreq_util::Emulation::Chrome130),
        "Chrome131" | "chrome_131" => Ok(wreq_util::Emulation::Chrome131),
        "Chrome132" | "chrome_132" => Ok(wreq_util::Emulation::Chrome132),
        "Chrome133" | "chrome_133" => Ok(wreq_util::Emulation::Chrome133),
        "Chrome134" | "chrome_134" => Ok(wreq_util::Emulation::Chrome134),
        "Chrome135" | "chrome_135" => Ok(wreq_util::Emulation::Chrome135),
        "Chrome136" | "chrome_136" => Ok(wreq_util::Emulation::Chrome136),
        "Chrome137" | "chrome_137" => Ok(wreq_util::Emulation::Chrome137),
        "Chrome138" | "chrome_138" => Ok(wreq_util::Emulation::Chrome138),
        "Chrome139" | "chrome_139" => Ok(wreq_util::Emulation::Chrome139),
        "Chrome140" | "chrome_140" => Ok(wreq_util::Emulation::Chrome140),
        "Chrome141" | "chrome_141" => Ok(wreq_util::Emulation::Chrome141),
        "Chrome142" | "chrome_142" => Ok(wreq_util::Emulation::Chrome142),
        "Chrome143" | "chrome_143" => Ok(wreq_util::Emulation::Chrome143),
        "Chrome144" | "chrome_144" => Ok(wreq_util::Emulation::Chrome144),
        "Chrome145" | "chrome_145" => Ok(wreq_util::Emulation::Chrome145),
        "Chrome146" | "chrome_146" => Ok(wreq_util::Emulation::Chrome146),
        "Chrome147" | "chrome_147" => Ok(wreq_util::Emulation::Chrome147),
        "Chrome148" | "chrome_148" => Ok(wreq_util::Emulation::Chrome148),
        "Chrome149" | "chrome_149" => Ok(wreq_util::Emulation::Chrome149),
        "Edge101" | "edge_101" => Ok(wreq_util::Emulation::Edge101),
        "Edge122" | "edge_122" => Ok(wreq_util::Emulation::Edge122),
        "Edge127" | "edge_127" => Ok(wreq_util::Emulation::Edge127),
        "Edge131" | "edge_131" => Ok(wreq_util::Emulation::Edge131),
        "Edge134" | "edge_134" => Ok(wreq_util::Emulation::Edge134),
        "Edge135" | "edge_135" => Ok(wreq_util::Emulation::Edge135),
        "Edge136" | "edge_136" => Ok(wreq_util::Emulation::Edge136),
        "Edge137" | "edge_137" => Ok(wreq_util::Emulation::Edge137),
        "Edge138" | "edge_138" => Ok(wreq_util::Emulation::Edge138),
        "Edge139" | "edge_139" => Ok(wreq_util::Emulation::Edge139),
        "Edge140" | "edge_140" => Ok(wreq_util::Emulation::Edge140),
        "Edge141" | "edge_141" => Ok(wreq_util::Emulation::Edge141),
        "Edge142" | "edge_142" => Ok(wreq_util::Emulation::Edge142),
        "Edge143" | "edge_143" => Ok(wreq_util::Emulation::Edge143),
        "Edge144" | "edge_144" => Ok(wreq_util::Emulation::Edge144),
        "Edge145" | "edge_145" => Ok(wreq_util::Emulation::Edge145),
        "Edge146" | "edge_146" => Ok(wreq_util::Emulation::Edge146),
        "Edge147" | "edge_147" => Ok(wreq_util::Emulation::Edge147),
        "Edge148" | "edge_148" => Ok(wreq_util::Emulation::Edge148),
        "Opera116" | "opera_116" => Ok(wreq_util::Emulation::Opera116),
        "Opera117" | "opera_117" => Ok(wreq_util::Emulation::Opera117),
        "Opera118" | "opera_118" => Ok(wreq_util::Emulation::Opera118),
        "Opera119" | "opera_119" => Ok(wreq_util::Emulation::Opera119),
        "Opera120" | "opera_120" => Ok(wreq_util::Emulation::Opera120),
        "Opera121" | "opera_121" => Ok(wreq_util::Emulation::Opera121),
        "Opera122" | "opera_122" => Ok(wreq_util::Emulation::Opera122),
        "Opera123" | "opera_123" => Ok(wreq_util::Emulation::Opera123),
        "Opera124" | "opera_124" => Ok(wreq_util::Emulation::Opera124),
        "Opera125" | "opera_125" => Ok(wreq_util::Emulation::Opera125),
        "Opera126" | "opera_126" => Ok(wreq_util::Emulation::Opera126),
        "Opera127" | "opera_127" => Ok(wreq_util::Emulation::Opera127),
        "Opera128" | "opera_128" => Ok(wreq_util::Emulation::Opera128),
        "Opera129" | "opera_129" => Ok(wreq_util::Emulation::Opera129),
        "Opera130" | "opera_130" => Ok(wreq_util::Emulation::Opera130),
        "Opera131" | "opera_131" => Ok(wreq_util::Emulation::Opera131),
        "Firefox109" | "firefox_109" => Ok(wreq_util::Emulation::Firefox109),
        "Firefox117" | "firefox_117" => Ok(wreq_util::Emulation::Firefox117),
        "Firefox128" | "firefox_128" => Ok(wreq_util::Emulation::Firefox128),
        "Firefox133" | "firefox_133" => Ok(wreq_util::Emulation::Firefox133),
        "Firefox135" | "firefox_135" => Ok(wreq_util::Emulation::Firefox135),
        "FirefoxPrivate135" | "firefox_private_135" => Ok(wreq_util::Emulation::FirefoxPrivate135),
        "FirefoxAndroid135" | "firefox_android_135" => Ok(wreq_util::Emulation::FirefoxAndroid135),
        "Firefox136" | "firefox_136" => Ok(wreq_util::Emulation::Firefox136),
        "FirefoxPrivate136" | "firefox_private_136" => Ok(wreq_util::Emulation::FirefoxPrivate136),
        "Firefox139" | "firefox_139" => Ok(wreq_util::Emulation::Firefox139),
        "Firefox142" | "firefox_142" => Ok(wreq_util::Emulation::Firefox142),
        "Firefox143" | "firefox_143" => Ok(wreq_util::Emulation::Firefox143),
        "Firefox144" | "firefox_144" => Ok(wreq_util::Emulation::Firefox144),
        "Firefox145" | "firefox_145" => Ok(wreq_util::Emulation::Firefox145),
        "Firefox146" | "firefox_146" => Ok(wreq_util::Emulation::Firefox146),
        "Firefox147" | "firefox_147" => Ok(wreq_util::Emulation::Firefox147),
        "Firefox148" | "firefox_148" => Ok(wreq_util::Emulation::Firefox148),
        "Firefox149" | "firefox_149" => Ok(wreq_util::Emulation::Firefox149),
        "Firefox150" | "firefox_150" => Ok(wreq_util::Emulation::Firefox150),
        "Firefox151" | "firefox_151" => Ok(wreq_util::Emulation::Firefox151),
        "SafariIos17_2" | "safari_ios_17.2" => Ok(wreq_util::Emulation::SafariIos17_2),
        "SafariIos17_4_1" | "safari_ios_17.4.1" => Ok(wreq_util::Emulation::SafariIos17_4_1),
        "SafariIos16_5" | "safari_ios_16.5" => Ok(wreq_util::Emulation::SafariIos16_5),
        "Safari15_3" | "safari_15.3" => Ok(wreq_util::Emulation::Safari15_3),
        "Safari15_5" | "safari_15.5" => Ok(wreq_util::Emulation::Safari15_5),
        "Safari15_6_1" | "safari_15.6.1" => Ok(wreq_util::Emulation::Safari15_6_1),
        "Safari16" | "safari_16" => Ok(wreq_util::Emulation::Safari16),
        "Safari16_5" | "safari_16.5" => Ok(wreq_util::Emulation::Safari16_5),
        "Safari17_0" | "safari_17.0" => Ok(wreq_util::Emulation::Safari17_0),
        "Safari17_2_1" | "safari_17.2.1" => Ok(wreq_util::Emulation::Safari17_2_1),
        "Safari17_4_1" | "safari_17.4.1" => Ok(wreq_util::Emulation::Safari17_4_1),
        "Safari17_5" | "safari_17.5" => Ok(wreq_util::Emulation::Safari17_5),
        "Safari17_6" | "safari_17.6" => Ok(wreq_util::Emulation::Safari17_6),
        "Safari18" | "safari_18" => Ok(wreq_util::Emulation::Safari18),
        "SafariIPad18" | "safari_ipad_18" => Ok(wreq_util::Emulation::SafariIPad18),
        "Safari18_2" | "safari_18.2" => Ok(wreq_util::Emulation::Safari18_2),
        "SafariIos18_1_1" | "safari_ios_18.1.1" => Ok(wreq_util::Emulation::SafariIos18_1_1),
        "Safari18_3" | "safari_18.3" => Ok(wreq_util::Emulation::Safari18_3),
        "Safari18_3_1" | "safari_18.3.1" => Ok(wreq_util::Emulation::Safari18_3_1),
        "Safari18_5" | "safari_18.5" => Ok(wreq_util::Emulation::Safari18_5),
        "Safari26" | "safari_26" => Ok(wreq_util::Emulation::Safari26),
        "Safari26_1" | "safari_26.1" => Ok(wreq_util::Emulation::Safari26_1),
        "Safari26_2" | "safari_26.2" => Ok(wreq_util::Emulation::Safari26_2),
        "Safari26_3" | "safari_26.3" => Ok(wreq_util::Emulation::Safari26_3),
        "Safari26_4" | "safari_26.4" => Ok(wreq_util::Emulation::Safari26_4),
        "SafariIPad26" | "safari_ipad_26" => Ok(wreq_util::Emulation::SafariIPad26),
        "SafariIpad26_2" | "safari_ipad_26.2" => Ok(wreq_util::Emulation::SafariIpad26_2),
        "SafariIos26" | "safari_ios_26" => Ok(wreq_util::Emulation::SafariIos26),
        "SafariIos26_2" | "safari_ios_26.2" => Ok(wreq_util::Emulation::SafariIos26_2),
        "OkHttp3_9" | "okhttp_3.9" => Ok(wreq_util::Emulation::OkHttp3_9),
        "OkHttp3_11" | "okhttp_3.11" => Ok(wreq_util::Emulation::OkHttp3_11),
        "OkHttp3_13" | "okhttp_3.13" => Ok(wreq_util::Emulation::OkHttp3_13),
        "OkHttp3_14" | "okhttp_3.14" => Ok(wreq_util::Emulation::OkHttp3_14),
        "OkHttp4_9" | "okhttp_4.9" => Ok(wreq_util::Emulation::OkHttp4_9),
        "OkHttp4_10" | "okhttp_4.10" => Ok(wreq_util::Emulation::OkHttp4_10),
        "OkHttp4_12" | "okhttp_4.12" => Ok(wreq_util::Emulation::OkHttp4_12),
        "OkHttp5" | "okhttp_5" => Ok(wreq_util::Emulation::OkHttp5),
        _ => Err(value_error("unknown emulation profile")),
    }
}

fn dependency((id, weight, exclusive): (u32, u8, bool)) -> PyResult<wreq::http2::StreamDependency> {
    if id > 0x7fff_ffff {
        return Err(value_error("invalid stream dependency id"));
    }
    Ok(wreq::http2::StreamDependency::new(
        id.into(),
        weight,
        exclusive,
    ))
}

pub fn emulation(v: &Bound<'_, PyAny>) -> PyResult<wreq::Emulation> {
    use wreq::IntoEmulation;
    if let Ok(d) = v.cast::<PyDict>() {
        let mut e = if let Some(p) = d.get_item("profile")? {
            let platform = match d.get_item("platform")? {
                Some(value) => match value.extract::<String>()?.to_lowercase().as_str() {
                    "windows" => wreq_util::Platform::Windows,
                    "macos" => wreq_util::Platform::MacOS,
                    "linux" => wreq_util::Platform::Linux,
                    "android" => wreq_util::Platform::Android,
                    "ios" => wreq_util::Platform::IOS,
                    _ => return Err(value_error("unknown emulation platform")),
                },
                None => wreq_util::Platform::default(),
            };
            let http2 = d
                .get_item("http2")?
                .map(|v| v.extract::<bool>())
                .transpose()?
                .unwrap_or(true);
            let headers = d
                .get_item("headers")?
                .and_then(|v| v.extract::<bool>().ok())
                .unwrap_or(true);
            wreq_util::Emulation::builder()
                .profile(profile(&p)?)
                .platform(platform)
                .http2(http2)
                .headers(headers)
                .build()
                .into_emulation()
        } else {
            if d.contains("platform")?
                || d.contains("http2")?
                || d.get_item("headers")?
                    .is_some_and(|v| v.extract::<bool>().is_ok())
            {
                return Err(value_error(
                    "platform, http2, and boolean headers require an emulation profile",
                ));
            }
            wreq::Emulation::builder().build(Default::default())
        };
        for (k, v) in d.iter() {
            match k.extract::<String>()?.as_str() {
                "profile" | "platform" | "http2" => {}
                "tls_options" => e.tls_options = Some(tls(&v)?),
                "http1_options" => e.http1_options = Some(http1(&v)?),
                "http2_options" => e.http2_options = Some(http2(&v)?),
                "orig_headers" => e.orig_headers = orig_headers(&v)?,
                "headers" => {
                    if v.extract::<bool>().is_ok() {
                        continue;
                    }
                    for (name, value) in v.extract::<Vec<(String, String)>>()? {
                        e.headers.append(
                            wreq::header::HeaderName::from_bytes(name.as_bytes())
                                .map_err(value_error)?,
                            wreq::header::HeaderValue::from_str(&value).map_err(value_error)?,
                        );
                    }
                }
                _ => return Err(value_error(format!("unknown emulation option: {k}"))),
            }
        }
        Ok(e)
    } else {
        Ok(profile(v)?.into_emulation())
    }
}

fn proxy(value: &Bound<'_, PyAny>) -> PyResult<wreq::Proxy> {
    if let Ok(url) = value.extract::<String>() {
        return wreq::Proxy::all(url).map_err(value_error);
    }
    let d = value.cast::<PyDict>()?;
    let url = d
        .get_item("url")?
        .ok_or_else(|| value_error("proxy requires url"))?
        .extract::<String>()?;
    let scheme = d
        .get_item("scheme")?
        .map(|v| v.extract::<String>())
        .transpose()?
        .unwrap_or_else(|| "all".into());
    let mut proxy = match scheme.as_str() {
        "all" => wreq::Proxy::all(url),
        "http" => wreq::Proxy::http(url),
        "https" => wreq::Proxy::https(url),
        #[cfg(unix)]
        "unix" => wreq::Proxy::unix(url),
        _ => {
            return Err(value_error(
                "proxy scheme must be all, http, https, or unix",
            ));
        }
    }
    .map_err(value_error)?;
    for (key, v) in d.iter() {
        match key.extract::<String>()?.as_str() {
            "url" | "scheme" => {}
            "basic_auth" => {
                let (user, password) = v.extract::<(String, String)>()?;
                proxy = proxy.basic_auth(&user, &password);
            }
            "custom_http_auth" => {
                proxy = proxy.custom_http_auth(
                    wreq::header::HeaderValue::from_bytes(&header_bytes(&v)?)
                        .map_err(value_error)?,
                )
            }
            "custom_http_headers" => {
                let mut headers = wreq::header::HeaderMap::new();
                for item in v.try_iter()? {
                    let item = item?;
                    let name = header_bytes(&item.get_item(0)?)?;
                    let value = header_bytes(&item.get_item(1)?)?;
                    headers.append(
                        wreq::header::HeaderName::from_bytes(&name).map_err(value_error)?,
                        wreq::header::HeaderValue::from_bytes(&value).map_err(value_error)?,
                    );
                }
                proxy = proxy.custom_http_headers(headers);
            }
            "no_proxy" => {
                proxy = proxy.no_proxy(
                    v.extract::<Option<String>>()?
                        .and_then(|s| wreq::NoProxy::from_string(&s)),
                )
            }
            _ => return Err(value_error(format!("unknown proxy option: {key}"))),
        }
    }
    Ok(proxy)
}
fn header_bytes(value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    if let Ok(s) = value.extract::<String>() {
        Ok(s.into_bytes())
    } else {
        value.extract()
    }
}
