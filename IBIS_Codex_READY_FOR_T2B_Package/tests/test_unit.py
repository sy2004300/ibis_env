from __future__ import annotations

import json
import unittest
from pathlib import Path

from ibis_auto.values import impedance_map, parse_logic, signal_bits

ROOT = Path(__file__).resolve().parents[1]


class RuleTests(unittest.TestCase):
    def test_impedance_minimum_codes(self):
        expected = json.loads((ROOT / "tests/test_vectors.json").read_text())["impedance_min_code"]
        text = " ".join(
            f"{code}: {ohm}ohm" + (f" {int(code, 2) + 1:04b}: {ohm}ohm" if code != "1111" else "")
            for ohm, code in expected.items()
        )
        self.assertEqual({str(k): v for k, v in impedance_map(text).items()}, expected)

    def test_logic_and_bus_expansion(self):
        self.assertEqual(parse_logic("8'h6A", "m", "s", 8), "01101010")
        self.assertEqual(signal_bits("bus[3:0]", 4), ["bus[3]", "bus[2]", "bus[1]", "bus[0]"])


if __name__ == "__main__":
    unittest.main()
