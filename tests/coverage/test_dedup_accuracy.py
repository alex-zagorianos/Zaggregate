import json
from pathlib import Path
from models import JobResult
from coverage.resolve import resolve

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "coverage" / "labeled_pairs.jsonl"

def _pairs():
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)

def _predict_same(a: dict, b: dict) -> bool:
    return len(resolve([JobResult(**a), JobResult(**b)])) == 1

def test_dedup_f1_meets_floor():
    tp = fp = fn = tn = 0
    for p in _pairs():
        pred, truth = _predict_same(p["a"], p["b"]), bool(p["same"])
        if pred and truth: tp += 1
        elif pred and not truth: fp += 1
        elif not pred and truth: fn += 1
        else: tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    assert f1 >= 0.85, f"F1={f1:.3f} P={precision:.3f} R={recall:.3f}"
    assert precision >= 0.80 and recall >= 0.80
