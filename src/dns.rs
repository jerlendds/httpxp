use pyo3::prelude::*;
use std::{net::SocketAddr, sync::Arc};
use wreq::dns::{Addrs, Name, Resolve, Resolving};

/// Run Python resolvers on blocking workers so they cannot stall Tokio I/O.
pub struct PythonResolver(pub Arc<Py<PyAny>>);

impl Resolve for PythonResolver {
    fn resolve(&self, name: Name) -> Resolving {
        let callback = self.0.clone();
        Box::pin(async move {
            let addresses = tokio::task::spawn_blocking(move || {
                Python::attach(|py| -> PyResult<Vec<SocketAddr>> {
                    let result = callback.call1(py, (name.as_str(),))?;
                    result
                        .bind(py)
                        .try_iter()?
                        .map(|item| {
                            let (ip, port) = item?.extract::<(String, u16)>()?;
                            Ok(SocketAddr::new(
                                ip.parse().map_err(crate::value_error)?,
                                port,
                            ))
                        })
                        .collect()
                })
            })
            .await??;
            Ok(Box::new(addresses.into_iter()) as Addrs)
        })
    }
}
