use pyo3::prelude::*;
use tokio::sync::watch;

/// Cross-thread cancellation. It never needs the response/client mutex or the GIL
/// to wake a pending Rust future.
#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct NativeCancellation {
    signal: watch::Sender<bool>,
}

#[pymethods]
impl NativeCancellation {
    #[new]
    pub fn new() -> Self {
        let (signal, _) = watch::channel(false);
        Self { signal }
    }
    pub fn cancel(&self) {
        self.signal.send_replace(true);
    }
}

impl NativeCancellation {
    pub async fn cancelled(&self) {
        let mut receiver = self.signal.subscribe();
        while !*receiver.borrow_and_update() {
            if receiver.changed().await.is_err() {
                break;
            }
        }
    }
}
