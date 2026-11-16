"""Name -> factory registry for property backends (open/closed principle).

The solver, CLI and GUI select a backend only through
``get_property_provider(name, **kwargs)``. A new backend is added by calling
``register_provider`` (or using it as a decorator) from any module, so no
solver code needs to change::

    @register_provider("my-gas")
    class MyGasProvider(PropertyProvider): ...
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from brayton_cycle.core.exceptions import InputValidationError
from brayton_cycle.core.interfaces import PropertyProvider

ProviderFactory = Callable[..., PropertyProvider]
F = TypeVar("F", bound=ProviderFactory)

_REGISTRY: dict[str, ProviderFactory] = {}


def _key(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def register_provider(
    name: str, factory: ProviderFactory | None = None, *, overwrite: bool = False
) -> Any:
    """Register ``factory`` (a class or callable returning a provider) under ``name``.

    Can be used as ``register_provider("x", Cls)`` or as a decorator
    ``@register_provider("x")``. Raises ``KeyError`` on a duplicate name
    unless ``overwrite=True``.

    Args:
        name: Registry key (case-insensitive; '_' treated as '-').
        factory: Class or callable returning a ``PropertyProvider`` (omit to use as decorator).
        overwrite: Replace an existing registration instead of raising.

    Returns:
        The factory (so it can be used as a decorator).
    """

    def _do(f: F) -> F:
        key = _key(name)
        if key in _REGISTRY and not overwrite:
            raise KeyError(f"property provider {key!r} is already registered")
        _REGISTRY[key] = f
        return f

    return _do(factory) if factory is not None else _do


def unregister_provider(name: str) -> None:
    """Remove a backend from the registry (mainly for tests).

    Args:
        name: Registry key to remove.

    Returns:
        None.
    """
    _REGISTRY.pop(_key(name), None)


def available_providers() -> list[str]:
    """Registered backend names (optional ones are listed even if not installed)."""
    return sorted(_REGISTRY)


def get_property_provider(name: str, **kwargs: Any) -> PropertyProvider:
    """Instantiate the backend registered under ``name``.

    Args:
        name: Registry key or alias of the backend.

    Returns:
        A new backend instance.

    Raises:
        KeyError: unknown name (the message lists the valid names).
        InputValidationError: ``kwargs`` do not match the backend's constructor.
        BackendUnavailable: the optional package for the backend is not installed.
    """
    key = _key(name)
    try:
        factory = _REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"unknown property provider {name!r}; available: {', '.join(available_providers())}"
        ) from None
    try:
        inspect.signature(factory).bind(**kwargs)
    except TypeError as exc:
        raise InputValidationError(f"invalid options for provider {key!r}: {exc}") from None
    return factory(**kwargs)
