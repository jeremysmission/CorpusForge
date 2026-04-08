"""
GPU selector — pick the least-used GPU for compute workloads.

Probes all NVIDIA GPUs via nvidia-smi and returns the index of the GPU
with the lowest memory utilization. Falls back to GPU 0 if probing fails.

Used by start_corpusforge.bat and pipeline boot to set CUDA_VISIBLE_DEVICES.
"""

from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def select_gpu() -> int:
    """
    Pick the GPU with the lowest memory usage.

    Returns the GPU index (0-based). Sets CUDA_VISIBLE_DEVICES in the
    current process environment.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("nvidia-smi failed, defaulting to GPU 0.")
            return 0

        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(",")
            if len(parts) == 2:
                idx = int(parts[0].strip())
                mem_used = int(parts[1].strip())
                gpus.append((idx, mem_used))

        if not gpus:
            return 0

        # Pick GPU with lowest memory usage
        best = min(gpus, key=lambda g: g[1])
        logger.info(
            "GPU selection: %s -- picked GPU %d (%d MiB used)",
            ", ".join(f"GPU {i}: {m} MiB" for i, m in gpus),
            best[0],
            best[1],
        )
        return best[0]

    except FileNotFoundError:
        logger.warning("nvidia-smi not found, defaulting to GPU 0.")
        return 0
    except Exception as exc:
        logger.warning("GPU probe failed: %s, defaulting to GPU 0.", exc)
        return 0


def apply_gpu_selection() -> int:
    """Select best GPU and set CUDA_VISIBLE_DEVICES in this process."""
    gpu_idx = select_gpu()
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_idx)
    logger.info("CUDA_VISIBLE_DEVICES set to %d", gpu_idx)
    return gpu_idx
