import unittest

from app.core.shared_cnn import load_head_class_counts


class SharedCNNRegistryTests(unittest.TestCase):
    def test_five_head_dimensions_match_registry(self):
        self.assertEqual(load_head_class_counts(), {
            "body_images": 2,
            "fullbody": 5,
            "portrait": 2,
            "arousal": 2,
            "corruption": 4,
        })


if __name__ == "__main__":
    unittest.main()
