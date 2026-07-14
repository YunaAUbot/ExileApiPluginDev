import tarfile
import tempfile
import unittest
from pathlib import Path

from exileapi_plugin_dev.snapshot_archive import filter_entries, load_or_build_index, read_member, select_entries, top_level_summary


class SnapshotArchiveTests(unittest.TestCase):
    def test_indexes_and_reads_only_selected_member(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "metadata.json"
            source.write_text('{"name":"test"}')
            archive = root / "test.exapisnap"
            with tarfile.open(archive, "w") as tar:
                tar.add(source, arcname="metadata/summary.json")
            index = load_or_build_index(archive, root / "cache")
            self.assertEqual(index["snapshot"], "test.exapisnap")
            self.assertEqual(top_level_summary(index), [{"path": "metadata", "entries": 1, "bytes": 15}])
            entry = select_entries(index, query="summary")[0]
            self.assertEqual(filter_entries(index, ["metadata", "summary"], ["nope"], 10), [entry])
            self.assertEqual(read_member(archive, index, entry["path"], 100), b'{"name":"test"}')
