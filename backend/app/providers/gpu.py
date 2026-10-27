"""Run a model on the GPU, and fall back to the CPU when the GPU runs out of memory."""

import gc
import logging
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)


def is_out_of_memory(exc: BaseException) -> bool:
    return "out of memory" in str(exc).lower()


def free_gpu_memory() -> None:
    gc.collect()
    torch = sys.modules.get("torch")  # only if a model already imported it
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_with_cpu_fallback[T](run: Callable[[str], T], device: str) -> T:
    """Call run(device); if CUDA runs out of memory, free what we can and call run("cpu")."""
    try:
        return run(device)
    except Exception as exc:
        if device != "cuda" or not is_out_of_memory(exc):
            raise
        logger.warning("GPU ran out of memory, retrying on the CPU: %s", exc)
    free_gpu_memory()
    return run("cpu")
