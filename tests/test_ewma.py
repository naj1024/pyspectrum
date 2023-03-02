import pytest

from misc import Ewma


def test_ewma():
    values = [0.1, 1.0, 0.7, -0.4, 0.0, 0.0, 0.0]
    avg = Ewma.Ewma(0.3)
    for val in values:
        avg.average(val)
    assert avg.get_ewma() == pytest.approx(0.0632, rel=1e-3)
