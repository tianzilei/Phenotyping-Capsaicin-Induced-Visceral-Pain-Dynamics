import unittest
from capsaicin.ecg_lead_stability import candidate_rmssd_ms, tolerant_event_jaccard


class LeadStabilityTests(unittest.TestCase):
    def test_tolerant_jaccard_is_one_to_one(self):
        value, matches = tolerant_event_jaccard(
            [100, 200, 300], [101, 102, 299], 1000, 0.005
        )
        self.assertEqual(matches, 2)
        self.assertAlmostEqual(value, 0.5)

    def test_candidate_rmssd_uses_symmetric_blocks(self):
        self.assertIsNotNone(candidate_rmssd_ms([0, 1000, 2000, 3000], 1000))
        self.assertIsNone(candidate_rmssd_ms([0, 1000, 1500, 2500], 1000))


if __name__ == "__main__":
    unittest.main()
