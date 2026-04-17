"""
CorpusForge boot validation script.

What it does for the operator:
  A quick, read-only sanity check of Forge's config file. It loads the YAML,
  validates every field, prints a one-screen summary of the settings that
  would be used on a real run, and exits. NO files are ingested, NO GPU is
  used, and NOTHING is written to disk.

When to run it:
  - First thing after editing config/config.yaml
  - Before scheduling a big overnight ingest, to confirm paths and toggles
  - After pulling fresh code, to confirm the config still parses cleanly

Inputs:
  --config  Path to the config YAML. Defaults to config/config.yaml.

Outputs:
  Prints a block of text to the terminal (chunk size, embed model, enrich
  status, paths, etc.). Exits 0 on success; a config error will raise.

Usage: python scripts/boot.py [--config path/to/config.yaml]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path so src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.schema import load_config


def main() -> None:
    """Load the config file, print the effective settings, and exit."""
    parser = argparse.ArgumentParser(description="CorpusForge boot validation")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config YAML file (default: config/config.yaml)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  CorpusForge — Boot Validation")
    print("=" * 50)

    config = load_config(args.config)

    print(f"  Chunk:     {config.chunk.size} chars / {config.chunk.overlap} overlap")
    print(f"  Embed:     {config.embed.model_name} ({config.embed.dim}d, {config.embed.device})")
    print(f"  Enrich:    {'ON' if config.enrich.enabled else 'OFF'} ({config.enrich.model})")
    print(f"  Extract:   {'ON' if config.extract.enabled else 'OFF (waiver pending)'}")
    print(f"  Parse:     timeout={config.parse.timeout_seconds}s, OCR={config.parse.ocr_mode}")
    if config.parse.defer_extensions:
        print(f"  Deferred:  {', '.join(config.parse.defer_extensions)}")
    else:
        print("  Deferred:  none")
    print(f"  Hardware:  GPU {config.hardware.gpu_index}, batch={config.hardware.embed_batch_size}")
    print(f"  Sources:   {config.paths.source_dirs}")
    print(f"  Output:    {config.paths.output_dir}")
    print(f"  State DB:  {config.paths.state_db}")
    print(f"  Pipeline:  reindex={config.pipeline.full_reindex}, log={config.pipeline.log_level}")
    print("=" * 50)
    print("  CorpusForge ready.")
    print("=" * 50)


if __name__ == "__main__":
    main()
