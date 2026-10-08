from __future__ import annotations

import re
import unittest
from dataclasses import replace
from pathlib import Path

from ibis_auto.config import parse_config
from ibis_auto.generator import _template


ROOT = Path(__file__).resolve().parents[1]
TOP_SUBCKT = "authoritative_spf_top"
RON = 30


class TemplateRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = parse_config(ROOT / "inputs/config/ibis_config.xlsx")
        cls.plan = cls.config.modules[0]

    def render(self, template_type: str) -> str:
        direction = "DRV" if template_type.startswith("drv_") else "RCV"
        rendered, spice = _template(
            self.config,
            self.plan,
            direction,
            RON,
            template_type,
            TOP_SUBCKT,
        )
        self.assertEqual(spice, "spectre")
        return rendered

    def test_config_values_are_present_in_the_canonical_model(self):
        self.assertEqual(self.plan.ibis_io_voltage_domain, "VDDQ")
        self.assertEqual(self.plan.ibis_vih_voltage_domain, "VDD")
        self.assertEqual(self.plan.tr, {"MAX": "20p", "TYP": "20p", "MIN": "20p"})
        self.assertEqual(self.plan.tf, {"MAX": "20p", "TYP": "20p", "MIN": "20p"})

    def test_renderer_consumes_canonical_domains_and_corner_values(self):
        plan = replace(
            self.plan,
            ibis_io_voltage_domain="VDD",
            ibis_vih_voltage_domain="VDDQ",
            tr={"MAX": "30p", "TYP": "10p", "MIN": "20p"},
            tf={"MAX": "31p", "TYP": "11p", "MIN": "21p"},
        )
        text, _spice = _template(
            self.config,
            plan,
            "DRV",
            RON,
            "drv_diff",
            TOP_SUBCKT,
        )

        self.assertIn("[Voltage Range] 0.75 0.6975 0.825", text)
        self.assertIn("[Vih] 0.5 0.47 0.57", text)
        self.assertIn("[Tr] 10p 20p 30p", text)
        self.assertIn("[Tf] 11p 21p 31p", text)
        self.assertIn("[Vmeas] 0.1875 0.174375 0.20625", text)
        self.assertIn("[Vinh] 0.2375 0.224375 0.25625", text)
        self.assertIn("[Vinl] 0.1375 0.124375 0.15625", text)

    def test_all_current_templates_render_the_common_dynamic_fields(self):
        for template_type in ("drv_se", "drv_diff", "rcv_se", "rcv_diff"):
            with self.subTest(template=template_type):
                text = self.render(template_type)
                direction = "drv" if template_type.startswith("drv_") else "rcv"

                self.assertNotRegex(text, r"\{\{[^{}]+\}\}")
                self.assertNotIn("[Model Selector]", text)
                self.assertRegex(text, r"(?m)^\[Date\] \d{4}/\d{2}$")
                self.assertIn(f"[File name] {TOP_SUBCKT}_{direction}_ron{RON}.ibs", text)
                self.assertIn(f"[Component] {TOP_SUBCKT}", text)
                self.assertIn("[Spice type] spectre", text)
                self.assertIn("[Spice command] spectre +preset=mx +spice +mt=4", text)
                self.assertIn("[Temperature Range] 25 -40 125", text)
                self.assertIn("[Voltage Range] 0.5 0.47 0.57", text)
                self.assertIn("[Vih] 0.75 0.6975 0.825", text)
                self.assertIn("[Tr] 20p 20p 20p", text)
                self.assertIn("[Tf] 20p 20p 20p", text)
                self.assertIn("[Vinh] 0.175 0.1675 0.1925", text)
                self.assertIn("[Vinl] 0.075 0.0675 0.0925", text)
                self.assertNotRegex(
                    text,
                    r"(?im)^\[Model file\].*(?:_io_diff|_io_se|iodiff)",
                )
                self.assertIn("[Spice file] component.sp", text)
                self.assertIn("[ExtSpiceCmd] ckt_topology.sp", text)

    def test_model_names_and_model_files_use_top_direction_and_ron(self):
        cases = {
            "drv_se": [f"{TOP_SUBCKT}_drv_ron{RON}_model"],
            "drv_diff": [
                f"{TOP_SUBCKT}_drv_ron{RON}_model_t",
                f"{TOP_SUBCKT}_drv_ron{RON}_model_c",
            ],
            "rcv_se": [f"{TOP_SUBCKT}_rcv_ron{RON}_model"],
            "rcv_diff": [
                f"{TOP_SUBCKT}_rcv_ron{RON}_model_t",
                f"{TOP_SUBCKT}_rcv_ron{RON}_model_c",
            ],
        }
        for template_type, expected_models in cases.items():
            with self.subTest(template=template_type):
                text = self.render(template_type)
                direction = "drv" if template_type.startswith("drv_") else "rcv"
                actual_models = re.findall(r"(?m)^\[Model\] (?!dummy$)(\S+)$", text)
                self.assertEqual(actual_models, expected_models)
                for model in expected_models:
                    self.assertGreaterEqual(text.count(model), 2)

                model_file = (
                    f"[Model file] corner_{direction}_ron{RON}_typ.sp "
                    f"corner_{direction}_ron{RON}_min.sp "
                    f"corner_{direction}_ron{RON}_max.sp"
                )
                self.assertEqual(text.count(model_file), len(expected_models))

                if template_type.endswith("_diff"):
                    self.assertIn("[Diff pin]\nipadt ipadc 0.25 0", text)
                else:
                    self.assertNotIn("[Diff pin]", text)
                    self.assertRegex(text, r"(?m)^iopad iopad iopad \S+_model$")

    def test_thresholds_and_waveforms_follow_each_template_structure(self):
        templates_with_vmeas = {"drv_se", "drv_diff", "rcv_se"}
        for template_type in ("drv_se", "drv_diff", "rcv_se", "rcv_diff"):
            with self.subTest(template=template_type):
                text = self.render(template_type)
                is_driver = template_type.startswith("drv_")
                model_count = 2 if template_type.endswith("_diff") else 1

                self.assertEqual(text.count("[Vinh] 0.175 0.1675 0.1925"), model_count)
                self.assertEqual(text.count("[Vinl] 0.075 0.0675 0.0925"), model_count)
                expected_vmeas_count = model_count if template_type in templates_with_vmeas else 0
                self.assertEqual(text.count("[Vmeas] 0.125 0.1175 0.1425"), expected_vmeas_count)

                rising_with_voltage = "[Rising waveform] 50 0.5 0.47 0.57 NA NA NA NA NA"
                falling_with_voltage = "[Falling waveform] 50 0.5 0.47 0.57 NA NA NA NA NA"
                if is_driver:
                    self.assertEqual(text.count(rising_with_voltage), model_count)
                    self.assertEqual(text.count(falling_with_voltage), model_count)
                else:
                    self.assertNotIn("[rising waveform]", text.casefold())
                    self.assertNotIn("[falling waveform]", text.casefold())


if __name__ == "__main__":
    unittest.main()
