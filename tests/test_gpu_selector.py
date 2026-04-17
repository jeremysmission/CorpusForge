"""Tests for GPU selection logic.

Plain-English summary for operators:
On a dual-GPU workstation, Forge picks the idlest GPU so the display GPU
is not starved during a long run. This file protects that selector. If
these tests fail, Forge might land on the wrong GPU (crashing the
display, or OOM-ing the embed stage), or fail to set the GPU
environment variable at all — which would silently default every run
to GPU 0 regardless of load.
"""
import os

from src.gpu_selector import select_gpu, apply_gpu_selection


def test_select_gpu_returns_int():
    """Protects against the selector returning None or a negative index — operators need a real GPU picked."""
    idx = select_gpu()
    assert isinstance(idx, int)
    assert idx >= 0


def test_apply_gpu_selection_sets_env():
    """Protects against Forge forgetting to set CUDA_VISIBLE_DEVICES — without it, every run defaults to GPU 0."""
    idx = apply_gpu_selection()
    assert os.environ["CUDA_VISIBLE_DEVICES"] == str(idx)
