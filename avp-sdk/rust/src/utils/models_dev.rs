//! Shared catalog fetching and snapshot persistence for pricing and endpoints.
use std::{
    borrow::Cow,
    env, fs,
    path::{Path, PathBuf},
    time::Duration,
};

use chrono::{DateTime, Utc};
use serde::{Serialize, de::DeserializeOwned};
use serde_json::Value;

use crate::Result;

pub(super) fn source() -> String {
    "https://models.dev/api.json".into()
}

pub(super) trait Snapshot: Serialize + DeserializeOwned {
    fn fetched(&self) -> DateTime<Utc>;
}

pub(super) fn cache_path(name: &str) -> PathBuf {
    let root = env::var_os("XDG_CACHE_HOME")
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env::var_os("HOME").expect("HOME is set")).join(".cache"));
    root.join("avp").join(name)
}

pub(super) fn catalog(catalog: Option<&Value>) -> Result<Cow<'_, Value>> {
    if let Some(catalog) = catalog.filter(|c| c.as_object().is_none_or(|c| !c.is_empty())) {
        return Ok(Cow::Borrowed(catalog));
    }
    Ok(Cow::Owned(
        ureq::get(&source())
            .header("User-Agent", "avp-rust-sdk")
            .config()
            .timeout_global(Some(Duration::from_secs(30)))
            .build()
            .call()?
            .body_mut()
            .read_json::<Value>()?,
    ))
}

pub(super) fn save(snapshot: &impl Serialize, path: &Path) -> Result<PathBuf> {
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    let partial = path.with_file_name(format!(
        ".{}.partial",
        path.file_name()
            .ok_or("snapshot path has no filename")?
            .to_string_lossy()
    ));
    fs::write(
        &partial,
        format!("{}\n", serde_json::to_string_pretty(snapshot)?),
    )?;
    fs::rename(&partial, path)?;
    Ok(path.to_path_buf())
}

pub(super) fn load<S: Snapshot>(
    path: Option<&Path>,
    default_path: &Path,
    max_age: Option<Duration>,
    bundled: impl FnOnce() -> S,
    fetch: impl FnOnce() -> Result<S>,
) -> Result<S> {
    let file = path.unwrap_or(default_path);
    let mut snapshot: Option<S> = match fs::read_to_string(file) {
        Ok(text) => Some(serde_json::from_str(&text)?),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    if path.is_none() {
        let shipped = bundled();
        if snapshot
            .as_ref()
            .is_none_or(|s| shipped.fetched() > s.fetched())
        {
            snapshot = Some(shipped);
        }
    }
    if max_age.is_some_and(|age| {
        snapshot.as_ref().is_none_or(|s| {
            Utc::now()
                .signed_duration_since(s.fetched())
                .to_std()
                .is_ok_and(|elapsed| elapsed > age)
        })
    }) {
        let fresh = fetch()?;
        save(&fresh, file)?;
        return Ok(fresh);
    }
    snapshot.ok_or_else(|| {
        std::io::Error::new(std::io::ErrorKind::NotFound, file.display().to_string()).into()
    })
}
