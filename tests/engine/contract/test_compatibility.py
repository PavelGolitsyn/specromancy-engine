from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

import specromancy_engine
from specromancy_engine import config, engine, hashing
from specromancy_engine.engine import Engine
from tests.engine.contract.compatibility_support import (
    NOW, RUN_ID, CompatibilityFixture, capture_canonical, capture_diagnostics,
    capture_lifecycle, normalize_response, read_record,
)
from tests.engine.unit.test_adapters import AdapterFixture


class CompatibilityContractTests(unittest.TestCase):
    def test_public_imports(self) -> None:
        self.assertIs(specromancy_engine.EngineError, engine.EngineError)
        self.assertIs(specromancy_engine.PipelineConfigError, config.PipelineConfigError)
        exports = {
            "ExitCode", "Engine", "EngineError", "PipelineConfig", "PipelineConfigError",
            "PipelineRegistry", "PipelineRegistration", "RunCorruptionError",
            "RunNotFoundError", "RunStore", "generate_run_id", "load_pipeline",
            "load_registry", "validate_run_id",
        }
        self.assertLessEqual(exports, set(specromancy_engine.__all__))
        for name in exports:
            self.assertTrue(callable(getattr(specromancy_engine, name)), name)

    def test_canonical_pipeline_bytes_and_hashes_match_baseline(self) -> None:
        expected = read_record("canonical.json")
        self.assertEqual(capture_canonical(), expected)
        self.assertEqual(expected["absent"], expected["false"])
        self.assertNotEqual(expected["absent"]["sha256"], expected["true"]["sha256"])
        for record in expected.values():
            self.assertEqual(
                hashlib.sha256(record["canonical"].encode("utf-8")).hexdigest(),
                record["sha256"],
            )
            self.assertIn(r"\u00c9", record["canonical"])
        # The generic hash serializer deliberately has a different Unicode contract.
        self.assertEqual(hashing.canonical_json_bytes({"text": "café 日本語"}),
                         '{"text":"café 日本語"}'.encode("utf-8"))

    def test_response_envelopes_and_persisted_bytes_match_baseline(self) -> None:
        states, responses = capture_lifecycle()
        self.assertEqual(responses, read_record("responses-current.json"))
        self.assertEqual(states, read_record("states.json"))

    def test_visit_provenance_hashes_raw_skill_bytes_and_preserves_prepared_records(self) -> None:
        fixture = CompatibilityFixture()
        self.addCleanup(fixture.close)
        skill = fixture.pipeline.phase("compose").skill_path
        normalized = skill.read_bytes()
        raw = normalized.replace(b"\n", b"\r\n") + b"\r\n"
        skill.write_bytes(raw)
        action = fixture.engine.initialize("Capture raw procedure bytes.")["action"]
        expected = {"path": "workflow/skills/compose/SKILL.md",
                    "sha256": hashlib.sha256(raw).hexdigest()}
        self.assertEqual(fixture.store.load(RUN_ID)["visits"][0]["skill"], expected)
        self.assertEqual(action["skill"]["path"], expected["path"])
        self.assertEqual(action["skill"]["sha256"], expected["sha256"])
        before = fixture.snapshot()
        skill.write_bytes(normalized)
        self.assertEqual(config.load_pipeline(fixture.path, fixture.root).config_hash,
                         fixture.pipeline.config_hash)
        with self.assertRaises(engine.EngineError) as caught:
            fixture.engine.start_phase(RUN_ID, "compose")
        self.assertEqual(caught.exception.diagnostic_code, "provenance-hash-mismatch")
        self.assertEqual(fixture.snapshot(), before)

    def test_persisted_records_replay_and_recovery_is_exactly_once(self) -> None:
        states = read_record("states.json")
        responses = read_record("responses-current.json")
        for name, files in states.items():
            with self.subTest(state=name):
                fixture = CompatibilityFixture(pause=True)
                try:
                    fixture.restore(files)
                    manifest = fixture.store.load(RUN_ID)
                    self.assertEqual(manifest["schema_version"], 2)
                    expected = states["recovered"] if name == "recoverable" else files
                    self.assertEqual(fixture.snapshot(), expected)
                    fixture.store.load(RUN_ID)
                    fixture.store.read_events(RUN_ID)
                    self.assertEqual(fixture.snapshot(), expected)
                    engine = Engine(fixture.pipeline, fixture.new_store())
                    if name in {"pending", "active", "recoverable", "recovered"}:
                        self.assertEqual(
                            normalize_response(engine.start_phase(RUN_ID, "compose"), fixture.root),
                            responses["action-active"],
                        )
                        continued = states["active"] if name == "pending" else expected
                        self.assertEqual(fixture.snapshot(), continued)
                        engine.start_phase(RUN_ID, "compose")
                        self.assertEqual(fixture.snapshot(), continued)
                    elif name == "awaiting-approval":
                        self.assertEqual(normalize_response(engine.run(RUN_ID), fixture.root),
                                         responses["approval"])
                        self.assertEqual(fixture.snapshot(), files)
                        with patch("specromancy_engine.engine.utc_now", return_value=NOW):
                            result = engine.approve(RUN_ID, "compose")
                        self.assertEqual(normalize_response(result, fixture.root), responses["paused"])
                        self.assertEqual(fixture.snapshot(), states["paused"])
                    elif name == "approved":
                        self.assertEqual(manifest["approvals"][0]["outcome"], "z-next")
                        self.assertEqual(manifest["approvals"][0]["status"], "approved")
                        self.assertEqual(normalize_response(engine.approve(RUN_ID, "compose"), fixture.root),
                                         responses["paused"])
                        self.assertEqual(fixture.snapshot(), states["paused"])
                    elif name == "paused":
                        self.assertEqual(normalize_response(engine.resume(RUN_ID), fixture.root),
                                         responses["resumed"])
                        engine.start_phase(RUN_ID, "seal")
                        fixture.store.write_visit_output(RUN_ID, 2, "Sealed.\n")
                        self.assertEqual(
                            normalize_response(engine.validate(RUN_ID, "seal"), fixture.root),
                            responses["terminal"],
                        )
                        self.assertEqual(fixture.snapshot(), states["completed"])
                    elif name == "completed":
                        before = fixture.snapshot()
                        self.assertEqual(engine.run(RUN_ID)["status"]["status"], "completed")
                        self.assertEqual(fixture.snapshot(), before)
                finally:
                    fixture.close()

    def test_overtaken_approval_returns_paused_or_successor_without_advancing_it(self):
        # Intentional Stage 13 correction, separate from sequential byte replay.
        for boundary in ("paused", "pending", "active", "completed"):
            with self.subTest(boundary=boundary):
                fixture = CompatibilityFixture(pause=True)
                self.addCleanup(fixture.close)
                fixture.restore(read_record("states.json")["awaiting-approval"])
                winner = Engine(fixture.pipeline, fixture.new_store())
                original = fixture.store.decide_approval
                snapshots = []

                def overlap(*args, **kwargs):
                    with patch("specromancy_engine.engine.utc_now", return_value=NOW):
                        winner.approve(RUN_ID, "compose")
                    if boundary != "paused":
                        winner.resume(RUN_ID)
                    if boundary in ("active", "completed"):
                        winner.start_phase(RUN_ID, "seal")
                    if boundary == "completed":
                        fixture.store.write_visit_output(RUN_ID, 2, "Sealed.\n")
                        winner.validate(RUN_ID, "seal")
                    snapshots.append(fixture.snapshot())
                    return original(*args, **kwargs)

                with patch.object(fixture.store, "decide_approval", side_effect=overlap):
                    result = fixture.engine.approve(RUN_ID, "compose")
                self.assertEqual(result["message"], "approval was already recorded")
                self.assertEqual(fixture.snapshot(), snapshots[0])
                manifest = fixture.store.load(RUN_ID)
                self.assertEqual(manifest["visits"][0]["chosen_outcome"], "z-next")
                self.assertEqual(manifest["visits"][0]["transition_target"], "seal")
                self.assertEqual(manifest["visits"][1]["status"], boundary
                                 if boundary != "paused" else "pending")

    def test_exact_error_envelopes_locations_and_cli_streams(self) -> None:
        self.assertEqual(capture_diagnostics(), read_record("diagnostics.json"))

    @patch("specromancy_engine._adapters.adapter_sources.get_version", lambda: "0.1.4")
    def test_generated_adapter_bytes_and_hashes_match_baseline(self) -> None:
        fixture = AdapterFixture()
        try:
            fixture.generate()
            actual = {path: {"text": content.decode("utf-8"), "sha256": hashlib.sha256(content).hexdigest()}
                      for path, content in fixture.snapshot().items()}
            self.assertEqual(actual, read_record("adapters-generator-v5.json"))
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
