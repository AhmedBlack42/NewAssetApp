import unittest

from app.core.confidence_verification import model_verified


class ConfidenceVerificationTests(unittest.TestCase):
    def test_strictly_greater_than_77(self):
        self.assertFalse(model_verified(0.7700))
        self.assertFalse(model_verified(0.7699))
        self.assertTrue(model_verified(0.7701))
        self.assertFalse(model_verified(None))
        self.assertFalse(model_verified(float("nan")))
