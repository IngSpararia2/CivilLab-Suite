from __future__ import annotations


class SuelosNotImplementedError(RuntimeError):
    pass


def create_window(on_return_to_suite=None, suite_context=None):
    del on_return_to_suite, suite_context
    raise SuelosNotImplementedError(
        "Suelos Lab está registrado, pero su implementación técnica aún no existe."
    )
