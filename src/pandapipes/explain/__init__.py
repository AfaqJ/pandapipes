"""
pandapipes-explain: Local LLM diagnostic explanations for pandapipes errors.

Usage
-----
# Pattern A — global hook (best for scripts)
import pandapipes.explain
pandapipes.explain.enable()

# Pattern B — context manager (best for notebooks / selective wrapping)
import pandapipes.explain
with pandapipes.explain.explain():
    pp.pipeflow(net)
"""

from pandapipes.explain.core.config import get_config
from pandapipes.explain.core import intercept
from contextlib import contextmanager

__version__ = "0.1.0"
__all__ = ["enable", "disable", "explain"]


def enable(
    model: str = "llama3.1:8b",
    ollama_host: str = "http://localhost:11434",
    source_context_lines: int = 30,
) -> None:
    """
    Install the LLM diagnostic hook globally.

    Call once at the top of a script or notebook.
    Any uncaught pandapipes exception will trigger an LLM explanation.

    Parameters
    ----------
    model : str
        Ollama model to use. Must be pulled first: ``ollama pull <model>``.
    ollama_host : str
        Base URL of the running Ollama server.
    source_context_lines : int
        Lines of source code to show around the error line.
    """
    cfg = get_config()
    cfg.model = model
    cfg.ollama_host = ollama_host
    cfg.source_context_lines = source_context_lines
    intercept.install()


def disable() -> None:
    """Remove the LLM diagnostic hook."""
    intercept.uninstall()


@contextmanager
def explain(
    model: str = "llama3.1:8b",
    ollama_host: str = "http://localhost:11434",
    source_context_lines: int = 30,
):
    """
    Context manager — enable the hook for a specific block of code only.

    The exception is explained then re-raised. The traceback is printed
    exactly once (by the context manager), so it will not be printed again
    by IPython's set_custom_exc handler.

    Example
    -------
    with pandapipes.explain.explain():
        pp.pipeflow(net)
    """
    enable(model=model, ollama_host=ollama_host, source_context_lines=source_context_lines)
    try:
        yield
    except Exception as exc:
        exc_type = type(exc)
        exc_tb = exc.__traceback__
        import traceback as _tb
        # Print the traceback exactly once here.
        _tb.print_exception(exc_type, exc, exc_tb)
        # Temporarily disable so the re-raise does NOT trigger the excepthook again.
        from pandapipes.explain.core.config import get_config
        get_config().enabled = False
        try:
            from pandapipes.explain.core import dispatcher
            dispatcher.handle(exc_type, exc, exc_tb)
        except Exception:
            pass
        finally:
            get_config().enabled = True
        raise
    finally:
        disable()
