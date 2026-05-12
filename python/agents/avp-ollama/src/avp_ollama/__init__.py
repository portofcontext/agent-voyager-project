"""AVP runner backed by a local Ollama model.

See the package README for scope. The public surface:

  - `OllamaTranslator` — drives one run end-to-end against the supervisor.
  - `SupervisorEventClient` — thin HTTP client for the supervisor's event API.
  - `runner.app` — FastAPI dispatcher used by `LocalOllamaBackend`.
"""

from .supervisor_client import SupervisorEventClient
from .translator import OllamaTranslator, RescueFailAt

__all__ = ["OllamaTranslator", "RescueFailAt", "SupervisorEventClient"]
