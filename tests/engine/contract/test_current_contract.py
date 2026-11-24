from __future__ import annotations

import hashlib
import json
from importlib.resources import files
import unittest
from unittest.mock import patch

import specromancy_engine
from specromancy_engine import config, engine, hashing, run_store
from specromancy_engine._config.config_loader import SUPPORTED_SCHEMA_VERSION
from specromancy_engine.actions import ACTION_PACKET_SCHEMA_VERSION
from specromancy_engine.adapters import ADAPTER_SCHEMA_VERSION, GENERATOR_VERSION, MANIFEST_PATH
from specromancy_engine.contracts import RESPONSE_SCHEMA_VERSION
from specromancy_engine.engine import Engine
from specromancy_engine.registry import load_registry
from specromancy_engine.run_store import EVENT_SCHEMA_VERSION, RUN_SCHEMA_VERSION
from specromancy_engine.status import STATUS_SCHEMA_VERSION
from tests.engine.contract.current_contract_support import (
    NOW, RUN_ID, CurrentContractFixture, capture_canonical, capture_diagnostics,
    capture_lifecycle, normalize_response, read_record,
)
from tests.engine.unit.test_adapters import AdapterFixture


class CurrentContractTests(unittest.TestCase):
    def test_public_imports(self) -> None:
        self.assertIs(specromancy_engine.EngineError, engine.EngineError)
        self.assertIs(specromancy_engine.PipelineConfigError, config.PipelineConfigError)
        self.assertIs(specromancy_engine.RunCorruptionError, run_store.RunCorruptionError)
        self.assertIs(specromancy_engine.RunNotFoundError, run_store.RunNotFoundError)
        exports = {
            "ExitCode", "Engine", "EngineError", "PipelineConfig", "PipelineConfigError",
            "PipelineRegistry", "PipelineRegistration", "RunCorruptionError",
            "RunNotFoundError", "RunStore", "generate_run_id", "load_pipeline",
            "load_registry", "validate_run_id",
        }
        self.assertLessEqual(exports, set(specromancy_engine.__all__))
        for name in exports:
            self.assertTrue(callable(getattr(specromancy_engine, name)), name)

    def test_packaged_schema_declarations_agree_with_current_formats(self):
        fixture = CurrentContractFixture()
        self.addCleanup(fixture.close)
        registry = json.loads(load_registry(fixture.root).canonical_json)
        for name, version in (
            ("pipeline", SUPPORTED_SCHEMA_VERSION), ("pipelines", registry["schema_version"]),
            ("run", RUN_SCHEMA_VERSION), ("event", EVENT_SCHEMA_VERSION),
        ):
            with self.subTest(schema=name):
                path = files("specromancy_engine").joinpath("schemas", f"{name}.schema.json")
                schema = json.loads(path.read_bytes())
                self.assertEqual(schema["properties"]["schema_version"]["const"], version)
        self.assertEqual(fixture.pipeline.schema_version, SUPPORTED_SCHEMA_VERSION)
        self.assertEqual(registry, {
            "schema_version": 1,
            "pipelines": [{"id": "compatibility", "path": "pipelines/compatibility.toml"}],
        })

    def test_canonical_pipeline_bytes_and_hashes_match_current_records(self) -> None:
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

    def test_response_envelopes_and_persisted_bytes_match_current_records(self) -> None:
        states, responses = capture_lifecycle()
        self.assertEqual(responses, read_record("responses.json"))
        self.assertEqual(states, read_record("states.json"))
        for response in responses.values():
            self.assertEqual(response["schema_version"], RESPONSE_SCHEMA_VERSION)
            if "action" in response:
                self.assertEqual(response["action"]["schema_version"], ACTION_PACKET_SCHEMA_VERSION)
            if "status" in response:
                self.assertEqual(response["status"]["schema_version"], STATUS_SCHEMA_VERSION)
        for snapshot in states.values():
            self.assertEqual(json.loads(snapshot["run.json"])["schema_version"], RUN_SCHEMA_VERSION)
            for line in snapshot["events.jsonl"].splitlines():
                self.assertEqual(json.loads(line)["schema_version"], EVENT_SCHEMA_VERSION)

    def test_visit_provenance_hashes_raw_skill_bytes_and_preserves_prepared_records(self) -> None:
        fixture = CurrentContractFixture()
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
        responses = read_record("responses.json")
        for name, files in states.items():
            with self.subTest(state=name):
                fixture = CurrentContractFixture(pause=True)
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
                fixture = CurrentContractFixture(pause=True)
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
    def test_generated_adapter_bytes_and_hashes_match_current_records(self) -> None:
        fixture = AdapterFixture()
        try:
            fixture.generate()
            actual = {path: {"text": content.decode("utf-8"), "sha256": hashlib.sha256(content).hexdigest()}
                      for path, content in fixture.snapshot().items()}
            self.assertEqual(actual, read_record("ownership.json"))
            manifest = json.loads(actual[MANIFEST_PATH]["text"])
            self.assertEqual(manifest["schema_version"], ADAPTER_SCHEMA_VERSION)
            self.assertEqual(manifest["generator"]["version"], GENERATOR_VERSION)
            selection = next(item for item in manifest["canonical_source"]["inputs"]
                             if item["path"] == "workflow/adapters.toml")
            canonical = b'{"harnesses":["claude","codex","copilot","hermes","opencode"],"schema_version":1}'
            self.assertEqual(selection["sha256"], hashlib.sha256(canonical).hexdigest())
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
