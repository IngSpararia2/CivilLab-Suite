import pytest

from civillab_suite.modules.suelos.adapter import (
    SuelosNotImplementedError,
    create_window,
)


def test_suelos_is_an_explicit_non_implemented_scaffold():
    with pytest.raises(SuelosNotImplementedError, match="aún no existe"):
        create_window()
