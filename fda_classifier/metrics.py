"""Classification metrics that do not pull in scikit-learn."""

from __future__ import annotations

from fda_classifier import LABELS


def accuracy(predictions: list[int], labels: list[int]) -> float:
    if not labels:
        return 0.0
    correct = sum(pred == label for pred, label in zip(predictions, labels))
    return correct / len(labels)


def macro_f1(predictions: list[int], labels: list[int], num_labels: int | None = None) -> float:
    count = num_labels if num_labels is not None else len(LABELS)
    scores = [_binary_f1(predictions, labels, class_id) for class_id in range(count)]
    present = [score for score in scores if score is not None]
    if not present:
        return 0.0
    return sum(present) / len(present)


def _binary_f1(predictions: list[int], labels: list[int], class_id: int) -> float | None:
    support = sum(label == class_id for label in labels)
    if support == 0:
        return None
    true_positive = sum(
        pred == class_id and label == class_id for pred, label in zip(predictions, labels)
    )
    predicted = sum(pred == class_id for pred in predictions)
    if true_positive == 0:
        return 0.0
    precision = true_positive / predicted
    recall = true_positive / support
    return 2 * precision * recall / (precision + recall)
