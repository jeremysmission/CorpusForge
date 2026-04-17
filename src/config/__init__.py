"""Configuration package for CorpusForge.

Every runtime setting Forge needs is read from ``config/config.yaml``
at startup, validated against the schema in ``schema.py``, and then
handed to the pipeline as an immutable object. The operator edits the
YAML file directly; Forge re-reads it on the next launch.
"""

from .schema import ForgeConfig, load_config

__all__ = ["ForgeConfig", "load_config"]
