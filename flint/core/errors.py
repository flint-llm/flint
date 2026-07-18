"""Flint exception hierarchy.

All errors raised by flint.core modules are subclasses of FlintError.
CLI handlers catch FlintError and format it for the user; unexpected
exceptions propagate unless --debug is set.
"""


class FlintError(Exception):
    """Base exception for all Flint errors."""


class TemplateRenderError(FlintError):
    """Raised when a Jinja2 template cannot be found or fails to render."""


class K8sError(FlintError):
    """Raised when a Kubernetes API call or kubectl command fails."""


class ClusterError(FlintError):
    """Raised when cluster introspection fails (kubeconfig, connectivity)."""


class ModelNotFoundError(FlintError):
    """Raised when a model or its pod/deployment cannot be located."""


class RoutingError(FlintError):
    """Raised when traffic routing configuration is invalid or cannot be applied."""


class BuildError(FlintError):
    """Raised when an image pull or push operation fails."""


class WeightsValidationError(FlintError):
    """Raised when traffic split weights are invalid (do not sum to 100)."""


class ConfigError(FlintError):
    """Raised when flint.toml cannot be read or contains invalid values."""


class OllamaError(FlintError):
    """Raised when a local Ollama operation fails."""


class OllamaNotFoundError(OllamaError):
    """Raised when the ollama binary is not found on PATH."""


class OllamaUnhealthyError(OllamaError):
    """Raised when the Ollama server does not become healthy within the timeout."""
