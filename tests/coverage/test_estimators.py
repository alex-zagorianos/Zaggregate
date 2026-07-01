import math
from coverage.estimators import (chapman, chao1, chao2, good_turing, loglinear,
                                 loglinear_ci, jackknife1, jackknife2)

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


def test_chao2_finite_sample_correction():
    # With q1=10, q2=5, s_obs=50, t=3: correction = (t-1)/t = 2/3.
    expected = 50 + (2 / 3) * (10 * 9) / (2 * 6)
    assert abs(chao2(10, 5, 50, 3) - expected) < 1e-9
    # chao2 is strictly below chao1 (the uncorrected form) for finite t>=2.
    assert chao2(10, 5, 50, 3) < chao1(10, 5, 50)


def test_chao2_degenerate_single_sample():
    # t<2 -> no unseen-class info -> degenerate to s_obs (honest "no ceiling"),
    # like jackknife, NOT the exploded uncorrected chao1 form.
    assert chao2(10, 5, 50, 1) == 50.0
    assert chao2(10, 5, 50, 0) == 50.0


def test_chao2_q2_zero_no_div_error():
    assert chao2(4, 0, 10, 4) == 10 + (3 / 4) * (4 * 3) / 2


def test_jackknife1():
    # s_obs + q1*(t-1)/t
    assert jackknife1(10, 50, 4) == 50 + 10 * 3 / 4
    assert jackknife1(10, 50, 1) == 50.0          # single sample -> degenerate
    assert jackknife1(10, 50, 0) == 50.0


def test_jackknife2():
    q1, q2, s_obs, t = 10, 5, 50, 4
    expected = s_obs + q1 * (2 * t - 3) / t - q2 * (t - 2) ** 2 / (t * (t - 1))
    assert abs(jackknife2(q1, q2, s_obs, t) - expected) < 1e-9
    assert jackknife2(10, 5, 50, 2) == 50.0        # needs t>=3
    assert jackknife2(10, 5, 50, 1) == 50.0


def test_loglinear_ci_brackets_point_and_is_deterministic():
    membership = ([frozenset({"a"})] * 80 + [frozenset({"b"})] * 80
                  + [frozenset({"c"})] * 60 + [frozenset({"a", "b"})] * 20
                  + [frozenset({"a", "c"})] * 15 + [frozenset({"b", "c"})] * 10)
    point, lo, hi = loglinear_ci(membership, n_boot=100)
    assert lo <= point <= hi
    assert lo <= hi
    # Deterministic given the default seed.
    assert loglinear_ci(membership, n_boot=100) == (point, lo, hi)


def test_loglinear_ci_empty():
    assert loglinear_ci([], n_boot=50) == (0.0, 0.0, 0.0)
