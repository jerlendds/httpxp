use futures_util::{Stream, StreamExt};
use pyo3::{
    exceptions::{PyRuntimeError, PyValueError},
    prelude::*,
    types::{PyBytes, PyDict},
};
use std::{
    pin::Pin,
    sync::{Arc, Mutex, OnceLock},
    time::Duration,
};
use wreq::{
    Method,
    header::{HeaderName, HeaderValue, OrigHeaderMap},
};
mod cancel;
mod dns;
use cancel::NativeCancellation;
mod options;
mod upload;
mod websocket;

fn runtime() -> &'static tokio::runtime::Runtime {
    static RT: OnceLock<tokio::runtime::Runtime> = OnceLock::new();
    RT.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("create wreq runtime")
    })
}
fn value_error(e: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(e.to_string())
}
fn error(e: wreq::Error) -> PyErr {
    // Preserve exceptions raised by Python callbacks through native wrappers.
    let mut source: Option<&(dyn std::error::Error + 'static)> = Some(&e);
    while let Some(cause) = source {
        if let Some(exception) = cause.downcast_ref::<PyErr>() {
            return Python::attach(|py| exception.clone_ref(py));
        }
        source = cause.source();
    }
    let kind = if e.is_timeout() {
        if e.is_connect() {
            "ConnectTimeout"
        } else {
            "ReadTimeout"
        }
    } else if e.is_proxy_connect() {
        "ProxyError"
    } else if e.is_connect() {
        "ConnectError"
    } else if e.is_body() || e.is_decode() {
        "ReadError"
    } else if e.is_builder() {
        "LocalProtocolError"
    } else {
        "RemoteProtocolError"
    };
    named_error(kind, e.to_string())
}
fn named_error(kind: &str, message: String) -> PyErr {
    Python::attach(|py| {
        match py
            .import("httpxp")
            .and_then(|m| m.getattr(kind))
            .and_then(|t| t.call1((message,)))
        {
            Ok(exc) => PyErr::from_value(exc),
            Err(exc) => exc,
        }
    })
}
fn http_version(version: wreq::Version) -> String {
    if version == wreq::Version::HTTP_2 {
        "HTTP/2".into()
    } else {
        format!("{version:?}")
    }
}
fn duration(v: &Bound<'_, PyAny>) -> PyResult<Duration> {
    Duration::try_from_secs_f64(v.extract()?).map_err(value_error)
}

type BodyStream = Pin<Box<dyn Stream<Item = wreq::Result<bytes::Bytes>> + Send>>;
#[pyclass]
struct NativeResponse {
    #[pyo3(get)]
    status: u16,
    #[pyo3(get)]
    version: String,
    #[pyo3(get)]
    headers: Vec<(Vec<u8>, Vec<u8>)>,
    #[pyo3(get)]
    peer_certificate: Option<Vec<u8>>,
    stream: Mutex<Option<BodyStream>>,
    cancellation: NativeCancellation,
    permit: Mutex<Option<tokio::sync::OwnedSemaphorePermit>>,
}
#[pymethods]
impl NativeResponse {
    fn read_chunk<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyBytes>>> {
        let result = py.detach(|| {
            let mut guard = self
                .stream
                .lock()
                .map_err(|_| PyRuntimeError::new_err("response lock poisoned"))?;
            let Some(stream) = guard.as_mut() else {
                return Ok(None);
            };
            let next = runtime().block_on(async {
                tokio::select! {
                    biased;
                    _ = self.cancellation.cancelled() => Err(PyRuntimeError::new_err("request cancelled")),
                    chunk = stream.next() => Ok(chunk),
                }
            });
            let next = match next {
                Ok(value) => value,
                Err(e) => { *guard = None; self.release_permit(); return Err(e); }
            };
            match next {
                Some(Ok(chunk)) => Ok(Some(chunk)),
                Some(Err(e)) => {
                    *guard = None;
                    self.release_permit();
                    Err(error(e))
                }
                None => {
                    *guard = None;
                    self.release_permit();
                    Ok(None)
                }
            }
        })?;
        Ok(result.map(|b| PyBytes::new(py, &b)))
    }
    fn cancel(&self) {
        self.cancellation.cancel();
    }
    fn close(&self, py: Python<'_>) {
        self.cancellation.cancel();
        py.detach(|| {
            if let Ok(mut s) = self.stream.lock() {
                *s = None;
                self.release_permit();
            }
        });
    }
}
impl NativeResponse {
    fn release_permit(&self) {
        if let Ok(mut p) = self.permit.lock() {
            *p = None;
        }
    }
}
#[pyclass]
struct NativeClient {
    client: Mutex<Option<wreq::Client>>,
    semaphore: Option<Arc<tokio::sync::Semaphore>>,
    configured_header_order: bool,
}
#[pymethods]
impl NativeClient {
    #[new]
    fn new(py: Python<'_>, options: &Bound<'_, PyDict>) -> PyResult<Self> {
        let _enter = runtime().enter();
        let builder = wreq::Client::builder()
            .no_proxy()
            .redirect(wreq::redirect::Policy::none())
            .no_gzip()
            .no_brotli()
            .no_deflate()
            .no_zstd();
        let opts = options.copy()?;
        let max = opts
            .get_item("_max_connections")?
            .map(|v| v.extract::<Option<usize>>())
            .transpose()?
            .flatten();
        if opts.contains("_max_connections")? {
            opts.del_item("_max_connections")?;
        }
        let builder = options::client_options(builder, &opts)?;
        let client = py.detach(|| builder.build()).map_err(error)?;
        Ok(Self {
            configured_header_order: opts.contains("emulation")?
                || opts.contains("orig_headers")?,
            client: Mutex::new(Some(client)),
            semaphore: max.map(|n| Arc::new(tokio::sync::Semaphore::new(n))),
        })
    }
    fn send(
        &self,
        py: Python<'_>,
        method: &str,
        url: &str,
        headers: Vec<(Vec<u8>, Vec<u8>)>,
        body: Py<PyAny>,
        options: &Bound<'_, PyDict>,
    ) -> PyResult<NativeResponse> {
        let client = self
            .client
            .lock()
            .map_err(|_| PyRuntimeError::new_err("client lock poisoned"))?
            .clone()
            .ok_or_else(|| PyRuntimeError::new_err("transport is closed"))?;
        let opts = options.copy()?;
        let cancellation = opts
            .get_item("_cancel")?
            .map(|v| v.extract::<NativeCancellation>().map_err(PyErr::from))
            .transpose()?
            .unwrap_or_else(NativeCancellation::new);
        if opts.contains("_cancel")? {
            opts.del_item("_cancel")?;
        }
        let pool_timeout = opts
            .get_item("_pool_timeout")?
            .filter(|v| !v.is_none())
            .map(|v| duration(&v))
            .transpose()?;
        if opts.contains("_pool_timeout")? {
            opts.del_item("_pool_timeout")?;
        }
        let permit = if let Some(semaphore) = &self.semaphore {
            Some(py.detach(|| runtime().block_on(async {
                let acquire = semaphore.clone().acquire_owned();
                let waiting = async {
                    if let Some(t) = pool_timeout {
                        tokio::time::timeout(t, acquire).await.map_err(|_| named_error("PoolTimeout", "Timed out waiting for an available connection".into()))
                    } else { Ok(acquire.await) }
                };
                let result = tokio::select! {
                    biased;
                    _ = cancellation.cancelled() => return Err(PyRuntimeError::new_err("request cancelled")),
                    result = waiting => result?,
                };
                result.map_err(|_| PyRuntimeError::new_err("transport is closed"))
            }))?)
        } else {
            None
        };
        let write_timeout = opts
            .get_item("_write_timeout")?
            .filter(|v| !v.is_none())
            .map(|v| duration(&v))
            .transpose()?;
        if opts.contains("_write_timeout")? {
            opts.del_item("_write_timeout")?;
        }
        let empty_body = body.is_none(py);
        let buffered = body
            .bind(py)
            .cast::<PyBytes>()
            .ok()
            .map(|b| bytes::Bytes::copy_from_slice(b.as_bytes()));
        let buffered_body = buffered.is_some();
        let upload = upload::Upload::new(body, buffered);
        let watchdog = upload.watchdog(write_timeout);
        let upload_error = upload.error;
        let upload_stop = upload.stop;
        let mut req = client
            .request(
                Method::from_bytes(method.as_bytes()).map_err(value_error)?,
                url,
            )
            .body(if empty_body {
                wreq::Body::from(bytes::Bytes::new())
            } else {
                upload.body
            });
        req = options::request_options(req, &opts)?;
        let mut orig = OrigHeaderMap::new();
        for (name, value) in headers {
            orig.insert(String::from_utf8(name.clone()).map_err(value_error)?);
            req = req.header(
                HeaderName::from_bytes(&name).map_err(value_error)?,
                HeaderValue::from_bytes(&value).map_err(value_error)?,
            );
        }
        if !self.configured_header_order
            && !opts.contains("emulation")?
            && !opts.contains("orig_headers")?
        {
            req = req.orig_headers(orig);
        }
        let result = py.detach(|| runtime().block_on(async {
            tokio::select! {
                biased;
                _ = cancellation.cancelled() => Err(PyRuntimeError::new_err("request cancelled")),
                result = req.send() => result.map_err(error),
                _ = watchdog => Err(named_error("WriteTimeout", "Timed out sending the request body".into())),
            }
        }));
        if result.is_ok() && !buffered_body {
            upload_stop.store(true, std::sync::atomic::Ordering::Release);
        }
        if let Some(e) = upload_error
            .lock()
            .map_err(|_| PyRuntimeError::new_err("upload lock poisoned"))?
            .take()
        {
            return Err(e);
        }
        let response = result?;
        let peer_certificate = response
            .extensions()
            .get::<wreq::tls::TlsInfo>()
            .and_then(|v| v.peer_certificate().map(Vec::from));
        Ok(NativeResponse {
            status: response.status().as_u16(),
            version: http_version(response.version()),
            headers: response
                .headers()
                .iter()
                .map(|(k, v)| (k.as_str().as_bytes().to_vec(), v.as_bytes().to_vec()))
                .collect(),
            peer_certificate,
            cancellation,
            stream: Mutex::new(Some(Box::pin(response.bytes_stream()))),
            permit: Mutex::new(permit),
        })
    }
    fn websocket(
        &self,
        py: Python<'_>,
        url: &str,
        headers: Vec<(Vec<u8>, Vec<u8>)>,
        options: &Bound<'_, PyDict>,
    ) -> PyResult<websocket::NativeWebSocket> {
        websocket::connect(self, py, url, headers, options)
    }
    fn close(&self) {
        if let Some(s) = &self.semaphore {
            s.close();
        }
        if let Ok(mut c) = self.client.lock() {
            *c = None;
        }
    }
}
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BACKEND", "wreq")?;
    m.add("PRIVATE_VERSION", "0.16.1")?;
    m.add_function(wrap_pyfunction!(emulation_headers, m)?)?;
    m.add_class::<NativeClient>()?;
    m.add_class::<NativeCancellation>()?;
    m.add_class::<websocket::NativeWebSocket>()?;
    m.add_class::<NativeResponse>()?;
    Ok(())
}

#[pyfunction]
fn emulation_headers(value: &Bound<'_, PyAny>) -> PyResult<Vec<(Vec<u8>, Vec<u8>)>> {
    Ok(options::emulation(value)?
        .headers
        .iter()
        .map(|(k, v)| (k.as_str().as_bytes().to_vec(), v.as_bytes().to_vec()))
        .collect())
}
