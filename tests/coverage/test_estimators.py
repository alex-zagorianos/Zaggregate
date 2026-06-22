import math
from coverage.estimators import chapman, chao1, good_turing, loglinear

def test_chapman_known_value():
    # Canonical Chapman (modified Petersen): N = (n1+1)(n2+1)/(m+1) - 1.
    # The plan's literal constant (480.0476...) was arithmetically inconsistent
    # with its own formula; this is the true output for (100, 100, 20).
    r = chapman(100, 100, 20)
    assert abs(r.n_hat - 484.76190476190476) < 1e-6
    assert r.ci95[0] < r.n_hat < r.ci95[1]

def test_chao1_known_value():
    assert chao1(10, 5, 50) == 50 + (10 * 9) / (2 * 6)

def test_chao1_f2_zero_no_div_error():
    assert chao1(4, 0, 10) == 10 + (4 * 3) / 2

def test_good_turing():
    assert good_turing(10, 100) == 0.9

def test_good_turing_zero_n():
    assert good_turing(0, 0) == 0.0

def test_loglinear_two_sources_falls_back():
    membership = [frozenset({"a"})] * 80 + [frozenset({"b"})] * 80 + [frozenset({"a", "b"})] * 20
    assert loglinear(membership) > 0
