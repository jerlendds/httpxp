//! Pull one Python upload chunk at a time; never collect a request iterator.
use bytes::Bytes;
use futures_util::stream;
use pyo3::{exceptions::PyStopIteration, prelude::*, types::PyBytes};
use std::{
    io,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};
use tokio::{sync::watch, time::Instant};

#[derive(Clone, Copy)]
enum Progress {
    Waiting,
    Writing(Instant),
    Done,
}

pub struct Upload {
    pub body: wreq::Body,
    pub error: Arc<Mutex<Option<PyErr>>>,
    progress: watch::Receiver<Progress>,
    pub stop: Arc<AtomicBool>,
}

impl Upload {
    pub fn new(iterator: Py<PyAny>, buffered: Option<Bytes>) -> Self {
        let error = Arc::new(Mutex::new(None));
        let (tx, rx) = watch::channel(Progress::Waiting);
        let stop = Arc::new(AtomicBool::new(false));
        let state = (
            if buffered.is_some() {
                None
            } else {
                Some(iterator)
            },
            buffered.unwrap_or_default(),
            tx,
            error.clone(),
            stop.clone(),
        );
        let body = stream::unfold(
            state,
            |(mut iterator, mut pending, tx, error, stop)| async move {
                if stop.load(Ordering::Acquire) {
                    tx.send_replace(Progress::Done);
                    return None;
                }
                if iterator.is_none() && pending.is_empty() {
                    tx.send_replace(Progress::Done);
                    return None;
                }
                tx.send_replace(Progress::Writing(Instant::now()));
                loop {
                    if !pending.is_empty() {
                        let chunk = pending.split_to(pending.len().min(64 * 1024));
                        return Some((
                            Ok::<_, io::Error>(chunk),
                            (iterator, pending, tx, error, stop),
                        ));
                    }
                    let current = iterator.take()?;
                    let read = tokio::task::spawn_blocking(move || {
                        let result =
                            Python::attach(|py| match current.bind(py).call_method0("__next__") {
                                Ok(value) => Ok(Some(Bytes::copy_from_slice(
                                    value.cast::<PyBytes>()?.as_bytes(),
                                ))),
                                Err(e) if e.is_instance_of::<PyStopIteration>(py) => Ok(None),
                                Err(e) => Err(e),
                            });
                        (current, result)
                    })
                    .await;
                    let (current, result) = match read {
                        Ok(v) => v,
                        Err(e) => {
                            tx.send_replace(Progress::Done);
                            return Some((
                                Err(io::Error::other(e.to_string())),
                                (None, pending, tx, error, stop),
                            ));
                        }
                    };
                    if stop.load(Ordering::Acquire) {
                        tx.send_replace(Progress::Done);
                        return None;
                    }
                    iterator = Some(current);
                    match result {
                        Ok(Some(chunk)) => pending = chunk,
                        Ok(None) => {
                            tx.send_replace(Progress::Done);
                            return None;
                        }
                        Err(e) => {
                            let message = e.to_string();
                            if let Ok(mut slot) = error.lock() {
                                *slot = Some(e);
                            }
                            tx.send_replace(Progress::Done);
                            return Some((
                                Err(io::Error::other(message)),
                                (None, pending, tx, error, stop),
                            ));
                        }
                    }
                }
            },
        );
        Self {
            body: wreq::Body::wrap_stream(body),
            error,
            progress: rx,
            stop,
        }
    }

    pub fn watchdog(&self, timeout: Option<Duration>) -> impl Future<Output = ()> + Send + 'static {
        let mut progress = self.progress.clone();
        async move {
            let Some(timeout) = timeout else {
                std::future::pending::<()>().await;
                return;
            };
            loop {
                let state = *progress.borrow_and_update();
                match state {
                    Progress::Done => std::future::pending::<()>().await,
                    Progress::Waiting => {
                        if progress.changed().await.is_err() {
                            std::future::pending::<()>().await;
                        }
                    }
                    Progress::Writing(last) => {
                        tokio::select! {
                            _ = tokio::time::sleep_until(last + timeout) => return,
                            changed = progress.changed() => {
                                if changed.is_err() { std::future::pending::<()>().await; }
                            }
                        }
                    }
                }
            }
        }
    }
}
