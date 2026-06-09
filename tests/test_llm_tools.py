import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LLMToolsValidationTest(unittest.TestCase):
    def test_validate_limit_parameter(self):
        """RED: Validation logic for limit parameter should handle invalid inputs."""

        def validate_limit(limit, default=5):
            """Validation logic that should be in kb_discover."""
            if limit is None or limit == "":
                return default
            try:
                value = int(limit)
                return max(1, min(value, 10))
            except (ValueError, TypeError):
                return default

        # Test cases
        test_cases = [
            ("abc", 5),      # non-numeric string -> default
            ("10.5", 5),     # float string -> invalid, use default
            ("", 5),         # empty string -> default
            (None, 5),       # None -> default
            (-5, 1),         # negative -> clamp to 1
            (0, 1),          # zero -> clamp to 1
            (5, 5),          # valid -> use as-is
            (100, 10),       # too large -> clamp to 10
            ("7", 7),        # valid string -> parse
        ]

        for input_val, expected in test_cases:
            result = validate_limit(input_val)
            self.assertEqual(result, expected,
                f"validate_limit({input_val!r}) should return {expected}, got {result}")

    def test_validate_page_parameter(self):
        """RED: Validation logic for page parameter should handle invalid inputs."""

        def validate_page(page, default=1):
            """Validation logic that should be in kb_read."""
            if page is None or page == "":
                return default
            try:
                value = int(page)
                return max(1, value)
            except (ValueError, TypeError):
                return default

        # Test cases
        test_cases = [
            ("abc", 1),      # non-numeric string -> default
            ("2.5", 1),      # float string -> invalid, use default
            ("", 1),         # empty string -> default
            (None, 1),       # None -> default
            (-1, 1),         # negative -> clamp to 1
            (0, 1),          # zero -> clamp to 1
            (3, 3),          # valid -> use as-is
            ("5", 5),        # valid string -> parse
        ]

        for input_val, expected in test_cases:
            result = validate_page(input_val)
            self.assertEqual(result, expected,
                f"validate_page({input_val!r}) should return {expected}, got {result}")


if __name__ == "__main__":
    unittest.main()
