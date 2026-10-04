import unittest

from fda_classifier.metrics import accuracy, macro_f1


class MetricTests(unittest.TestCase):
    def test_perfect_predictions(self):
        gold = [0, 1, 2, 2]
        self.assertEqual(accuracy(gold, gold), 1.0)
        self.assertEqual(macro_f1(gold, gold), 1.0)

    def test_macro_f1_ignores_classes_missing_from_the_gold_set(self):
        # Class 0 is partial, class 1 is a miss, class 2 has no gold rows.
        self.assertAlmostEqual(macro_f1([0, 0], [0, 1], num_labels=3), 1 / 3)


if __name__ == "__main__":
    unittest.main()
