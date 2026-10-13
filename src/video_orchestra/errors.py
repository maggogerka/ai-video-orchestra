class VideoOrchestraError(Exception):
    """Base error shown to the CLI user."""


class WorkflowFormatError(VideoOrchestraError):
    """The workflow is not a ComfyUI API workflow."""


class WorkflowNodeError(VideoOrchestraError):
    """A required workflow node or input cannot be resolved safely."""


class ComfyClientError(VideoOrchestraError):
    """Communication with ComfyUI failed."""
