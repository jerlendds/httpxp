use crate::{
    cancel::NativeCancellation, duration, error, named_error, options, runtime, value_error,
};
use futures_util::{
    SinkExt, StreamExt,
    stream::{SplitSink, SplitStream},
};
use pyo3::{exceptions::PyRuntimeError, prelude::*, types::PyDict};
use std::time::Duration;
use tokio::sync::{Mutex, OwnedSemaphorePermit};
use wreq::{
    header::{HeaderName, HeaderValue},
    ws::{
        WebSocket, WebSocketRequestBuilder,
        message::{CloseFrame, Message},
    },
};

#[pyclass]
pub struct NativeWebSocket {
    #[pyo3(get)]
    pub status: u16,
    #[pyo3(get)]
    pub version: String,
    #[pyo3(get)]
    pub headers: Vec<(Vec<u8>, Vec<u8>)>,
    #[pyo3(get)]
    pub protocol: Option<String>,
    tx: Mutex<Option<SplitSink<WebSocket, Message>>>,
    rx: Mutex<Option<SplitStream<WebSocket>>>,
    permit: Mutex<Option<OwnedSemaphorePermit>>,
    cancellation: NativeCancellation,
}

#[pymethods]
impl NativeWebSocket {
    fn send(&self, py: Python<'_>, kind: &str, data: Vec<u8>, code: Option<u16>) -> PyResult<()> {
        let message = match kind {
            "text" => Message::text(String::from_utf8(data).map_err(value_error)?),
            "binary" => Message::binary(data),
            "ping" | "pong" if data.len() > 125 => {
                return Err(value_error("control frame payload exceeds 125 bytes"));
            }
            "ping" => Message::Ping(data.into()),
            "pong" => Message::Pong(data.into()),
            "close" => Message::Close(code.map(|code| CloseFrame {
                code: code.into(),
                reason: String::from_utf8_lossy(&data).into_owned().into(),
            })),
            _ => return Err(value_error("unknown WebSocket message type")),
        };
        py.detach(|| runtime().block_on(async {
            tokio::select! {
                biased;
                _ = self.cancellation.cancelled() => Err(PyRuntimeError::new_err("WebSocket is closed")),
                result = async {
                    let mut tx = self.tx.lock().await;
                    tx.as_mut().ok_or_else(|| PyRuntimeError::new_err("WebSocket is closed"))?.send(message).await.map_err(error)
                } => result,
            }
        }))
    }
    fn receive(&self, py: Python<'_>) -> PyResult<Option<(String, Vec<u8>, Option<u16>)>> {
        py.detach(|| runtime().block_on(async {
            let item = tokio::select! {
                biased;
                _ = self.cancellation.cancelled() => return Err(PyRuntimeError::new_err("WebSocket is closed")),
                item = async {
                    let mut rx = self.rx.lock().await;
                    match rx.as_mut() { Some(rx) => rx.next().await, None => None }
                } => item,
            };
            let Some(item) = item else { return Ok(None); };
            Ok(Some(match item.map_err(error)? {
                Message::Text(v) => ("text".into(), v.as_bytes().to_vec(), None),
                Message::Binary(v) => ("binary".into(), v.to_vec(), None),
                Message::Ping(v) => ("ping".into(), v.to_vec(), None),
                Message::Pong(v) => ("pong".into(), v.to_vec(), None),
                Message::Close(v) => match v {
                    Some(v) => ("close".into(), v.reason.as_bytes().to_vec(), Some(v.code.into())),
                    None => ("close".into(), vec![], None),
                },
            }))
        }))
    }
    fn cancel(&self) {
        self.cancellation.cancel();
    }
    fn close(&self, py: Python<'_>, code: u16, reason: String) -> PyResult<()> {
        if reason.len() > 123 {
            return Err(value_error("WebSocket close reason exceeds 123 bytes"));
        }
        self.cancellation.cancel();
        py.detach(|| {
            runtime().block_on(async {
                let mut tx = self.tx.lock().await;
                if let Some(mut sink) = tx.take() {
                    let _ = tokio::time::timeout(
                        Duration::from_secs(2),
                        sink.send(Message::Close(Some(CloseFrame {
                            code: code.into(),
                            reason: reason.into(),
                        }))),
                    )
                    .await;
                }
                *self.rx.lock().await = None;
                *self.permit.lock().await = None;
            })
        });
        Ok(())
    }
}

pub fn connect(
    client: &crate::NativeClient,
    py: Python<'_>,
    url: &str,
    headers: Vec<(Vec<u8>, Vec<u8>)>,
    config: &Bound<'_, PyDict>,
) -> PyResult<NativeWebSocket> {
    let native = client
        .client
        .lock()
        .map_err(|_| PyRuntimeError::new_err("client lock poisoned"))?
        .clone()
        .ok_or_else(|| PyRuntimeError::new_err("transport is closed"))?;
    let opts = config.copy()?;
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
    let mut request = native.get(url);
    for (name, value) in headers {
        request = request.header(
            HeaderName::from_bytes(&name).map_err(value_error)?,
            HeaderValue::from_bytes(&value).map_err(value_error)?,
        );
    }
    let ws_options = PyDict::new(py);
    for name in [
        "version",
        "protocols",
        "accept_key",
        "max_frame_size",
        "read_buffer_size",
        "write_buffer_size",
        "max_write_buffer_size",
        "max_message_size",
        "accept_unmasked_frames",
    ] {
        if let Some(v) = opts.get_item(name)? {
            ws_options.set_item(name, &v)?;
            opts.del_item(name)?;
        }
    }
    request = options::request_options(request, &opts)?;
    let read_buffer = ws_options
        .get_item("read_buffer_size")?
        .map(|v| v.extract::<usize>())
        .transpose()?
        .unwrap_or(128 * 1024);
    let write_buffer = ws_options
        .get_item("write_buffer_size")?
        .map(|v| v.extract::<usize>())
        .transpose()?
        .unwrap_or(128 * 1024);
    let max_write_buffer = ws_options
        .get_item("max_write_buffer_size")?
        .map(|v| v.extract::<usize>())
        .transpose()?
        .unwrap_or(usize::MAX);
    if read_buffer == 0 || max_write_buffer <= write_buffer {
        return Err(value_error(
            "read_buffer_size must be positive and max_write_buffer_size must exceed write_buffer_size",
        ));
    }
    let mut builder = WebSocketRequestBuilder::new(request);
    for (key, v) in ws_options.iter() {
        builder = match key.extract::<String>()?.as_str() {
            "version" => builder.version(match v.extract::<String>()?.as_str() {
                "1.1" | "HTTP/1.1" => wreq::Version::HTTP_11,
                "2" | "HTTP/2" => wreq::Version::HTTP_2,
                _ => return Err(value_error("WebSockets require HTTP/1.1 or HTTP/2")),
            }),
            "protocols" => builder.protocols(v.extract::<Vec<String>>()?),
            "accept_key" => builder.accept_key(v.extract::<String>()?),
            "max_frame_size" => builder.max_frame_size(v.extract()?),
            "read_buffer_size" => builder.read_buffer_size(v.extract()?),
            "write_buffer_size" => builder.write_buffer_size(v.extract()?),
            "max_write_buffer_size" => builder.max_write_buffer_size(v.extract()?),
            "max_message_size" => builder.max_message_size(v.extract()?),
            "accept_unmasked_frames" => builder.accept_unmasked_frames(v.extract()?),
            _ => unreachable!(),
        };
    }
    py.detach(|| runtime().block_on(async {
        let future = async {
            let permit = if let Some(s) = &client.semaphore {
                let acquire = s.clone().acquire_owned();
                let p = if let Some(t) = pool_timeout { tokio::time::timeout(t, acquire).await.map_err(|_| named_error("PoolTimeout", "Timed out waiting for a WebSocket connection slot".into()))? } else { acquire.await };
                Some(p.map_err(|_| PyRuntimeError::new_err("transport is closed"))?)
            } else { None };
            let response = builder.send().await.map_err(error)?;
            let status = response.status().as_u16();
            let version = crate::http_version(response.version());
            let headers = response.headers().iter().map(|(k,v)| (k.as_str().as_bytes().to_vec(), v.as_bytes().to_vec())).collect();
            let socket = response.into_websocket().await.map_err(error)?;
            let protocol = socket.protocol().map(|p| p.to_str().map(String::from)).transpose().map_err(value_error)?;
            let (tx, rx) = socket.split();
            Ok(NativeWebSocket {status, version, headers, protocol, tx: Mutex::new(Some(tx)), rx: Mutex::new(Some(rx)), permit: Mutex::new(permit), cancellation: cancellation.clone()})
        };
        tokio::select! { biased; _ = cancellation.cancelled() => Err(PyRuntimeError::new_err("WebSocket handshake cancelled")), result = future => result }
    }))
}
