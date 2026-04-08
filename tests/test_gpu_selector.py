"""Tests for GPU selection logic."""
import os

from src.gpu_selector import select_gpu, apply_gpu_selection


def test_select_gpu_returns_int():
    idx = select_gpu()
    assert isinstance(idx, int)
    assert idx >= 0


def test_apply_gpu_selection_sets_env():
    idx = apply_gpu_selection()
    assert os.environ["CUDA_VISIBLE_DEVICES"] == str(idx)
