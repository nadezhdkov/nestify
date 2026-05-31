"""
nestifypy.yaml.exceptions
----------------------
YAML specific exceptions.
"""

from nestifypy.slogger import ConfigError

class YamlPathError(ConfigError):
    """Raised when a requested YAML dot-path cannot be found."""
    pass
