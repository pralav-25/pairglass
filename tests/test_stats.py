import math
import unittest

from pairglass.stats import holm_adjust, paired_regression_p


class PairedRegressionTests(unittest.TestCase):
    def test_exhaustive_small_counts_against_exact_integer_distribution(self):
        for total in range(31):
            for losses in range(total + 1):
                with self.subTest(total=total, losses=losses):
                    expected = sum(math.comb(total, count) for count in range(losses, total + 1)) / 2**total
                    self.assertAlmostEqual(paired_regression_p(total - losses, losses), expected, places=14)

    def test_regression_is_one_sided_and_uses_only_discordances(self):
        self.assertAlmostEqual(paired_regression_p(3, 7), 0.171875)
        self.assertAlmostEqual(paired_regression_p(7, 3), 0.9453125)
        self.assertEqual(paired_regression_p(0, 0), 1)
        self.assertEqual(paired_regression_p(100_000, 0), 1)
        self.assertAlmostEqual(paired_regression_p(0, 12), 1 / 4096)

    def test_large_central_tail_matches_independent_product_identity(self):
        # P[X >= m] = 1/2 + P[X = m]/2 for Binomial(2m, 1/2).
        # This independent product avoids huge binomial integer conversions.
        mass = math.prod((2 * index - 1) / (2 * index) for index in range(1, 50_001))
        self.assertAlmostEqual(paired_regression_p(50_000, 50_000), 0.5 + 0.5 * mass, places=14)
        self.assertAlmostEqual(paired_regression_p(49_999, 50_001), 0.5 - 0.5 * mass, places=14)

    def test_large_and_subnormal_tails_do_not_overflow(self):
        self.assertAlmostEqual(paired_regression_p(49_000, 51_000), 1.2943580191734434e-10, delta=1e-23)
        self.assertEqual(paired_regression_p(0, 1074), math.ldexp(1.0, -1074))
        self.assertEqual(paired_regression_p(0, 100_000), 0)

    def test_invalid_counts_are_rejected(self):
        for value in (-1, 1.5, "1", True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                paired_regression_p(value, 1)
            with self.subTest(value=value), self.assertRaises(ValueError):
                paired_regression_p(1, value)


class HolmTests(unittest.TestCase):
    def test_holm_preserves_order_and_enforces_monotonic_adjustment(self):
        actual = holm_adjust([0.03, 0.01, 0.02, 0.5])
        for found, expected in zip(actual, [0.06, 0.04, 0.06, 0.5]):
            self.assertAlmostEqual(found, expected)

    def test_ties_empty_and_clamping(self):
        self.assertEqual(holm_adjust([]), [])
        self.assertEqual(holm_adjust([0, 1]), [0, 1])
        self.assertEqual(holm_adjust([0.9, 0.9, 0.9]), [1, 1, 1])
        self.assertEqual(holm_adjust([0.1, 0.1]), [0.2, 0.2])

    def test_invalid_probabilities(self):
        for value in (-0.1, 1.1, float("nan"), float("inf"), True, "0.1", None, 10**1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                holm_adjust([value])


if __name__ == "__main__":
    unittest.main()
