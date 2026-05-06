from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class PolicyLabTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import polars  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest("polars is not installed in this environment") from exc

    def test_baseline_execution_runs(self) -> None:
        from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.result_repository import ResultRepository
        from policy_lab.storage.scenario_repository import ScenarioRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        orchestrator = ScenarioOrchestrator(
            study_repository=study_repository,
            feature_repository=FeatureRepository(),
            scenario_repository=ScenarioRepository(),
            result_repository=ResultRepository(),
        )
        study = study_repository.load("demo_lending")
        baseline_bundle = orchestrator.run_baseline(study)

        self.assertEqual(baseline_bundle.result.study_id, "demo_lending")
        self.assertGreater(baseline_bundle.result.metrics.records_evaluated, 0)
        self.assertGreaterEqual(baseline_bundle.result.metrics.approval_rate, 0.0)

    def test_manual_override_changes_policy(self) -> None:
        from policy_lab.engine.policy_parser import PolicyBuilder
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        predicate = study.manifest.baseline_policy.rules[0].blocks[0].predicates[0]
        handle = PolicyBuilder.predicate_handle(0, 0, 0, predicate)
        candidate = PolicyBuilder.apply_threshold_overrides(
            study.manifest.baseline_policy,
            {handle: 600},
        )
        original_value = study.manifest.baseline_policy.rules[0].blocks[0].predicates[0].value

        self.assertEqual(candidate.rules[0].blocks[0].predicates[0].value, 600)
        self.assertEqual(
            study.manifest.baseline_policy.rules[0].blocks[0].predicates[0].value,
            original_value,
        )

    def test_matrix_selection_builds_decision_rule(self) -> None:
        from policy_lab.apps.simulator_app.services import build_matrix_rule
        from policy_lab.domain import LogicalOperator, Operator
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)

        rule = build_matrix_rule(
            snapshot=snapshot,
            row_variable="score1",
            column_variable="z1",
            selected_cells=[{"row": "[300, 520)", "column": "1"}],
            decision="approve",
            name="Teste matriz",
            existing_rule_ids=set(),
        )

        self.assertEqual(rule.decision, "approve")
        self.assertEqual(rule.block_combiner, LogicalOperator.ANY)
        self.assertEqual(rule.blocks[0].logical_operator, LogicalOperator.ALL)
        self.assertEqual(rule.blocks[0].predicates[0].operator, Operator.GTE)
        self.assertEqual(rule.blocks[0].predicates[1].operator, Operator.LT)
        self.assertEqual(rule.blocks[0].predicates[2].field, "z1")

    def test_matrix_rule_set_builds_one_rule_per_decision(self) -> None:
        from policy_lab.apps.simulator_app.services import build_matrix_rule_set
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)

        rules = build_matrix_rule_set(
            snapshot=snapshot,
            row_variable="score1",
            column_variable="z1",
            cell_decisions=[
                {"row": "[300, 520)", "column": "1", "decision": "approve"},
                {"row": "[520, 760]", "column": "1", "decision": "reject"},
            ],
            name="Teste multicategoria",
            existing_rule_ids=set(),
            decision_order=["approve", "reject"],
        )

        self.assertEqual(len(rules), 2)
        self.assertEqual([rule.decision for rule in rules], ["approve", "reject"])
        self.assertEqual(rules[0].name, "Teste multicategoria :: approve")
        self.assertEqual(rules[1].name, "Teste multicategoria :: reject")

    def test_prepare_matrix_dimension_assigns_extremes_to_outer_bins(self) -> None:
        import polars as pl

        from policy_lab.apps.simulator_app.services import prepare_matrix_dimension

        snapshot = pl.DataFrame({"score": [65.0, 75.0, 95.0]})
        labeled = snapshot.select(
            prepare_matrix_dimension(
                snapshot,
                "score",
                {"type": "binned", "boundaries": [70.0, 90.0], "labels": ["[70, 90]"]},
            ).alias("bucket")
        )

        self.assertEqual(labeled.get_column("bucket").to_list(), ["[70, 90]"] * 3)

    def test_extract_anchor_population_for_second_rule_uses_prefix_before_host_rule(self) -> None:
        from policy_lab.apps.simulator_app.runtime import policy_executor
        from policy_lab.apps.simulator_app.services import (
            extract_anchor_population_for_predicate,
            ui_predicate_handle,
        )
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        policy = study.manifest.baseline_policy
        target_rule = policy.rules[1]
        target_predicate = target_rule.blocks[0].predicates[0]
        handle = ui_predicate_handle(
            target_rule.rule_id,
            0,
            0,
            target_predicate.field,
            target_predicate.operator.value,
        )

        anchored = extract_anchor_population_for_predicate(snapshot, policy, handle)
        expected = snapshot.filter(~policy_executor._rule_expression(policy.rules[0]))

        self.assertEqual(anchored.height, expected.height)

    def test_created_rule_repository_roundtrip(self) -> None:
        from policy_lab.storage.created_rule_repository import CreatedRuleRepository
        from policy_lab.storage.studies_repository import StudyRepository

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            study_root = root / "demo_lending"
            study_root.mkdir(parents=True, exist_ok=True)

            source_study_root = Path("runtime/studies/demo_lending")
            (study_root / "study.json").write_text(
                (source_study_root / "study.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (study_root / "study_snapshot.csv").write_text(
                (source_study_root / "study_snapshot.csv").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            study = StudyRepository(studies_root=root).load("demo_lending")
            repository = CreatedRuleRepository()
            entries = [
                {
                    "rule_id": "matrix-test",
                    "rule_name": "Matrix test",
                    "rule": {
                        "rule_id": "matrix-test",
                        "name": "Matrix test",
                        "decision": "approve",
                        "block_combiner": "any",
                        "blocks": [],
                        "description": "Created in test.",
                    },
                    "source_type": "matrix_composition",
                    "row_variable": "score1",
                    "column_variable": "z1",
                    "eligible_filters": {
                        "months": [],
                        "segment_field": None,
                        "segment_values": [],
                        "matrix_filters": [],
                    },
                    "selected_cells": [{"row": "[300, 520)", "column": "1"}],
                    "decision": "approve",
                    "version": 1,
                    "author": "local_user",
                    "created_at": "2026-04-23T00:00:00+00:00",
                    "updated_at": "2026-04-23T00:00:00+00:00",
                }
            ]
            repository.save(study, entries)

            loaded = repository.load(study)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["source_type"], "matrix_composition")
            self.assertEqual(loaded[0]["rule"]["name"], "Matrix test")

    def test_manual_config_repository_roundtrip(self) -> None:
        from policy_lab.storage.manual_config_repository import ManualConfigRepository
        from policy_lab.storage.studies_repository import StudyRepository

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            study_root = root / "demo_lending"
            study_root.mkdir(parents=True, exist_ok=True)

            source_study_root = Path("runtime/studies/demo_lending")
            (study_root / "study.json").write_text(
                (source_study_root / "study.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (study_root / "study_snapshot.csv").write_text(
                (source_study_root / "study_snapshot.csv").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            study = StudyRepository(studies_root=root).load("demo_lending")
            repository = ManualConfigRepository()
            entries = [
                {
                    "config_id": "workspace-manual",
                    "name": "Workspace manual",
                    "workspace_id": "default",
                    "author": "local_user",
                    "created_at": "2026-05-04T00:00:00+00:00",
                    "updated_at": "2026-05-04T00:00:00+00:00",
                    "manual_ui_state": {"study_id": study.study_id},
                    "rule_state": {"study_id": study.study_id},
                    "cutoff_override": None,
                }
            ]
            repository.save(study, entries)

            loaded = repository.load(study)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["config_id"], "workspace-manual")

    def test_build_candidate_policy_uses_composite_custom_entry(self) -> None:
        from policy_lab.apps.simulator_app.services import (
            build_candidate_policy,
            build_matrix_rule_set,
            normalize_rule_state,
        )
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        rules = build_matrix_rule_set(
            snapshot=snapshot,
            row_variable="score1",
            column_variable="z1",
            cell_decisions=[
                {"row": "[300, 520)", "column": "1", "decision": "approve"},
                {"row": "[520, 760]", "column": "1", "decision": "review"},
            ],
            name="Teste multicategoria",
            existing_rule_ids=set(),
            decision_order=["approve", "review"],
        )
        custom_entries = [
            {
                "rule_id": "matrix-asset-teste",
                "rule_name": "Teste multicategoria",
                "rules": [rule.to_dict() for rule in rules],
            }
        ]
        state = normalize_rule_state(
            study,
            {
                "study_id": study.study_id,
                "used_rule_ids": [],
                "used_custom_rule_ids": ["matrix-asset-teste"],
                "selected_feature_ids": [],
            },
            custom_rule_entries=custom_entries,
        )

        policy = build_candidate_policy(
            study,
            rule_state=state,
            predicate_ids=[],
            predicate_values=[],
            custom_rule_entries=custom_entries,
        )

        self.assertEqual([rule.decision for rule in policy.rules], ["approve", "review"])

    def test_build_candidate_policy_uses_predicate_editor_state(self) -> None:
        from policy_lab.apps.simulator_app.services import (
            build_candidate_policy,
            default_predicate_editor_state,
            normalize_rule_state,
            ui_predicate_handle,
        )
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        state = normalize_rule_state(study, None)
        predicate = study.manifest.baseline_policy.rules[0].blocks[0].predicates[0]
        handle = ui_predicate_handle(
            study.manifest.baseline_policy.rules[0].rule_id,
            0,
            0,
            predicate.field,
            predicate.operator.value,
        )
        editor_state = default_predicate_editor_state(study)
        editor_state["values"][handle] = 777

        policy = build_candidate_policy(
            study,
            rule_state=state,
            predicate_editor_state=editor_state,
        )

        self.assertEqual(policy.rules[0].blocks[0].predicates[0].value, 777)

    def test_prepare_custom_rule_matrix_edit_accepts_composite_entry(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        custom_rule_state = {
            "study_id": study.study_id,
            "entries": [
                {
                    "rule_id": "matrix-asset-teste-3",
                    "rule_name": "Teste 3",
                    "rules": [
                        {
                            "rule_id": "matrix-teste-3-approve",
                            "name": "Teste 3 :: approve",
                            "decision": "approve",
                            "block_combiner": "any",
                            "blocks": [],
                        },
                        {
                            "rule_id": "matrix-teste-3-reject",
                            "name": "Teste 3 :: reject",
                            "decision": "reject",
                            "block_combiner": "any",
                            "blocks": [],
                        },
                    ],
                    "eligible_filters": {
                        "months": [],
                        "segment_field": None,
                        "segment_values": [],
                        "matrix_filters": [],
                    },
                }
            ],
        }

        original_triggered_id = callback_handlers.current_triggered_id
        original_ctx = callback_handlers.ctx
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "edit-custom-rule",
                "rule_id": "matrix-asset-teste-3",
            }

            class DummyContext:
                triggered = [{"value": 1}]

            callback_handlers.ctx = DummyContext()
            pending_state, message, displayed = (
                callback_handlers.prepare_custom_rule_matrix_edit(
                    [1],
                    study.study_id,
                    custom_rule_state,
                    None,
                    None,
                )
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id
            callback_handlers.ctx = original_ctx

        self.assertTrue(displayed)
        self.assertEqual(pending_state["entry"]["rule_id"], "matrix-asset-teste-3")
        self.assertIn("Teste 3", message)

    def test_prepare_custom_rule_matrix_edit_blocks_active_rule(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        custom_rule_state = {
            "study_id": study.study_id,
            "entries": [
                {
                    "rule_id": "matrix-asset-teste-3",
                    "rule_name": "Teste 3",
                    "rules": [
                        {
                            "rule_id": "matrix-teste-3-approve",
                            "name": "Teste 3 :: approve",
                            "decision": "approve",
                            "block_combiner": "any",
                            "blocks": [],
                        }
                    ],
                    "eligible_filters": {
                        "months": [],
                        "segment_field": None,
                        "segment_values": [],
                        "matrix_filters": [],
                    },
                }
            ],
        }
        rule_state = {
            "study_id": study.study_id,
            "used_rule_ids": [],
            "used_custom_rule_ids": ["matrix-asset-teste-3"],
            "selected_feature_ids": [],
        }

        original_triggered_id = callback_handlers.current_triggered_id
        original_ctx = callback_handlers.ctx
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "edit-custom-rule",
                "rule_id": "matrix-asset-teste-3",
            }

            class DummyContext:
                triggered = [{"value": 1}]

            callback_handlers.ctx = DummyContext()
            pending_state, message, displayed = (
                callback_handlers.prepare_custom_rule_matrix_edit(
                    [1],
                    study.study_id,
                    custom_rule_state,
                    None,
                    rule_state,
                )
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id
            callback_handlers.ctx = original_ctx

        self.assertIsNone(pending_state)
        self.assertTrue(displayed)
        self.assertIn("esta ativa", message)
        self.assertIn("Simular novamente", message)

    def test_select_cutoff_target_returns_handle(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.apps.simulator_app.services import ui_predicate_handle
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        predicate = study.manifest.baseline_policy.rules[0].blocks[0].predicates[0]
        handle_id = ui_predicate_handle(
            study.manifest.baseline_policy.rules[0].rule_id,
            0,
            0,
            predicate.field,
            predicate.operator.value,
        )
        original_triggered_id = callback_handlers.current_triggered_id
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "select-cutoff-handle",
                "handle": handle_id,
            }
            handle, message = callback_handlers.select_cutoff_target([1], study.study_id)
        finally:
            callback_handlers.current_triggered_id = original_triggered_id

        self.assertEqual(handle, handle_id)
        self.assertIn("Predicado-alvo selecionado", message)

    def test_update_asset_editor_state_opens_rule_asset(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        original_triggered_id = callback_handlers.current_triggered_id
        original_ctx = callback_handlers.ctx
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "open-rule-editor",
                "rule_id": "approve-resilient-applicants",
            }

            class DummyContext:
                triggered = [{"value": 1}]

            callback_handlers.ctx = DummyContext()
            state = callback_handlers.update_asset_editor_state(
                "demo_lending",
                [],
                [],
                [],
                0,
                None,
                None,
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id
            callback_handlers.ctx = original_ctx

        self.assertTrue(state["open"])
        self.assertEqual(state["asset_type"], "rule")
        self.assertEqual(state["rule_id"], "approve-resilient-applicants")

    def test_update_asset_editor_state_ignores_zero_click_open_event(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        original_triggered_id = callback_handlers.current_triggered_id
        original_ctx = callback_handlers.ctx
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "open-rule-editor",
                "rule_id": "approve-resilient-applicants",
            }

            class DummyContext:
                triggered = [{"value": 0}]

            callback_handlers.ctx = DummyContext()
            state = callback_handlers.update_asset_editor_state(
                "demo_lending",
                [],
                [],
                [],
                0,
                None,
                None,
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id
            callback_handlers.ctx = original_ctx

        self.assertFalse(state["open"])

    def test_update_asset_editor_state_opens_variant_asset(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        original_triggered_id = callback_handlers.current_triggered_id
        original_ctx = callback_handlers.ctx
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "open-custom-editor",
                "rule_id": "variant-approve-prime-2",
            }

            class DummyContext:
                triggered = [{"value": 1}]

            callback_handlers.ctx = DummyContext()
            state = callback_handlers.update_asset_editor_state(
                "demo_lending",
                [],
                [],
                [1],
                0,
                None,
                {
                    "study_id": "demo_lending",
                    "entries": [
                        {
                            "rule_id": "variant-approve-prime-2",
                            "source_type": "baseline_rule_variant",
                            "origin_rule_id": "approve-prime",
                            "rule": {
                                "rule_id": "rule-approve-prime-2",
                                "name": "Approve resilient applicants (2)",
                                "decision": "approve",
                                "block_combiner": "any",
                                "blocks": [],
                            },
                        }
                    ],
                },
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id
            callback_handlers.ctx = original_ctx

        self.assertTrue(state["open"])
        self.assertEqual(state["asset_type"], "variant_rule")
        self.assertEqual(state["rule_id"], "variant-approve-prime-2")

    def test_render_asset_editor_rule_shows_cutoff_panel(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        (
            drawer_class,
            body,
            status,
            save_disabled,
            save_style,
            title,
            cutoff_style,
        ) = (
            callback_handlers.render_asset_editor(
                "demo_lending",
                {
                    "study_id": "demo_lending",
                    "open": True,
                    "opened_at": "2026-05-04T00:00:00+00:00",
                    "asset_type": "rule",
                    "rule_id": "approve-prime",
                },
                None,
                None,
                None,
            )
        )

        self.assertIn("open", drawer_class)
        self.assertFalse(save_disabled)
        self.assertEqual(save_style.get("display"), "inline-flex")
        self.assertEqual(title, "Editor de regra")
        self.assertEqual(cutoff_style.get("display"), "grid")
        self.assertEqual(status, "")
        self.assertTrue(
            any("Approve resilient applicants" in str(child) for child in body.children)
        )

    def test_save_asset_editor_values_creates_baseline_variant(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.apps.simulator_app.services import (
            custom_rule_entries_from_store,
            default_predicate_editor_state,
            normalize_rule_state,
            ui_predicate_handle,
        )
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        original_load = callback_handlers.created_rule_repository.load
        original_save = callback_handlers.created_rule_repository.save
        persisted_entries: list[dict[str, object]] = []
        predicate = study.manifest.baseline_policy.rules[0].blocks[0].predicates[0]
        handle = ui_predicate_handle(
            study.manifest.baseline_policy.rules[0].rule_id,
            0,
            0,
            predicate.field,
            predicate.operator.value,
        )
        editor_state = default_predicate_editor_state(study)
        rule_state = normalize_rule_state(study, None)
        try:
            callback_handlers.created_rule_repository.load = lambda _study: list(persisted_entries)
            callback_handlers.created_rule_repository.save = lambda _study, entries: (
                persisted_entries.clear() or persisted_entries.extend(entries)
            )
            (
                updated_editor_state,
                custom_store,
                updated_rule_state,
                updated_asset_editor_state,
                status,
            ) = (
                callback_handlers.save_asset_editor_values(
                    1,
                    study.study_id,
                    {
                        "study_id": study.study_id,
                        "open": True,
                        "asset_type": "rule",
                        "rule_id": study.manifest.baseline_policy.rules[0].rule_id,
                    },
                    [{"handle": handle}],
                    [float(predicate.value) + 10],
                    editor_state,
                    {"study_id": study.study_id, "entries": []},
                    rule_state,
                    "Approve resilient applicants (2)",
                    ["replace"],
                )
            )
        finally:
            callback_handlers.created_rule_repository.load = original_load
            callback_handlers.created_rule_repository.save = original_save

        entries = custom_rule_entries_from_store(study, custom_store)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source_type"], "baseline_rule_variant")
        self.assertEqual(entries[0]["origin_rule_id"], "approve-prime")
        self.assertIn("criada com sucesso", status)
        self.assertIn("substituiu", status)
        self.assertIn("custom:", updated_rule_state["used_asset_ids"][0])
        self.assertFalse(updated_asset_editor_state["open"])
        self.assertEqual(
            updated_editor_state["values"][handle],
            predicate.value,
        )

    def test_update_rule_state_add_variant_replaces_origin_baseline_token(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.apps.simulator_app.services import normalize_rule_state
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        custom_rule_state = {
            "study_id": study.study_id,
            "entries": [
                {
                    "rule_id": "variant-approve-prime-2",
                    "rule_name": "Approve resilient applicants (2)",
                    "source_type": "baseline_rule_variant",
                    "origin_rule_id": "approve-prime",
                    "origin_rule_name": "Approve resilient applicants",
                    "rule": {
                        "rule_id": "rule-approve-prime-2",
                        "name": "Approve resilient applicants (2)",
                        "decision": "approve",
                        "block_combiner": "any",
                        "blocks": [],
                    },
                }
            ],
        }
        rule_state = normalize_rule_state(
            study,
            None,
            custom_rule_entries=custom_rule_state["entries"],
        )

        original_triggered_id = callback_handlers.current_triggered_id
        try:
            callback_handlers.current_triggered_id = lambda: {
                "type": "add-custom-rule",
                "rule_id": "variant-approve-prime-2",
            }
            updated = callback_handlers.update_rule_state(
                study.study_id,
                [],
                [],
                [],
                [],
                [1],
                [],
                [],
                [],
                custom_rule_state,
                rule_state,
            )
        finally:
            callback_handlers.current_triggered_id = original_triggered_id

        self.assertIn("custom:variant-approve-prime-2", updated["used_asset_ids"])
        self.assertNotIn("baseline:approve-prime", updated["used_asset_ids"])

    def test_save_manual_config_creates_derivation_when_name_changes(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        original_load = callback_handlers.manual_config_repository.load
        original_save = callback_handlers.manual_config_repository.save
        saved_entries = []
        try:
            callback_handlers.manual_config_repository.load = lambda study: [
                {
                    "config_id": "workspace-a",
                    "name": "Workspace A",
                    "workspace_id": "default",
                    "author": "local_user",
                    "created_at": "2026-05-04T00:00:00+00:00",
                    "updated_at": "2026-05-04T00:00:00+00:00",
                    "manual_ui_state": {"study_id": study.study_id},
                    "rule_state": {"study_id": study.study_id},
                    "cutoff_override": None,
                }
            ]
            callback_handlers.manual_config_repository.save = (
                lambda study, entries: saved_entries.extend(entries)
            )
            store, current, status = callback_handlers.save_manual_config(
                1,
                "demo_lending",
                "Workspace B",
                {
                    "study_id": "demo_lending",
                    "config_id": "workspace-a",
                    "name": "Workspace A",
                    "workspace_id": "default",
                    "author": "local_user",
                },
                {
                    "study_id": "demo_lending",
                    "filters": {"months": [], "segment_field": None, "segment_values": []},
                    "cutoff": {"objective": "approval", "handle": None, "target_value": 80.0},
                },
                None,
                {"study_id": "demo_lending", "entries": []},
                None,
                None,
                "approval",
                80.0,
            )
        finally:
            callback_handlers.manual_config_repository.load = original_load
            callback_handlers.manual_config_repository.save = original_save

        self.assertEqual(current["name"], "Workspace B")
        self.assertEqual(len(store["entries"]), 2)
        self.assertIn("derivado", status)

    def test_save_manual_config_updates_loaded_config_when_name_matches(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers

        original_load = callback_handlers.manual_config_repository.load
        original_save = callback_handlers.manual_config_repository.save
        saved_entries = []
        try:
            callback_handlers.manual_config_repository.load = lambda study: [
                {
                    "config_id": "workspace-a",
                    "name": "Workspace A",
                    "workspace_id": "default",
                    "author": "local_user",
                    "created_at": "2026-05-04T00:00:00+00:00",
                    "updated_at": "2026-05-04T00:00:00+00:00",
                    "manual_ui_state": {"study_id": study.study_id},
                    "rule_state": {"study_id": study.study_id},
                    "cutoff_override": None,
                }
            ]
            callback_handlers.manual_config_repository.save = (
                lambda study, entries: saved_entries.extend(entries)
            )
            store, current, status = callback_handlers.save_manual_config(
                1,
                "demo_lending",
                "Workspace A",
                {
                    "study_id": "demo_lending",
                    "config_id": "workspace-a",
                    "name": "Workspace A",
                    "workspace_id": "default",
                    "author": "local_user",
                },
                {
                    "study_id": "demo_lending",
                    "filters": {"months": [], "segment_field": None, "segment_values": []},
                    "cutoff": {"objective": "approval", "handle": None, "target_value": 80.0},
                },
                None,
                {"study_id": "demo_lending", "entries": []},
                None,
                None,
                "approval",
                80.0,
            )
        finally:
            callback_handlers.manual_config_repository.load = original_load
            callback_handlers.manual_config_repository.save = original_save

        self.assertEqual(current["config_id"], "workspace-a")
        self.assertEqual(len(store["entries"]), 1)
        self.assertIn("atualizado", status)

    def test_apply_rule_library_drag_drop_moves_asset_between_panels(self) -> None:
        import json

        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.apps.simulator_app.services import normalize_rule_state
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        rule_state = normalize_rule_state(study, None)
        moved_asset = f"baseline:{study.manifest.baseline_policy.rules[0].rule_id}"

        updated = callback_handlers.apply_rule_library_drag_drop(
            json.dumps(
                {
                    "asset_id": moved_asset,
                    "target_panel": "available",
                    "placement": "append",
                }
            ),
            study.study_id,
            rule_state,
            {"study_id": study.study_id, "entries": []},
        )

        self.assertNotIn(moved_asset, updated["used_asset_ids"])

    def test_apply_rule_library_drag_drop_reorders_used_assets(self) -> None:
        import json

        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.apps.simulator_app.services import normalize_rule_state
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        baseline_rules = study.manifest.baseline_policy.rules
        first_asset = f"baseline:{baseline_rules[0].rule_id}"
        second_asset = f"baseline:{baseline_rules[1].rule_id}"
        rule_state = normalize_rule_state(study, None)

        updated = callback_handlers.apply_rule_library_drag_drop(
            json.dumps(
                {
                    "asset_id": second_asset,
                    "target_panel": "used",
                    "target_asset_id": first_asset,
                    "placement": "before",
                }
            ),
            study.study_id,
            rule_state,
            {"study_id": study.study_id, "entries": []},
        )

        self.assertEqual(updated["used_asset_ids"][0], second_asset)
        self.assertEqual(updated["used_asset_ids"][1], first_asset)

    def test_build_candidate_policy_respects_feature_asset_order(self) -> None:
        from policy_lab.apps.simulator_app.services import (
            build_candidate_policy,
            feature_asset_id,
            normalize_rule_state,
        )
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        features = FeatureRepository().load(study)
        feature_id = features[0].feature_id
        baseline_rule_id = study.manifest.baseline_policy.rules[0].rule_id
        state = normalize_rule_state(
            study,
            {
                "study_id": study.study_id,
                "used_asset_ids": [
                    feature_asset_id(feature_id),
                    f"baseline:{baseline_rule_id}",
                ],
                "selected_feature_ids": [feature_id],
            },
        )

        policy = build_candidate_policy(study, rule_state=state)

        self.assertEqual(policy.rules[0].rule_id, f"derived-{feature_id}")
        self.assertEqual(policy.rules[1].rule_id, baseline_rule_id)

    def test_matrix_edit_restores_full_scope_filters_visually(self) -> None:
        from policy_lab.apps.simulator_app.callback_handlers import (
            available_month_values,
            resolved_manual_filters_for_matrix_edit,
        )
        from policy_lab.apps.simulator_app.services import available_segment_columns
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        snapshot = StudyRepository().load_snapshot(study)
        segment_field = available_segment_columns(snapshot, study)[0]
        segment_value = str(snapshot.get_column(segment_field).drop_nulls().unique().to_list()[0])
        manual_state = {
            "study_id": "demo_lending",
            "filters": {
                "months": ["202401"],
                "segment_field": segment_field,
                "segment_values": [segment_value],
            },
        }
        resolved = resolved_manual_filters_for_matrix_edit(
            study,
            {
                "months": [],
                "segment_field": None,
                "segment_values": [],
                "matrix_filters": [],
            },
            manual_state,
        )
        filters, alert_message = resolved

        self.assertEqual(filters["months"], available_month_values(study))
        self.assertEqual(filters["segment_field"], segment_field)
        self.assertGreater(len(filters["segment_values"]), 0)
        self.assertIsNone(alert_message)

    def test_matrix_edit_uses_manual_filters_when_saved_filters_are_invalid(self) -> None:
        from policy_lab.apps.simulator_app.callback_handlers import (
            current_manual_filters,
            resolved_manual_filters_for_matrix_edit,
        )
        from policy_lab.apps.simulator_app.services import available_segment_columns
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        snapshot = StudyRepository().load_snapshot(study)
        segment_field = available_segment_columns(snapshot, study)[0]
        manual_state = {
            "study_id": "demo_lending",
            "filters": {
                "months": ["209901"],
                "segment_field": segment_field,
                "segment_values": ["categoria-inexistente"],
            },
        }

        resolved, alert_message = resolved_manual_filters_for_matrix_edit(
            study,
            {
                "months": ["209901"],
                "segment_field": segment_field,
                "segment_values": ["categoria-inexistente"],
                "matrix_filters": [],
            },
            manual_state,
        )

        self.assertEqual(resolved, current_manual_filters(study, manual_state))
        self.assertIsNotNone(alert_message)
        self.assertIn("snapshot diferente", alert_message)

    def test_matrix_eligible_snapshot_resolves_derived_features(self) -> None:
        from policy_lab.apps.simulator_app.callback_handlers import matrix_eligible_snapshot
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        snapshot = matrix_eligible_snapshot(
            study,
            months=None,
            segment_field=None,
            segment_values=None,
            rule_state=None,
            custom_rule_state=None,
            cutoff_override=None,
            cutoff_handle=None,
            cutoff_objective=None,
            cutoff_value=None,
            predicate_editor_state=None,
            filter_variables=[],
            filter_operators=[],
            filter_values=[],
        )

        self.assertIn("thin_file_watch_flag", snapshot.columns)

    def test_snapshot_schema_validation_raises_for_missing_column(self) -> None:
        import json

        from policy_lab.storage.studies_repository import StudyRepository

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            study_root = root / "broken_study"
            study_root.mkdir(parents=True, exist_ok=True)

            manifest = {
                "study_id": "broken_study",
                "name": "Broken Study",
                "description": "Study used to validate snapshot schema checks.",
                "workspace": {"workspace_id": "lab", "name": "Lab", "description": ""},
                "policy_family": {
                    "policy_family_id": "family",
                    "name": "Family",
                    "description": "",
                },
                "baseline_version": "v1",
                "snapshot": {
                    "file_name": "study_snapshot.csv",
                    "format": "csv",
                    "entity_id_column": "entity_id",
                    "historical_decision_column": "historical_decision",
                    "outcome_columns": ["profit_value"],
                    "metadata_columns": [],
                },
                "baseline_policy": {
                    "policy_id": "baseline",
                    "name": "Baseline",
                    "version": "v1",
                    "decision_column": "simulated_decision",
                    "default_decision": "reject",
                    "rules": [
                        {
                            "rule_id": "approve-score",
                            "name": "Approve score",
                            "decision": "approve",
                            "blocks": [
                                {
                                    "block_id": "b1",
                                    "name": "b1",
                                    "logical_operator": "all",
                                    "predicates": [
                                        {"field": "score1", "operator": ">", "value": 300}
                                    ],
                                }
                            ],
                        }
                    ],
                },
            }
            (study_root / "study.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (study_root / "study_snapshot.csv").write_text(
                "entity_id,historical_decision\n1,approve\n",
                encoding="utf-8",
            )

            repository = StudyRepository(studies_root=root)
            study = repository.load("broken_study")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                repository.load_snapshot(study)

    def test_policy_optimizer_variable_search_respects_bounds_and_grid(self) -> None:
        import polars as pl

        from policy_lab.engine.optimizer import PolicyOptimizer

        optimizer = PolicyOptimizer()
        candidates = optimizer._candidate_thresholds(
            field_name="score1",
            column=pl.Series("score1", [100, 200, 300, 400, 500, 600]),
            baseline_value=340,
            search_defaults={
                "integer_shifts": [-10, 10],
                "candidate_quantiles": [],
                "observed_sample_size": 0,
                "grid_size": 0,
                "variable_search": {
                    "score1": {
                        "grid_values": [150, 275, 700],
                        "min_value": 180,
                        "max_value": 520,
                    }
                },
            },
        )

        self.assertEqual(candidates, [180, 275, 330, 340, 350, 520])

    def test_policy_optimizer_observed_and_quantile_candidates_expand_search_space(self) -> None:
        import polars as pl

        from policy_lab.engine.optimizer import PolicyOptimizer

        optimizer = PolicyOptimizer()
        candidates = optimizer._candidate_thresholds(
            field_name="ratio",
            column=pl.Series("ratio", [0.1, 0.2, 0.35, 0.4, 0.7, 0.9]),
            baseline_value=0.4,
            search_defaults={
                "float_shifts": [-0.05, 0.05],
                "candidate_quantiles": [0.25, 0.5, 0.75],
                "observed_sample_size": 4,
                "grid_size": 4,
            },
        )

        self.assertGreaterEqual(len(candidates), 8)
        self.assertIn(0.35, candidates)
        self.assertIn(0.45, candidates)

    def test_policy_optimizer_parameter_sweep_uses_richer_search_defaults(self) -> None:
        from policy_lab.domain import SearchStrategy
        from policy_lab.engine.optimizer import PolicyOptimizer
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        optimizer = PolicyOptimizer()

        candidates = optimizer.generate_candidates(
            study.manifest.baseline_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.PARAMETER_SWEEP,
            search_defaults=study.manifest.search_defaults,
        )

        candidate_names = {candidate.name for candidate in candidates}
        self.assertTrue(any("score1 >" in name for name in candidate_names))
        self.assertTrue(
            any("indicador_potencial1 >" in name for name in candidate_names)
        )
        self.assertTrue(any("w1 <" in name for name in candidate_names))
        self.assertTrue(
            any("Derived veto risk_buffer_flag" == name for name in candidate_names)
        )

    def test_policy_optimizer_guided_search_explores_pairs_beyond_first_two_positions(self) -> None:
        from policy_lab.domain import PolicyDefinition, SearchStrategy
        from policy_lab.engine.optimizer import PolicyOptimizer
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        optimizer = PolicyOptimizer()

        candidates = optimizer.generate_candidates(
            study.manifest.baseline_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.GUIDED_SEARCH,
            search_defaults=study.manifest.search_defaults,
        )

        candidate_names = {candidate.name for candidate in candidates}
        self.assertTrue(any("w1 <" in name for name in candidate_names))
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "rule_bundle_candidate"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "guarded_rule_candidate"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "policy_pack_candidate"
                for candidate in candidates
            )
        )

        scratch_policy = PolicyDefinition.from_dict(study.manifest.baseline_policy.to_dict())
        scratch_policy.rules = []
        scratch_candidates = optimizer.generate_candidates(
            scratch_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.GUIDED_SEARCH,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "simple_rule_candidate"
                for candidate in scratch_candidates
            )
        )

    def test_policy_optimizer_heuristic_search_generates_candidates_from_scratch(self) -> None:
        from policy_lab.domain import PolicyDefinition, SearchStrategy
        from policy_lab.engine.optimizer import PolicyOptimizer
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        optimizer = PolicyOptimizer()
        scratch_policy = PolicyDefinition.from_dict(study.manifest.baseline_policy.to_dict())
        scratch_policy.rules = []

        candidates = optimizer.generate_candidates(
            scratch_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.HEURISTIC_SEARCH,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
        )

        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                in {
                    "mixed_candidate",
                    "rule_bundle_candidate",
                    "policy_pack_candidate",
                    "simple_rule_candidate",
                    "layered_rule_candidate",
                    "guarded_rule_candidate",
                }
                for candidate in candidates
            )
        )

    def test_policy_optimizer_simulated_annealing_generates_seed_candidates(self) -> None:
        from policy_lab.domain import SearchStrategy
        from policy_lab.engine.optimizer import PolicyOptimizer
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        optimizer = PolicyOptimizer()

        candidates = optimizer.generate_candidates(
            study.manifest.baseline_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.SIMULATED_ANNEALING,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
            performance_columns=study.manifest.snapshot.performance_columns,
        )

        self.assertGreater(len(candidates), 0)
        self.assertLessEqual(
            len(candidates),
            int(study.manifest.search_defaults.get("annealing_seed_limit", 18)),
        )

    def test_policy_optimizer_generates_simple_rule_candidates_from_unused_features(self) -> None:
        from policy_lab.domain import SearchStrategy
        from policy_lab.engine.optimizer import PolicyOptimizer
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        optimizer = PolicyOptimizer()

        candidates = optimizer.generate_candidates(
            study.manifest.baseline_policy,
            snapshot,
            derived_features=FeatureRepository().load(study),
            strategy=SearchStrategy.PARAMETER_SWEEP,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
        )

        candidate_names = {candidate.name for candidate in candidates}
        self.assertTrue(
            any(
                name.startswith("Add rule: approve when score2")
                for name in candidate_names
            )
        )
        self.assertTrue(
            any(
                name.startswith("Add rule: approve when z1 ==")
                for name in candidate_names
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "grouped_rule_candidate"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                "number_of_protests in" in candidate.name
                or "number_of_protests in" in candidate.policy.metadata.get(
                    "search_details",
                    {},
                ).get("summary", "")
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "composite_rule_candidate"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "signal_bundle_candidate"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate.policy.metadata.get("search_details", {}).get("candidate_kind")
                == "layered_rule_candidate"
                for candidate in candidates
            )
        )

    def test_run_search_records_objective_performance_details(self) -> None:
        from policy_lab.domain import PolicyDefinition, SearchStrategy
        from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.result_repository import ResultRepository
        from policy_lab.storage.scenario_repository import ScenarioRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        orchestrator = ScenarioOrchestrator(
            study_repository=study_repository,
            feature_repository=FeatureRepository(),
            scenario_repository=ScenarioRepository(),
            result_repository=ResultRepository(),
        )
        study = study_repository.load("demo_lending")
        results = orchestrator.run_search(
            study,
            strategy=SearchStrategy.PARAMETER_SWEEP,
        )

        self.assertGreater(len(results), 0)
        self.assertIn("objective_performance", results[0].lineage)
        self.assertIn("objective_performance_details", results[0].lineage)
        self.assertIn(
            "primary_gain",
            results[0].lineage["objective_performance_details"],
        )
        self.assertIn("objective_spec", results[0].lineage)
        self.assertIn("pareto_front", results[0].lineage)

        scratch_policy = PolicyDefinition.from_dict(study.manifest.baseline_policy.to_dict())
        scratch_policy.rules = []
        scratch_policy.metadata = {
            **scratch_policy.metadata,
            "search_base": "from_scratch",
        }
        scratch_results = orchestrator.run_search(
            study,
            strategy=SearchStrategy.PARAMETER_SWEEP,
            base_policy=scratch_policy,
        )

        self.assertIsInstance(scratch_results, list)
        self.assertTrue(
            all(
                item.lineage.get("search_details", {}).get("candidate_kind")
                not in {"threshold_override", "threshold_pair"}
                for item in scratch_results
            )
        )

    def test_run_search_supports_simulated_annealing(self) -> None:
        from policy_lab.domain import SearchStrategy
        from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.result_repository import ResultRepository
        from policy_lab.storage.scenario_repository import ScenarioRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        orchestrator = ScenarioOrchestrator(
            study_repository=study_repository,
            feature_repository=FeatureRepository(),
            scenario_repository=ScenarioRepository(),
            result_repository=ResultRepository(),
        )
        study = study_repository.load("demo_lending")
        results = orchestrator.run_search(
            study,
            strategy=SearchStrategy.SIMULATED_ANNEALING,
        )

        self.assertGreater(len(results), 0)
        self.assertTrue(
            all("objective_performance" in result.lineage for result in results)
        )

    def test_search_candidate_evaluation_does_not_retain_frames(self) -> None:
        from policy_lab.domain import SearchObjectiveSpec, SearchStrategy
        from policy_lab.engine.scenario_orchestrator import ScenarioOrchestrator
        from policy_lab.storage.feature_repository import FeatureRepository
        from policy_lab.storage.result_repository import ResultRepository
        from policy_lab.storage.scenario_repository import ScenarioRepository
        from policy_lab.storage.studies_repository import StudyRepository

        study_repository = StudyRepository()
        orchestrator = ScenarioOrchestrator(
            study_repository=study_repository,
            feature_repository=FeatureRepository(),
            scenario_repository=ScenarioRepository(),
            result_repository=ResultRepository(),
        )
        study = study_repository.load("demo_lending")
        snapshot = study_repository.load_snapshot(study)
        baseline_bundle = orchestrator.run_baseline_with_snapshot(study, snapshot)
        derived_features = FeatureRepository().load(study)
        candidates = orchestrator.optimizer.generate_candidates(
            study.manifest.baseline_policy,
            snapshot,
            derived_features=derived_features,
            strategy=SearchStrategy.PARAMETER_SWEEP,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
            performance_columns=study.manifest.snapshot.performance_columns,
            objective_spec=SearchObjectiveSpec(),
        )[:2]

        evaluations = orchestrator._evaluate_search_candidates(
            study,
            candidates,
            baseline_bundle=baseline_bundle,
            snapshot=snapshot,
            derived_features=derived_features,
            profit_reference_expected_profit=baseline_bundle.result.metrics.expected_profit,
            search_defaults=study.manifest.search_defaults,
        )

        self.assertEqual(len(evaluations), len(candidates))
        self.assertTrue(all(item.bundle.frame is None for item in evaluations))

    def test_search_parallel_worker_resolution_respects_bounds(self) -> None:
        from policy_lab.engine.scenario_orchestrator.service import (
            _resolve_search_max_workers,
        )

        self.assertEqual(
            _resolve_search_max_workers(
                search_defaults={"search_parallel_workers": 8},
                candidate_count=3,
            ),
            3,
        )
        self.assertEqual(
            _resolve_search_max_workers(
                search_defaults={"search_parallel_workers": 0},
                candidate_count=1,
            ),
            1,
        )

    def test_pareto_fronts_group_dominated_candidates(self) -> None:
        from policy_lab.domain import ScenarioMetrics, ScenarioResult
        from policy_lab.engine.scenario_orchestrator.service import _pareto_fronts

        strong = ScenarioResult(
            scenario_id="strong",
            scenario_name="Strong",
            policy_id="p1",
            study_id="s1",
            metrics=ScenarioMetrics(
                approval_rate=0.80,
                review_rate=0.0,
                rejection_rate=0.20,
                expected_profit=100.0,
                expected_profit_index=105.0,
                risk_estimate=0.10,
                churn_estimate=0.05,
                out_of_support_ratio=0.02,
                uncertainty_label="low",
                complexity_score=1.0,
                features_used=[],
                rules_count=1,
                records_evaluated=100,
            ),
            transitions=[],
            decision_distribution=[],
        )
        weak = ScenarioResult(
            scenario_id="weak",
            scenario_name="Weak",
            policy_id="p2",
            study_id="s1",
            metrics=ScenarioMetrics(
                approval_rate=0.75,
                review_rate=0.0,
                rejection_rate=0.25,
                expected_profit=95.0,
                expected_profit_index=100.0,
                risk_estimate=0.12,
                churn_estimate=0.06,
                out_of_support_ratio=0.03,
                uncertainty_label="low",
                complexity_score=1.2,
                features_used=[],
                rules_count=1,
                records_evaluated=100,
            ),
            transitions=[],
            decision_distribution=[],
        )
        tradeoff = ScenarioResult(
            scenario_id="tradeoff",
            scenario_name="Tradeoff",
            policy_id="p3",
            study_id="s1",
            metrics=ScenarioMetrics(
                approval_rate=0.85,
                review_rate=0.0,
                rejection_rate=0.15,
                expected_profit=90.0,
                expected_profit_index=97.0,
                risk_estimate=0.14,
                churn_estimate=0.07,
                out_of_support_ratio=0.01,
                uncertainty_label="low",
                complexity_score=0.9,
                features_used=[],
                rules_count=1,
                records_evaluated=100,
            ),
            transitions=[],
            decision_distribution=[],
        )

        fronts = _pareto_fronts([strong, weak, tradeoff])

        self.assertEqual([item.scenario_id for item in fronts[0]], ["strong", "tradeoff"])
        self.assertEqual([item.scenario_id for item in fronts[1]], ["weak"])

    def test_run_search_returns_transferable_store_payload(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.domain import SearchStrategy

        table_data, columns, _figure, store_payload = callback_handlers.run_search(
            1,
            "demo_lending",
            SearchStrategy.GUIDED_SEARCH.value,
            "baseline_study",
            "approval",
            "maximize",
            "risk",
            2.0,
            None,
            None,
            None,
            None,
        )

        self.assertTrue(table_data)
        self.assertTrue(columns)
        self.assertEqual(store_payload["study_id"], "demo_lending")
        self.assertTrue(store_payload["results"])
        self.assertIn("scenario", store_payload["results"][0])
        self.assertIn("result", store_payload["results"][0])

    def test_transfer_search_candidate_to_manual_lab_creates_optimization_asset(self) -> None:
        from policy_lab.apps.simulator_app import callback_handlers
        from policy_lab.domain import PolicyDefinition, ScenarioDefinition
        from policy_lab.storage.studies_repository import StudyRepository

        study = StudyRepository().load("demo_lending")
        persisted_entries: list[dict[str, object]] = []
        original_load = callback_handlers.created_rule_repository.load
        original_save = callback_handlers.created_rule_repository.save
        candidate_policy = PolicyDefinition.from_dict(study.manifest.baseline_policy.to_dict())
        candidate_policy.rules[0].blocks[0].predicates[0].value = 777
        scenario = ScenarioDefinition(
            scenario_id="search-transfer-test",
            name="Policy pack",
            description="Sugestao sintetica.",
            policy=candidate_policy,
            feature_ids=[],
            tags=["search"],
        )
        search_results_store = {
            "study_id": study.study_id,
            "results": [
                {
                    "scenario": scenario.to_dict(),
                    "result": {
                        "metrics": {
                            "approval_rate": 0.85,
                            "expected_profit_index": 102.5,
                            "risk_estimate": 0.18,
                            "uncertainty_label": "low",
                            "complexity_score": 1.0,
                        },
                        "lineage": {
                            "pareto_front": 1,
                            "objective_performance": 42.0,
                            "search_details": {
                                "candidate_kind": "policy_pack_candidate",
                                "summary": "approve when score1 > 400",
                            },
                        },
                    },
                    "search_strategy": "guided_search",
                    "search_base": "baseline_study",
                    "objective_spec": {
                        "primary_metric": "approval",
                        "direction": "maximize",
                        "preserve_metric": "risk",
                        "max_degradation": 2.0,
                    },
                }
            ],
        }
        try:
            callback_handlers.created_rule_repository.load = lambda _study: list(persisted_entries)
            callback_handlers.created_rule_repository.save = lambda _study, entries: (
                persisted_entries.clear() or persisted_entries.extend(entries)
            )
            result = callback_handlers.transfer_search_candidate_to_manual_lab(
                1,
                study.study_id,
                [0],
                search_results_store,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        finally:
            callback_handlers.created_rule_repository.load = original_load
            callback_handlers.created_rule_repository.save = original_save

        updated_custom_store = result[0]
        updated_rule_state = result[1]
        updated_last_simulation = result[8]
        main_tab = result[9]
        status = result[10]

        self.assertEqual(main_tab, "manual_lab")
        self.assertIn("transferida", status)
        self.assertEqual(updated_custom_store["study_id"], study.study_id)
        self.assertEqual(updated_custom_store["entries"][0]["source_type"], "baseline_rule_variant")
        self.assertEqual(
            len(updated_rule_state["used_rule_ids"]),
            len(study.manifest.baseline_policy.rules) - 1,
        )
        self.assertEqual(len(updated_rule_state["used_custom_rule_ids"]), 1)
        self.assertEqual(updated_last_simulation["study_id"], study.study_id)


if __name__ == "__main__":
    unittest.main()
