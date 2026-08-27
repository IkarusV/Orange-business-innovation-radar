import unittest

from radar_v2.services import market_size_repository


class MarketSizeRepositoryTests(unittest.TestCase):
    def test_pending_record_never_displays_context_as_eur_market_size(self):
        result = market_size_repository._compact({
        "opportunity_key": "Public/Gov sector|compliance-monitoring|cybersecurity-platform",
        "market_size": {
            "status": "pending_or_unavailable",
            "low_eur": None, "central_eur": None, "high_eur": None,
            "countries_covered": 2, "countries_expected": 29, "coverage_ratio": 2 / 29,
            "public_employment_persons": 14_000_000,
            "general_public_services_expenditure_eur": 1_100_000_000_000,
            "blocking_reasons": ["blocked_annual_value_not_approved"],
        },
        "statistical_mapping": {"denominator_method": "public_buyer_count"},
        })

        self.assertFalse(result["estimated"])
        self.assertIsNone(result["low_eur"])
        self.assertEqual(result["range_label"], "Estimate pending")
        self.assertIn("not the opportunity's market size", result["context_note"])

    def test_valid_estimate_is_formatted_as_non_negative_range(self):
        result = market_size_repository._compact({
        "opportunity_key": "Manufacturing|predictive-maintenance|digital-twin",
        "market_size": {
            "status": "estimated",
            "low_eur": 42_000_000, "central_eur": 68_000_000, "high_eur": 105_000_000,
            "countries_covered": 27, "countries_expected": 29, "coverage_ratio": 27 / 29,
            "blocking_reasons": [],
        },
        "statistical_mapping": {"denominator_method": "sbs_enterprise_count"},
        })

        self.assertTrue(result["estimated"])
        self.assertEqual(result["range_label"], "€42.0m – €105.0m")
        self.assertEqual(result["central_eur"], 68_000_000)

    def test_invalid_negative_or_unordered_estimate_is_suppressed(self):
        result = market_size_repository._compact({
        "opportunity_key": "Retail|customer-service-automation|generative-ai-llms",
        "market_size": {
            "status": "estimated",
            "low_eur": -1, "central_eur": 5, "high_eur": 4,
            "blocking_reasons": [],
        },
        "statistical_mapping": {"denominator_method": "sbs_enterprise_count"},
        })

        self.assertFalse(result["estimated"])
        self.assertEqual(result["status"], "invalid_estimate_suppressed")
        self.assertIsNone(result["low_eur"])

    def test_unmatched_opportunity_remains_available_with_explicit_gap(self):
        result = market_size_repository._empty()
        self.assertFalse(result["matched"])
        self.assertEqual(result["range_label"], "Estimate unavailable")


if __name__ == "__main__":
    unittest.main()
