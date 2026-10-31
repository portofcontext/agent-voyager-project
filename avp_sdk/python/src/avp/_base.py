"""Settings shared by the wire models of all three specs."""

from pydantic import BaseModel, ConfigDict

AVP_VERSION = "0.1"


class WireModel(BaseModel):
    """A wire object that rejects fields its spec doesn't define."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)
