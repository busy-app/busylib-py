from examples.bc.transfer import _progress_fraction


def test_progress_fraction_bounds() -> None:
    """
    Ensure progress fraction clamps and handles zero totals.
    """
    assert _progress_fraction(0, 0) == 0.0
    assert _progress_fraction(5, 10) == 0.5
    assert _progress_fraction(15, 10) == 1.0
    assert _progress_fraction(-5, 10) == 0.0
