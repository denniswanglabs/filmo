#!/usr/bin/env python3
"""Unit tests for the hardened Higgsfield response parser in adapters.py.

$0 — NO real higgsfield calls. Exercises `_extract_job_id` / `_extract_asset_url`
against representative `generate create` (no --wait) and `generate get/list --json`
payloads, including the EXACT real `get` object captured live this session for the
job that the original parser choked on. Also proves the mock generation path is
unaffected (no signature/behavior regression).

Run: python3 -m unittest tests.test_adapters_higgsfield_parse
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import adapters  # noqa: E402

# The actual job id the original parser FAILED on (build-orinovate-edf804,
# scene 'cinematic-motion', seedance_2_0). Captured live via `generate list --json`.
REAL_JOB_ID = "cb5acbc2-4ff0-49a8-a785-9c933a5ebd13"
REAL_RESULT_URL = ("https://d8j0ntlcm91z4.cloudfront.net/user_X/"
                   "hf_20260619_161431_cb5acbc2-4ff0-49a8-a785-9c933a5ebd13.mp4")

# Exact shape of `higgsfield generate get <id> --json` (and each element of
# `generate list --json`), captured live, v0.1.34.
REAL_GET_OBJECT = {
    "id": REAL_JOB_ID,
    "status": "completed",
    "display_name": "Seedance 2.0",
    "job_set_type": "seedance_2_0",
    "result_url": REAL_RESULT_URL,
    "created_at": 1781885671.991108,
    "params": {"prompt": "Show a dynamic aerial view...", "duration": 7},
}


class TestExtractJobId(unittest.TestCase):
    def test_single_object_id(self):
        out = json.dumps({"id": REAL_JOB_ID, "status": "queued"})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_single_object_job_id(self):
        out = json.dumps({"job_id": REAL_JOB_ID, "status": "in_progress"})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_array_of_objects(self):
        # SKILL.md: "with --wait --json you get the final job object array."
        out = json.dumps([{"id": REAL_JOB_ID, "status": "completed"},
                          {"id": "ffffffff-0000-0000-0000-000000000000"}])
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_wrapper_jobs_list(self):
        out = json.dumps({"jobs": [{"id": REAL_JOB_ID}]})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_wrapper_job_ids_bare_strings(self):
        # "Without --wait, you get the job IDs" — plural bare-string variant.
        out = json.dumps({"job_ids": [REAL_JOB_ID]})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_wrapper_ids_bare_strings(self):
        out = json.dumps({"ids": [REAL_JOB_ID]})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_wrapper_data_objects(self):
        out = json.dumps({"data": [{"job_id": REAL_JOB_ID, "status": "queued"}]})
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_bare_uuid_string_json(self):
        # json.loads('"<uuid>"') -> a python str (old parser .get path skipped this).
        out = json.dumps(REAL_JOB_ID)
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_bare_uuid_plain_text(self):
        # Not JSON at all — plain id line.
        self.assertEqual(adapters._extract_job_id(REAL_JOB_ID + "\n"), REAL_JOB_ID)

    def test_plain_text_created_line(self):
        out = "Created job %s (seedance_2_0), status queued\n" % REAL_JOB_ID
        self.assertEqual(adapters._extract_job_id(out), REAL_JOB_ID)

    def test_real_get_object(self):
        self.assertEqual(adapters._extract_job_id(json.dumps(REAL_GET_OBJECT)), REAL_JOB_ID)

    def test_real_list_response(self):
        self.assertEqual(adapters._extract_job_id(json.dumps([REAL_GET_OBJECT])), REAL_JOB_ID)

    def test_no_id_returns_none(self):
        self.assertIsNone(adapters._extract_job_id(json.dumps({"status": "error", "msg": "bad"})))

    def test_empty_returns_none(self):
        self.assertIsNone(adapters._extract_job_id(""))
        self.assertIsNone(adapters._extract_job_id("   "))

    def test_garbage_returns_none(self):
        self.assertIsNone(adapters._extract_job_id("totally not a response"))

    def test_non_uuid_id_is_rejected(self):
        # A short/non-UUID "id" should not be mistaken for a job id.
        out = json.dumps({"id": "queued", "items": []})
        self.assertIsNone(adapters._extract_job_id(out))


class TestExtractAssetUrl(unittest.TestCase):
    def test_real_get_result_url(self):
        self.assertEqual(adapters._extract_asset_url(json.dumps(REAL_GET_OBJECT)), REAL_RESULT_URL)

    def test_array_result_url(self):
        self.assertEqual(adapters._extract_asset_url(json.dumps([REAL_GET_OBJECT])), REAL_RESULT_URL)

    def test_results_nested_url(self):
        out = json.dumps({"results": [{"url": REAL_RESULT_URL}]})
        self.assertEqual(adapters._extract_asset_url(out), REAL_RESULT_URL)

    def test_video_url_key(self):
        out = json.dumps({"video_url": REAL_RESULT_URL})
        self.assertEqual(adapters._extract_asset_url(out), REAL_RESULT_URL)

    def test_non_json_raises_with_raw(self):
        with self.assertRaises(adapters.AdapterError) as cm:
            adapters._extract_asset_url("<html>captcha</html>")
        self.assertIn("captcha", str(cm.exception))  # raw response is surfaced

    def test_no_url_raises_with_raw(self):
        with self.assertRaises(adapters.AdapterError) as cm:
            adapters._extract_asset_url(json.dumps({"status": "completed"}))
        self.assertIn("completed", str(cm.exception))


class TestPersistArtifact(unittest.TestCase):
    def test_sidecar_written_and_merged(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "01_cinematic.mp4")
            scene = {"id": "cinematic-motion"}
            raw = json.dumps({"id": REAL_JOB_ID, "status": "queued"})
            # Submit-time: job_id known, asset_url not yet.
            p = adapters._persist_higgsfield_artifact(out, scene, "seedance_2_0", raw,
                                                      job_id=REAL_JOB_ID)
            self.assertTrue(p and os.path.exists(p))
            with open(p) as f:
                rec = json.load(f)
            self.assertEqual(rec["job_id"], REAL_JOB_ID)
            self.assertEqual(rec["scene_id"], "cinematic-motion")
            self.assertIsNone(rec["asset_url"])
            self.assertIn(REAL_JOB_ID, rec["raw_response"])
            # Resolved call adds asset_url and must not erase job_id.
            adapters._persist_higgsfield_artifact(out, scene, "seedance_2_0",
                                                  json.dumps(REAL_GET_OBJECT),
                                                  job_id=REAL_JOB_ID, asset_url=REAL_RESULT_URL)
            with open(p) as f:
                rec2 = json.load(f)
            self.assertEqual(rec2["job_id"], REAL_JOB_ID)
            self.assertEqual(rec2["asset_url"], REAL_RESULT_URL)


class TestMockPathUnaffected(unittest.TestCase):
    """The mock path must stay $0, real-file-producing, and signature-stable."""

    def test_generate_cinematic_mock_video(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "clip.mp4")
            scene = {"id": "s1", "type": "cinematic", "model": "seedance_2_0", "duration_s": 2}
            res = adapters.generate_cinematic(scene, out, "mock")
            self.assertFalse(res["real"])
            self.assertEqual(res["output_path"], out)
            self.assertTrue(os.path.exists(out) and os.path.getsize(out) > 1000)
            # Mock must NOT touch higgsfield / write a sidecar.
            self.assertFalse(os.path.exists(out.rsplit(".", 1)[0] + ".higgsfield.json"))

    def test_generate_cinematic_mock_still(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "still.mp4")
            scene = {"id": "s2", "type": "cinematic", "model": "gpt_image_2", "duration_s": 2}
            res = adapters.generate_cinematic(scene, out, "mock")
            self.assertFalse(res["real"])
            self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
