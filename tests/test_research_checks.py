import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checks", ROOT / ".agents/skills/a-share-research/scripts/research_checks.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def fact(eid="E001", tier="S", family="issuer-report"):
    return dict(id=eid, content="synthetic test fact", type="Fact", source_title="test",
                publisher="test issuer", url="https://example.org/report", published_at="2026-08-19",
                period="2026H1", accessed_at="2026-10-13", tier=tier, confidence="high",
                confidence_reason="test fixture", status="verified", access_method="fixture",
                access_result="read", locator="p2", source_family=family, value=100,
                unit="CNY", value_basis="reported", notes="synthetic fixture, not actual research",
                supersedes=[], conflict_with=[])


def claim(ids=None):
    return dict(id="C001", category="financial", importance="core", evidence_ids=ids or ["E001"],
                logic="synthetic explanation", assumptions=[], conclusion="conditional test conclusion",
                counter_evidence_ids=[], falsification="test observation", status="supported", calculation=None)


class ResearchChecks(unittest.TestCase):
    def setUp(self):
        self.run = dict(schema_version="1.0", run_id="test", company="test", ticker="300394.SZ",
                        market="A-share", currency="CNY", as_of="2026-10-13", timezone="Asia/Shanghai",
                        horizon="3个月", mode="中短期", style="平衡研究", status="limited", gaps=[])

    def test_single_s_supports_core(self):
        self.assertEqual(checks.validate(self.run, [fact()], [claim()]), [])

    def test_reprints_are_not_independent(self):
        items = [fact("E001", "A"), fact("E002", "A")]
        self.assertTrue(checks.validate(self.run, items, [claim(["E001", "E002"])]))

    def test_two_independent_a_sources(self):
        items = [fact("E001", "A", "one"), fact("E002", "A", "two")]
        self.assertEqual(checks.validate(self.run, items, [claim(["E001", "E002"])]), [])

    def test_future_disclosure_is_rejected(self):
        e = fact()
        e["published_at"] = "2026-10-14"
        self.assertTrue(checks.validate(self.run, [e], []))

    def test_unknown_publication_date_needs_explanation(self):
        e = fact()
        e.update(published_at=None, notes="")
        self.assertTrue(checks.validate(self.run, [e], []))

    def test_social_fact_is_rejected(self):
        self.assertTrue(checks.validate(self.run, [fact(tier="D")], [claim()]))

    def test_opinion_does_not_support_fact_conclusion(self):
        e = fact()
        e.update(type="Opinion", status="attributed")
        self.assertTrue(checks.validate(self.run, [e], [claim()]))

    def test_unresolved_conflict(self):
        e = fact()
        e["conflict_with"] = ["E002"]
        self.assertTrue(checks.validate(self.run, [e, fact("E002")], [claim()]))

    def test_unknown_reference(self):
        self.assertTrue(checks.validate(self.run, [fact()], [claim(["missing"])]))

    def test_forecast_cannot_be_actual_calculation(self):
        e = fact()
        e["value_basis"] = "forecast"
        c = claim()
        c["calculation"] = dict(inputs=[dict(name="profit", value=100, unit="CNY", evidence_ids=["E001"])],
                                formula="profit", output=100, unit="CNY", rounding="none",
                                basis_date="2026-10-13", basis="actual")
        self.assertTrue(checks.validate(self.run, [e], [c]))
        c["calculation"]["basis"] = "forecast"
        self.assertEqual(checks.validate(self.run, [e], [c]), [])

    def test_infinite_values(self):
        e = fact()
        e["value"] = float("inf")
        self.assertTrue(checks.validate(self.run, [e], []))

    def config(self):
        metric = dict(name="fixture", observed=10, evidence_ids=["E001"],
                      rule=dict(kind="numeric", direction="higher", thresholds=[0, 5, 10, 20],
                                basis="synthetic test thresholds"), notes="test")
        return dict(dimensions={n: dict(metrics=[copy.deepcopy(metric) for _ in range(3)])
                                for n in checks.WEIGHTS}, risk_review_complete=True, risks=[])

    def test_weight_normalization_and_risk_cap(self):
        cfg = self.config()
        cfg["risks"] = [dict(name=str(i), triggered=True, deduction=20, evidence_ids=["E001"],
                             rule="test rule") for i in range(2)]
        result = checks.score(cfg, {"E001": fact()})
        self.assertEqual(result["company_quality"], 75)
        self.assertEqual(result["opportunity_gross"], 75)
        self.assertEqual(result["risk_deduction"], 20)
        self.assertEqual(result["opportunity_net"], 55)

    def test_missing_does_not_renormalize(self):
        cfg = self.config()
        cfg["dimensions"]["valuation"]["metrics"][0]["observed"] = None
        result = checks.score(cfg, {"E001": fact()})
        self.assertEqual(result["company_quality"], 75)
        self.assertIsNone(result["opportunity_gross"])
        self.assertAlmostEqual(result["weight_coverage_percent"], 75 / 90 * 100)

    def test_forecast_and_social_cannot_score(self):
        e = fact()
        e["value_basis"] = "forecast"
        with self.assertRaises(ValueError):
            checks.score(self.config(), {"E001": e})
        with self.assertRaises(ValueError):
            checks.score(self.config(), {"E001": fact(tier="D")})

    def test_threshold_order(self):
        cfg = self.config()
        cfg["dimensions"]["finance"]["metrics"][0]["rule"]["thresholds"] = [10, 5, 20, 30]
        with self.assertRaises(ValueError):
            checks.score(cfg, {"E001": fact()})

    def test_unreviewed_risk_is_not_zero(self):
        cfg = self.config()
        cfg["risk_review_complete"] = False
        result = checks.score(cfg, {"E001": fact()})
        self.assertIsNone(result["risk_deduction"])
        self.assertIsNone(result["opportunity_net"])

    def test_disclosure_and_lower_boundary(self):
        cfg = self.config()
        m = cfg["dimensions"]["finance"]["metrics"][0]
        m.update(observed="best", rule=dict(kind="disclosure", bands=["worst", "bad", "mid", "good", "best"], basis="test"))
        self.assertAlmostEqual(checks.score(cfg, {"E001": fact()})["dimensions"]["finance"], 250 / 3)
        m.update(observed=10, rule=dict(kind="numeric", direction="lower", thresholds=[0, 5, 10, 20], basis="test"))
        self.assertAlmostEqual(checks.score(cfg, {"E001": fact()})["dimensions"]["finance"], 175 / 3)


if __name__ == "__main__":
    unittest.main()
