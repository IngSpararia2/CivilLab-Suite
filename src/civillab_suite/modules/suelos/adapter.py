from __future__ import annotations


class SuelosNotImplementedError(RuntimeError):
    pass


def create_window(on_return_to_suite=None):
    del on_return_to_suite
    raise SuelosNotImplementedError(
        "Suelos Lab está registrado, pero su implementación técnica aún no existe."
    )
