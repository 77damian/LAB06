"""Focused checks for simulation.sensor_values."""
from itertools import islice
import inspect
import math
import random
import unittest
from unittest.mock import patch

from simulation import sensor_values


def spec(**changes):
    base = {"room": "laboratory", "sensor_id": "station-01", "metric": "temperature",
            "interval_seconds": 1, "mean": 21.0, "noise_std": 0.25, "seed": 42}
    return {**base, **changes}


class SensorValuesTests(unittest.TestCase):
    def test_is_generator_and_lazy(self):
        with patch("simulation.random.Random", wraps=random.Random) as factory:
            stream = sensor_values(spec())
            self.assertTrue(inspect.isgenerator(stream))
            factory.assert_not_called()
            next(stream)
            factory.assert_called_once_with(42)
            stream.close()

    def test_same_seed_reproducible_different_seed_differs(self):
        a = list(islice(sensor_values(spec()), 20))
        self.assertEqual(a, list(islice(sensor_values(spec()), 20)))
        self.assertNotEqual(a, list(islice(sensor_values(spec(seed=7)), 20)))

    def test_interleaving_and_global_state_untouched(self):
        state = random.getstate()
        a, b = sensor_values(spec(seed=1)), sensor_values(spec(seed=2))
        mixed = [next(a), next(b), next(a), next(b)]
        ea = list(islice(sensor_values(spec(seed=1)), 2))
        eb = list(islice(sensor_values(spec(seed=2)), 2))
        self.assertEqual(mixed, [ea[0], eb[0], ea[1], eb[1]])
        self.assertEqual(random.getstate(), state)

    def test_zero_noise_is_constant_mean_floats(self):
        values = list(islice(sensor_values(spec(noise_std=0)), 5))
        self.assertEqual(values, [21.0] * 5)
        self.assertTrue(all(isinstance(v, float) for v in values))

    def test_gaussian_statistics(self):
        values = list(islice(sensor_values(spec(noise_std=2.0, seed=3)), 20000))
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        self.assertAlmostEqual(mean, 21.0, delta=0.1)
        self.assertAlmostEqual(std, 2.0, delta=0.1)

    def test_metric_limits(self):
        hum = list(islice(sensor_values(spec(metric="humidity", mean=50, noise_std=1000)), 500))
        pre = list(islice(sensor_values(spec(metric="pressure", mean=1, noise_std=1000)), 500))
        tem = list(islice(sensor_values(spec(mean=0, noise_std=1000)), 500))
        self.assertTrue(all(0 <= v <= 100 for v in hum))
        self.assertIn(0.0, hum); self.assertIn(100.0, hum)
        self.assertTrue(all(v >= 0 for v in pre))
        self.assertTrue(any(v < 0 for v in tem))  # temperature is not clipped

    def test_nonfinite_values_rejected(self):
        for bad in (math.nan, math.inf):
            with patch("simulation.random.Random") as factory:
                factory.return_value.gauss.return_value = bad
                with self.assertRaises(ValueError):
                    next(sensor_values(spec()))

    def test_does_not_sleep_or_mutate_config(self):
        s = spec()
        before = dict(s)
        with patch("time.sleep") as sleeper:
            list(islice(sensor_values(s), 100))
        sleeper.assert_not_called()
        self.assertEqual(s, before)


if __name__ == "__main__":
    unittest.main()
