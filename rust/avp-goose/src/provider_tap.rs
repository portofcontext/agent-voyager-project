//! A `Provider` decorator that taps per-inference usage off the stream.
//!
//! Goose surfaces token usage (including the cache read/write split) on the
//! provider's stream as `ProviderUsage`, but that signal never reaches the
//! `AgentEvent` level. Since `Agent::update_provider` takes `Arc<dyn Provider>`,
//! we wrap the real provider, delegate everything, and tee each chunk's usage
//! into a shared buffer the runner drains per turn. This gives exact per-turn
//! usage and cache split without modifying Goose.
//!
//! Only hot-path methods are overridden (the rest use trait defaults):
//! `stream` (tapped), plus `get_name` / `get_model_config` /
//! `supports_cache_control` / `manages_own_context` delegated so the wrapper is
//! behaviorally transparent (notably `supports_cache_control` defaults to
//! `false`, which would silently disable prompt caching).

use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use futures::StreamExt;
use goose::conversation::message::Message;
use goose::model::ModelConfig;
use goose::providers::base::{MessageStream, Provider, ProviderUsage};
use goose::providers::errors::ProviderError;
use rmcp::model::Tool;

/// Handle the runner holds to drain captured usage as turns complete.
#[derive(Clone, Default)]
pub struct UsageTap {
    usages: Arc<Mutex<Vec<ProviderUsage>>>,
}

impl UsageTap {
    /// Usages captured since the last drain (one entry per completed inference).
    pub fn drain_new(&self, consumed: &mut usize) -> Vec<ProviderUsage> {
        let all = self.usages.lock().unwrap();
        let new = all[(*consumed).min(all.len())..].to_vec();
        *consumed = all.len();
        new
    }
}

struct TappedProvider {
    inner: Arc<dyn Provider>,
    usages: Arc<Mutex<Vec<ProviderUsage>>>,
}

/// Wrap `inner` so its stream usage is captured; returns the wrapped provider
/// (to hand to `update_provider`) and the tap the runner reads.
pub fn tap(inner: Arc<dyn Provider>) -> (Arc<dyn Provider>, UsageTap) {
    let usages = Arc::new(Mutex::new(Vec::new()));
    let provider: Arc<dyn Provider> = Arc::new(TappedProvider {
        inner,
        usages: usages.clone(),
    });
    (provider, UsageTap { usages })
}

#[async_trait]
impl Provider for TappedProvider {
    fn get_name(&self) -> &str {
        self.inner.get_name()
    }

    fn get_model_config(&self) -> ModelConfig {
        self.inner.get_model_config()
    }

    async fn supports_cache_control(&self) -> bool {
        self.inner.supports_cache_control().await
    }

    fn manages_own_context(&self) -> bool {
        self.inner.manages_own_context()
    }

    async fn stream(
        &self,
        model_config: &ModelConfig,
        session_id: &str,
        system: &str,
        messages: &[Message],
        tools: &[Tool],
    ) -> Result<MessageStream, ProviderError> {
        let inner = self
            .inner
            .stream(model_config, session_id, system, messages, tools)
            .await?;
        let usages = self.usages.clone();
        Ok(Box::pin(inner.inspect(move |item| {
            if let Ok((_, Some(usage))) = item {
                usages.lock().unwrap().push(usage.clone());
            }
        })))
    }
}
