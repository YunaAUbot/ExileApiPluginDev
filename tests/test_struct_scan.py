import unittest

from exileapi_plugin_dev.server import _rank_scan_paths, _truncated_snapshot_paths


class StructScanTests(unittest.TestCase):
    def test_collects_only_addressable_truncated_branches(self) -> None:
        snapshot = {
            "shortcuts": {
                "Player": {
                    "_type": "PlayerType",
                    "Currency": {"_type": "CurrencyType", "_truncated": "depth_limit"},
                    "Values": [{"_truncated": "depth_limit"}],
                }
            }
        }

        self.assertEqual(_truncated_snapshot_paths(snapshot), ["Player.Currency"])

    def test_goal_related_paths_are_preferred_to_layout_noise(self) -> None:
        paths = ["IngameUI.CurrencyExchangePanel.Position", "IngameUI.CurrencyExchangePanel.Offers"]

        self.assertEqual(_rank_scan_paths(paths, "currency offers")[0], "IngameUI.CurrencyExchangePanel.Offers")

