from dataclasses import dataclass


def variant(_cls=None, *, frozen=True, slots=True):
    """Small ADT helper: applies dataclass uniformly to every variant."""

    def wrap(cls):
        return dataclass(frozen=frozen, slots=slots)(cls)

    if _cls is None:
        return wrap
    return wrap(_cls)
