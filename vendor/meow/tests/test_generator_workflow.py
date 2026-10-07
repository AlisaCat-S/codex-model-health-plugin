from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from test_benchmarks import fixture
from test_execution import EchoModel, SECRET
from gpt56_vnext.errors import AppError
from gpt56_vnext.generator import collection_contract, collection_jobs, ProbeGeneratorSession, merge_windows
from gpt56_vnext.server import AppState
from gpt56_vnext.benchmark import normalize_project


class GeneratorWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_hundred_probe_draft_expands_to_exact_request_count(self):
        project = normalize_project({"id": "hundred", "mode": "gpt",
            "models": [{"id": f"m{i}"} for i in range(4)],
            "probes": [{"id": f"p{i}", "prompt": f"Choose an option for prompt {i}."} for i in range(100)]})
        jobs = collection_jobs(project, 3, 1)
        self.assertEqual(len(jobs), 1200)
        self.assertEqual(len({job["job_id"] for job in jobs}), 1200)
        self.assertEqual([sum(project["tiers"][tier]["counts"].values()) for tier in ("low", "medium", "high")], [400, 1000, 2000])

    def test_only_request_changes_invalidate_collection(self):
        project, _ = fixture()
        updated = deepcopy(project)
        updated["metadata"]["name"] = "New title"
        updated["version"] = "0.2.0"
        updated["probes"][0]["title"] = "Display only"
        updated["tiers"]["low"]["counts"]["ab"] = 4
        self.assertEqual(collection_contract(project), collection_contract(updated))
        updated["probes"][0]["cells"][0]["prompt"] = "A different question"
        self.assertNotEqual(collection_contract(project), collection_contract(updated))

    def test_subset_counts_and_invalid_selection(self):
        project, _ = fixture()
        jobs = collection_jobs(project, 5, 2, probe_ids=["ab"])
        self.assertEqual(len(jobs), 15)
        self.assertEqual({job["probe_id"] for job in jobs}, {"ab"})
        for selected in ([], ["missing"], ["ab", "ab"]):
            with self.assertRaises(AppError):
                collection_jobs(project, 5, 2, probe_ids=selected)



if __name__ == "__main__":
    unittest.main()
