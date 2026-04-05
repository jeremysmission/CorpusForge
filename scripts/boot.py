"""
CorpusForge boot validation script.

Loads config, validates all fields, prints status, exits.
Usage: python scripts/boot.py [--config path/to/config.yaml]
"""

import argparse
import sys
from pathlib import Path

# Add project root to path so src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.schema import load_config


def main() -> None:
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
