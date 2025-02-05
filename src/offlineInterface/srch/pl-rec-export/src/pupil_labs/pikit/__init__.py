from ._version import get_versions
from .recording import Recording  # noqa

__version__ = get_versions()["version"]
del get_versions
