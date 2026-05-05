"""Shared argument-normalisation utilities for storage backends."""

from .base import PalaceRef


def _normalize_get_collection_args(args, kwargs):
    """Unify legacy positional ``(palace_path, collection_name, create)`` calls
    with the new kwargs-only ``(palace=PalaceRef, collection_name=..., create=...)``.

    Returns ``(PalaceRef, collection_name, create, options)``.
    """
    # New-style: palace= kwarg with a PalaceRef (spec path).
    if "palace" in kwargs:
        palace_ref = kwargs.pop("palace")
        if not isinstance(palace_ref, PalaceRef):
            raise TypeError("palace= must be a PalaceRef instance")
        collection_name = kwargs.pop("collection_name")
        create = kwargs.pop("create", False)
        options = kwargs.pop("options", None)
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        if args:
            raise TypeError("positional args not allowed with palace= kwarg")
        return palace_ref, collection_name, create, options

    # Legacy: first positional is a path string.
    if args:
        palace_path = args[0]
        rest = list(args[1:])
        collection_name = kwargs.pop("collection_name", None) or (rest.pop(0) if rest else None)
        if collection_name is None:
            raise TypeError("collection_name is required")
        create = kwargs.pop("create", False)
        if rest:
            create = rest.pop(0)
        if rest:
            raise TypeError(f"unexpected positional args: {rest!r}")
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        return (
            PalaceRef(id=palace_path, local_path=palace_path),
            collection_name,
            bool(create),
            None,
        )

    # Legacy kwargs-only (palace_path=..., collection_name=..., create=...)
    if "palace_path" in kwargs:
        palace_path = kwargs.pop("palace_path")
        collection_name = kwargs.pop("collection_name")
        create = kwargs.pop("create", False)
        if kwargs:
            raise TypeError(f"unexpected kwargs: {sorted(kwargs)}")
        return (
            PalaceRef(id=palace_path, local_path=palace_path),
            collection_name,
            bool(create),
            None,
        )

    raise TypeError("get_collection requires palace= or a positional palace_path")
