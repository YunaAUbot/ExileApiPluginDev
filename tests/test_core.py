import tempfile
import unittest
from pathlib import Path

from exileapi_plugin_dev.core import csharp_identifier, read_tail, scaffold_plugin, validate_plugin_name


class PluginScaffoldTests(unittest.TestCase):
    def test_name_validation_and_csharp_normalisation(self):
        self.assertEqual(validate_plugin_name("My-Plugin.2"), "My-Plugin.2")
        self.assertEqual(csharp_identifier("My-Plugin.2"), "My_Plugin_2")
        with self.assertRaises(ValueError):
            validate_plugin_name("../escape")

    def test_scaffold_uses_current_exileapi_settings_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = scaffold_plugin(Path(temporary_directory), "My-Plugin", "A test plugin")
            source = Path(result["created"]) / result["source"]
            self.assertIn("namespace My_Plugin;", source.read_text())
            self.assertIn("public ToggleNode Enable { get; set; } = new(true);", source.read_text())
            with self.assertRaises(ValueError):
                scaffold_plugin(Path(temporary_directory), "My-Plugin", "duplicate")

    def test_tail_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log = Path(temporary_directory) / "Errors.txt"
            log.write_text("one\ntwo\nthree\n")
            self.assertEqual(read_tail(log, 2), "two\nthree")


if __name__ == "__main__":
    unittest.main()
