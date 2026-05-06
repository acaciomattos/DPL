from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from random import Random
from typing import Any, Protocol

import polars as pl

from policy_lab.domain import (
    DecisionRuleDefinition,
    DerivedFeatureDefinition,
    LogicalOperator,
    Operator,
    PolicyDefinition,
    PredicateDefinition,
    RuleBlockDefinition,
    ScenarioDefinition,
    SearchObjectiveSpec,
    SearchStrategy,
)
from policy_lab.engine.policy_parser import PolicyBuilder


@dataclass(slots=True)
class SearchProblem:
    policy: PolicyDefinition
    snapshot: pl.DataFrame
    derived_features: list[DerivedFeatureDefinition]
    search_defaults: dict[str, Any]
    analysis_feature_columns: list[str]
    performance_columns: dict[str, str]
    objective_spec: SearchObjectiveSpec


@dataclass(slots=True)
class PredicatePosition:
    handle: str
    rule_name: str
    field: str
    operator: Operator
    value: float | int


@dataclass(slots=True)
class RuleCandidateSpec:
    rule: DecisionRuleDefinition
    feature_ids: list[str]
    summary: str
    tags: list[str]


class SearchStrategyEngine(Protocol):
    def generate(
        self,
        problem: SearchProblem,
        generator: CandidateGenerator,
    ) -> list[ScenarioDefinition]: ...


class CandidateGenerator:
    def __init__(self, problem: SearchProblem) -> None:
        self.problem = problem

    def parameter_sweep_candidates(self) -> list[ScenarioDefinition]:
        candidates: list[ScenarioDefinition] = []
        derived_by_id = {
            feature.feature_id: feature for feature in self.problem.derived_features
        }

        for position in self.numeric_positions():
            values = self.threshold_candidates(
                field_name=position.field,
                column=self.problem.snapshot[position.field],
                baseline_value=position.value,
            )
            for candidate_value in values:
                if candidate_value == position.value:
                    continue
                candidate_policy = PolicyBuilder.apply_threshold_overrides(
                    self.problem.policy,
                    {position.handle: candidate_value},
                )
                self._attach_search_details(
                    candidate_policy,
                    strategy="parameter_sweep",
                    candidate_kind="threshold_override",
                    summary=self._override_summary(position, candidate_value),
                    details={
                        "threshold_overrides": [
                            {
                                "rule_name": position.rule_name,
                                "field": position.field,
                                "operator": position.operator.value,
                                "value": candidate_value,
                            }
                        ],
                        "added_rules": [],
                    },
                )
                candidates.append(
                    ScenarioDefinition(
                        scenario_id=(
                            f"search-{position.field}-{_slug_value(candidate_value)}"
                        ),
                        name=self._override_summary(position, candidate_value),
                        description=f"Threshold scenario for {position.field}.",
                        policy=candidate_policy,
                        tags=["parameter_sweep"],
                    )
                )

        if self.problem.policy.rules or self.problem.policy.default_decision != "reject":
            for feature_id in self.problem.search_defaults.get("feature_candidates", []):
                feature = derived_by_id.get(feature_id)
                if not feature:
                    continue
                candidates.append(
                    ScenarioDefinition(
                        scenario_id=f"search-feature-{feature_id}",
                        name=f"Derived veto {feature.name}",
                        description="Adds a reusable derived veto block.",
                        policy=self._policy_with_details(
                            PolicyBuilder.add_reject_rule_from_feature(
                                self.problem.policy,
                                feature,
                            ),
                            strategy="parameter_sweep",
                            candidate_kind="derived_veto",
                            summary=f"reject when {feature.name} == True",
                            details={
                                "threshold_overrides": {},
                                "added_rules": [f"reject when {feature.name} == True"],
                            },
                        ),
                        feature_ids=[feature_id],
                        tags=["derived_feature"],
                    )
                )

        candidates.extend(self.simple_rule_candidates())
        return deduplicate_candidates(candidates)

    def simple_rule_candidates(self) -> list[ScenarioDefinition]:
        candidates: list[ScenarioDefinition] = []
        for spec in self.all_rule_specs():
            candidate_kind = self._spec_candidate_kind(spec)
            candidate_policy = PolicyBuilder.add_rule(self.problem.policy, spec.rule)
            self._attach_search_details(
                candidate_policy,
                strategy="parameter_sweep",
                candidate_kind=candidate_kind,
                summary=spec.summary,
                details={
                    "threshold_overrides": {},
                    "added_rules": [spec.summary],
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=f"rule-{_slug_value(spec.rule.rule_id)}",
                    name=f"Add rule: {spec.summary}",
                    description=(
                        "Simple rule candidate generated from an analysis feature "
                        "outside the baseline structure."
                    ),
                    policy=candidate_policy,
                    feature_ids=spec.feature_ids,
                    tags=spec.tags,
                )
            )
        return deduplicate_candidates(candidates)

    def all_rule_specs(self) -> list[RuleCandidateSpec]:
        simple_specs = self.simple_rule_specs()
        grouped_specs = self.grouped_category_rule_specs()
        composite_specs = self.composite_rule_specs(simple_specs)
        signal_bundle_specs = self.signal_bundle_specs(simple_specs)
        layered_specs = self.layered_rule_specs(simple_specs, signal_bundle_specs)
        return [
            *simple_specs,
            *grouped_specs,
            *composite_specs,
            *signal_bundle_specs,
            *layered_specs,
        ]

    def simple_rule_specs(self) -> list[RuleCandidateSpec]:
        derived_by_name = {
            feature.name: feature for feature in self.problem.derived_features
        }
        configured_fields = [
            field
            for field in [
                *self.problem.analysis_feature_columns,
                *list(derived_by_name),
            ]
            if field in self.problem.snapshot.columns or field in derived_by_name
        ]
        if not configured_fields:
            return []

        used_fields = {
            predicate.field
            for rule in self.problem.policy.rules
            for block in rule.blocks
            for predicate in block.predicates
        }
        candidate_fields = [field for field in configured_fields if field not in used_fields]
        decisions = self._candidate_decisions()
        if not decisions:
            return []

        existing_rule_ids = {rule.rule_id for rule in self.problem.policy.rules}
        specs: list[RuleCandidateSpec] = []
        for field_name in candidate_fields:
            derived_feature = derived_by_name.get(field_name)
            if derived_feature is not None:
                for decision in decisions:
                    rule = self._build_simple_rule(
                        field_name=field_name,
                        operator=Operator.EQ,
                        value=True,
                        decision=decision,
                        existing_rule_ids=existing_rule_ids,
                    )
                    specs.append(
                        RuleCandidateSpec(
                            rule=rule,
                            feature_ids=[derived_feature.feature_id],
                            summary=f"{decision} when {field_name} == True",
                            tags=["simple_rule_candidate", "derived_feature_rule"],
                        )
                    )
                continue

            dtype = self.problem.snapshot.schema.get(field_name)
            if _is_low_cardinality(dtype, self.problem.snapshot[field_name]):
                categories = sorted(
                    set(self.problem.snapshot[field_name].drop_nulls().unique().to_list())
                )
                category_limit = int(
                    self.problem.search_defaults.get("new_rule_category_limit", 4)
                )
                for decision in decisions:
                    for category in categories[:category_limit]:
                        rule = self._build_simple_rule(
                            field_name=field_name,
                            operator=Operator.EQ,
                            value=category,
                            decision=decision,
                            existing_rule_ids=existing_rule_ids,
                        )
                        specs.append(
                            RuleCandidateSpec(
                                rule=rule,
                                feature_ids=[],
                                summary=f"{decision} when {field_name} == {category}",
                                tags=["simple_rule_candidate", "parameter_sweep"],
                            )
                        )
                continue

            if _is_numeric_dtype(dtype):
                threshold_values = self.threshold_candidates(
                    field_name=field_name,
                    column=self.problem.snapshot[field_name],
                    baseline_value=self._baseline_for_new_field(field_name),
                )
                threshold_limit = int(
                    self.problem.search_defaults.get("new_rule_threshold_limit", 3)
                )
                selected_values = _spread_values(threshold_values, threshold_limit)
                operators = self.problem.search_defaults.get(
                    "new_rule_numeric_operators",
                    [Operator.GT.value, Operator.LT.value],
                )
                for decision in decisions:
                    for operator_value in operators:
                        operator = Operator(operator_value)
                        for candidate_value in selected_values:
                            rule = self._build_simple_rule(
                                field_name=field_name,
                                operator=operator,
                                value=candidate_value,
                                decision=decision,
                                existing_rule_ids=existing_rule_ids,
                            )
                            specs.append(
                                RuleCandidateSpec(
                                    rule=rule,
                                    feature_ids=[],
                                    summary=(
                                        f"{decision} when {field_name} "
                                        f"{operator.value} {candidate_value}"
                                    ),
                                    tags=["simple_rule_candidate", "parameter_sweep"],
                                )
                            )

        ranked_specs = self._rank_rule_candidate_specs(specs)
        field_limit = int(self.problem.search_defaults.get("new_rule_feature_limit", 6))
        candidate_limit = int(
            self.problem.search_defaults.get("new_rule_candidate_limit", field_limit * 4)
        )
        selected_specs: list[RuleCandidateSpec] = []
        seen_fields: set[str] = set()
        overflow_specs: list[RuleCandidateSpec] = []
        for spec in ranked_specs:
            field_name = spec.rule.blocks[0].predicates[0].field
            if field_name not in seen_fields and len(seen_fields) < field_limit:
                selected_specs.append(spec)
                seen_fields.add(field_name)
            else:
                overflow_specs.append(spec)
        for spec in overflow_specs:
            if len(selected_specs) >= candidate_limit:
                break
            selected_specs.append(spec)
        return selected_specs

    def grouped_category_rule_specs(self) -> list[RuleCandidateSpec]:
        derived_by_name = {
            feature.name: feature for feature in self.problem.derived_features
        }
        configured_fields = [
            field
            for field in self.problem.analysis_feature_columns
            if field in self.problem.snapshot.columns and field not in derived_by_name
        ]
        if not configured_fields:
            return []

        used_fields = {
            predicate.field
            for rule in self.problem.policy.rules
            for block in rule.blocks
            for predicate in block.predicates
        }
        candidate_fields = [field for field in configured_fields if field not in used_fields]
        decisions = self._candidate_decisions()
        if not decisions:
            return []

        existing_rule_ids = {rule.rule_id for rule in self.problem.policy.rules}
        max_unique = int(
            self.problem.search_defaults.get("grouped_category_max_unique", 12)
        )
        window_sizes = [
            int(size)
            for size in self.problem.search_defaults.get(
                "grouped_category_window_sizes",
                [2, 3],
            )
            if int(size) > 1
        ]
        per_field_limit = int(
            self.problem.search_defaults.get("grouped_category_candidate_limit", 6)
        )
        specs: list[RuleCandidateSpec] = []
        for field_name in candidate_fields:
            series = self.problem.snapshot[field_name]
            dtype = self.problem.snapshot.schema.get(field_name)
            if not _is_integral_dtype(dtype):
                continue
            categories = sorted(set(series.drop_nulls().unique().to_list()))
            if len(categories) < 3 or len(categories) > max_unique:
                continue

            field_specs: list[RuleCandidateSpec] = []
            for decision in decisions:
                for window_size in window_sizes:
                    if window_size > len(categories):
                        continue
                    for start in range(0, len(categories) - window_size + 1):
                        category_group = categories[start : start + window_size]
                        rule = self._build_simple_rule(
                            field_name=field_name,
                            operator=Operator.IN,
                            value=category_group,
                            decision=decision,
                            existing_rule_ids=existing_rule_ids,
                        )
                        field_specs.append(
                            RuleCandidateSpec(
                                rule=rule,
                                feature_ids=[],
                                summary=(
                                    f"{decision} when {field_name} in "
                                    f"{category_group}"
                                ),
                                tags=["grouped_rule_candidate", "parameter_sweep"],
                            )
                        )
            ranked_field_specs = self._rank_rule_candidate_specs(field_specs)
            specs.extend(
                _spread_rule_specs(ranked_field_specs, limit=per_field_limit)
            )
        return specs

    def composite_rule_specs(
        self,
        simple_specs: list[RuleCandidateSpec],
    ) -> list[RuleCandidateSpec]:
        ranked_specs = [
            spec
            for spec in self._rank_rule_candidate_specs(simple_specs)
            if self._supports_composite_rule(spec)
        ]
        field_limit = int(self.problem.search_defaults.get("pair_rule_feature_limit", 4))
        candidate_limit = int(self.problem.search_defaults.get("pair_rule_candidate_limit", 6))
        selected_specs: list[RuleCandidateSpec] = []
        existing_rule_ids = {rule.rule_id for rule in self.problem.policy.rules}

        for first, second in combinations(ranked_specs[:field_limit], 2):
            if len(selected_specs) >= candidate_limit:
                break
            first_predicate = first.rule.blocks[0].predicates[0]
            second_predicate = second.rule.blocks[0].predicates[0]
            if first.rule.decision != second.rule.decision:
                continue
            if first_predicate.field == second_predicate.field:
                continue

            rule_id = _unique_rule_id(
                (
                    f"candidate-composite-{first_predicate.field}-"
                    f"{second_predicate.field}-{first.rule.decision}"
                ),
                existing_rule_ids,
            )
            composite_rule = DecisionRuleDefinition(
                rule_id=rule_id,
                name=(
                    f"{first.rule.decision} when {first_predicate.field} "
                    f"and {second_predicate.field}"
                ),
                decision=first.rule.decision,
                description="Composite rule candidate generated automatically.",
                block_combiner=LogicalOperator.ALL,
                blocks=[
                    RuleBlockDefinition(
                        block_id=f"{rule_id}-block",
                        name=f"{first_predicate.field}-{second_predicate.field} block",
                        logical_operator=LogicalOperator.ALL,
                        predicates=[
                            PredicateDefinition.from_dict(first_predicate.to_dict()),
                            PredicateDefinition.from_dict(second_predicate.to_dict()),
                        ],
                    )
                ],
            )
            selected_specs.append(
                RuleCandidateSpec(
                    rule=composite_rule,
                    feature_ids=[*first.feature_ids, *second.feature_ids],
                    summary=(
                        f"{first.rule.decision} when "
                        f"{first_predicate.field} {first_predicate.operator.value} "
                        f"{first_predicate.value} and {second_predicate.field} "
                        f"{second_predicate.operator.value} {second_predicate.value}"
                    ),
                    tags=["composite_rule_candidate", "guided_search"],
                )
            )
            existing_rule_ids.add(rule_id)
        return selected_specs

    def signal_bundle_specs(
        self,
        simple_specs: list[RuleCandidateSpec],
    ) -> list[RuleCandidateSpec]:
        ranked_specs = [
            spec
            for spec in self._rank_rule_candidate_specs(simple_specs)
            if self._supports_signal_bundle(spec)
        ]
        feature_limit = int(self.problem.search_defaults.get("signal_bundle_feature_limit", 6))
        candidate_limit = int(
            self.problem.search_defaults.get("signal_bundle_candidate_limit", 6)
        )
        selected_specs: list[RuleCandidateSpec] = []
        existing_rule_ids = {rule.rule_id for rule in self.problem.policy.rules}

        for first, second in combinations(ranked_specs[:feature_limit], 2):
            if len(selected_specs) >= candidate_limit:
                break
            first_predicate = first.rule.blocks[0].predicates[0]
            second_predicate = second.rule.blocks[0].predicates[0]
            if first.rule.decision != second.rule.decision:
                continue
            if first_predicate.field == second_predicate.field:
                continue
            if first_predicate.operator != second_predicate.operator:
                continue
            if first_predicate.value != second_predicate.value:
                continue

            rule_id = _unique_rule_id(
                (
                    f"candidate-signal-{first_predicate.field}-"
                    f"{second_predicate.field}-{first.rule.decision}"
                ),
                existing_rule_ids,
            )
            signal_rule = DecisionRuleDefinition(
                rule_id=rule_id,
                name=(
                    f"{first.rule.decision} when any of "
                    f"{first_predicate.field} or {second_predicate.field}"
                ),
                decision=first.rule.decision,
                description="Signal bundle candidate generated automatically.",
                block_combiner=LogicalOperator.ALL,
                blocks=[
                    RuleBlockDefinition(
                        block_id=f"{rule_id}-block",
                        name=f"{first_predicate.field}-{second_predicate.field} signals",
                        logical_operator=LogicalOperator.ANY,
                        predicates=[
                            PredicateDefinition.from_dict(first_predicate.to_dict()),
                            PredicateDefinition.from_dict(second_predicate.to_dict()),
                        ],
                    )
                ],
            )
            selected_specs.append(
                RuleCandidateSpec(
                    rule=signal_rule,
                    feature_ids=[*first.feature_ids, *second.feature_ids],
                    summary=(
                        f"{first.rule.decision} when any of "
                        f"{first_predicate.field} {first_predicate.operator.value} "
                        f"{first_predicate.value} or {second_predicate.field} "
                        f"{second_predicate.operator.value} {second_predicate.value}"
                    ),
                    tags=["signal_bundle_candidate", "guided_search"],
                )
            )
            existing_rule_ids.add(rule_id)
        return selected_specs

    def layered_rule_specs(
        self,
        simple_specs: list[RuleCandidateSpec],
        signal_bundle_specs: list[RuleCandidateSpec],
    ) -> list[RuleCandidateSpec]:
        numeric_specs = [
            spec
            for spec in self._rank_rule_candidate_specs(simple_specs)
            if self._supports_layered_numeric_spec(spec)
        ]
        ranked_signal_specs = [
            spec
            for spec in self._rank_rule_candidate_specs(signal_bundle_specs)
            if self._supports_layered_signal_spec(spec)
        ]
        numeric_limit = int(
            self.problem.search_defaults.get("layered_rule_numeric_limit", 4)
        )
        signal_limit = int(
            self.problem.search_defaults.get("layered_rule_signal_limit", 4)
        )
        candidate_limit = int(
            self.problem.search_defaults.get("layered_rule_candidate_limit", 6)
        )
        selected_specs: list[RuleCandidateSpec] = []
        existing_rule_ids = {rule.rule_id for rule in self.problem.policy.rules}

        for numeric_spec in numeric_specs[:numeric_limit]:
            if len(selected_specs) >= candidate_limit:
                break
            numeric_predicate = numeric_spec.rule.blocks[0].predicates[0]
            for signal_spec in ranked_signal_specs[:signal_limit]:
                if len(selected_specs) >= candidate_limit:
                    break
                if numeric_spec.rule.decision != signal_spec.rule.decision:
                    continue
                signal_predicates = signal_spec.rule.blocks[0].predicates
                signal_fields = {predicate.field for predicate in signal_predicates}
                if numeric_predicate.field in signal_fields:
                    continue

                rule_id = _unique_rule_id(
                    (
                        f"candidate-layered-{numeric_predicate.field}-"
                        f"{'-'.join(sorted(signal_fields))}-{numeric_spec.rule.decision}"
                    ),
                    existing_rule_ids,
                )
                layered_rule = DecisionRuleDefinition(
                    rule_id=rule_id,
                    name=(
                        f"{numeric_spec.rule.decision} when "
                        f"{numeric_predicate.field} and bundled signals"
                    ),
                    decision=numeric_spec.rule.decision,
                    description="Structured rule candidate generated automatically.",
                    block_combiner=LogicalOperator.ALL,
                    blocks=[
                        RuleBlockDefinition(
                            block_id=f"{rule_id}-thresholds",
                            name=f"{numeric_predicate.field} threshold",
                            logical_operator=LogicalOperator.ALL,
                            predicates=[
                                PredicateDefinition.from_dict(
                                    numeric_predicate.to_dict()
                                )
                            ],
                        ),
                        RuleBlockDefinition(
                            block_id=f"{rule_id}-signals",
                            name="Bundled signals",
                            logical_operator=LogicalOperator.ANY,
                            predicates=[
                                PredicateDefinition.from_dict(predicate.to_dict())
                                for predicate in signal_predicates
                            ],
                        ),
                    ],
                )
                signal_summary = " or ".join(
                    (
                        f"{predicate.field} {predicate.operator.value} "
                        f"{predicate.value}"
                    )
                    for predicate in signal_predicates
                )
                selected_specs.append(
                    RuleCandidateSpec(
                        rule=layered_rule,
                        feature_ids=[
                            *numeric_spec.feature_ids,
                            *signal_spec.feature_ids,
                        ],
                        summary=(
                            f"{numeric_spec.rule.decision} when "
                            f"{numeric_predicate.field} "
                            f"{numeric_predicate.operator.value} "
                            f"{numeric_predicate.value} and any of {signal_summary}"
                        ),
                        tags=["layered_rule_candidate", "guided_search"],
                    )
                )
                existing_rule_ids.add(rule_id)
        return selected_specs

    def guided_candidates(self) -> list[ScenarioDefinition]:
        positions = self.numeric_positions()
        candidates: list[ScenarioDefinition] = []
        values_per_predicate = int(
            self.problem.search_defaults.get("guided_values_per_predicate", 3)
        )
        pair_limit = int(self.problem.search_defaults.get("guided_pair_limit", 8))

        if len(positions) >= 2:
            for first, second in list(combinations(positions, 2))[:pair_limit]:
                first_values = self.threshold_candidates(
                    field_name=first.field,
                    column=self.problem.snapshot[first.field],
                    baseline_value=first.value,
                )[:values_per_predicate]
                second_values = self.threshold_candidates(
                    field_name=second.field,
                    column=self.problem.snapshot[second.field],
                    baseline_value=second.value,
                )[:values_per_predicate]

                for first_value in first_values:
                    for second_value in second_values:
                        overrides = {first.handle: first_value, second.handle: second_value}
                        candidate_policy = PolicyBuilder.apply_threshold_overrides(
                            self.problem.policy,
                            overrides,
                        )
                        self._attach_search_details(
                            candidate_policy,
                            strategy="guided_search",
                            candidate_kind="threshold_pair",
                            summary=(
                                f"{self._override_summary(first, first_value)}; "
                                f"{self._override_summary(second, second_value)}"
                            ),
                            details={
                                "threshold_overrides": [
                                    {
                                        "rule_name": first.rule_name,
                                        "field": first.field,
                                        "operator": first.operator.value,
                                        "value": first_value,
                                    },
                                    {
                                        "rule_name": second.rule_name,
                                        "field": second.field,
                                        "operator": second.operator.value,
                                        "value": second_value,
                                    },
                                ],
                                "added_rules": [],
                            },
                        )
                        candidates.append(
                            ScenarioDefinition(
                                scenario_id=(
                                    f"guided-{first.field}-{_slug_value(first_value)}-"
                                    f"{second.field}-{_slug_value(second_value)}"
                                ),
                                name=(
                                    f"{first.rule_name}: {first.field} {first.operator.value} "
                                    f"{first_value} | {second.rule_name}: {second.field} "
                                    f"{second.operator.value} {second_value}"
                                ),
                                description="Bounded multi-threshold candidate.",
                                policy=candidate_policy,
                                tags=["guided_search"],
                            )
                        )

        mix_limit = int(self.problem.search_defaults.get("guided_rule_mix_limit", 4))
        for spec in self.all_rule_specs()[:mix_limit]:
            candidate_kind = self._spec_candidate_kind(spec)
            candidate_policy = PolicyBuilder.add_rule(self.problem.policy, spec.rule)
            self._attach_search_details(
                candidate_policy,
                strategy="guided_search",
                candidate_kind=candidate_kind,
                summary=spec.summary,
                details={
                    "threshold_overrides": {},
                    "added_rules": [spec.summary],
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=f"guided-rule-{_slug_value(spec.rule.rule_id)}",
                    name=f"Guided rule candidate: {spec.summary}",
                    description="Guided candidate created from an analysis feature.",
                    policy=candidate_policy,
                    feature_ids=spec.feature_ids,
                    tags=["guided_search", *spec.tags],
                )
            )
        guarded_limit = int(
            self.problem.search_defaults.get("guarded_rule_candidate_limit", 4)
        )
        for spec, feature in self.guarded_rule_candidates(limit=guarded_limit):
            candidate_policy = PolicyBuilder.add_rule(self.problem.policy, spec.rule)
            candidate_policy = PolicyBuilder.add_reject_rule_from_feature(
                candidate_policy,
                feature,
            )
            summary = f"{spec.summary}; reject when {feature.name} == True"
            self._attach_search_details(
                candidate_policy,
                strategy="guided_search",
                candidate_kind="guarded_rule_candidate",
                summary=summary,
                details={
                    "threshold_overrides": {},
                    "added_rules": [spec.summary, f"reject when {feature.name} == True"],
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=(
                        "guided-guarded-"
                        f"{_slug_value(spec.rule.rule_id)}-{_slug_value(feature.feature_id)}"
                    ),
                    name=f"Guided guarded rule: {spec.rule.decision}",
                    description="Guided candidate with one positive rule and a derived veto.",
                    policy=candidate_policy,
                    feature_ids=[*spec.feature_ids, feature.feature_id],
                    tags=["guided_search", "guarded_rule_candidate", *spec.tags],
                )
            )
        bundle_limit = int(self.problem.search_defaults.get("guided_bundle_limit", 4))
        for bundle_specs in self.rule_bundles(limit=bundle_limit):
            candidate_policy = self.problem.policy
            feature_ids: list[str] = []
            added_rules: list[str] = []
            for spec in bundle_specs:
                candidate_policy = PolicyBuilder.add_rule(candidate_policy, spec.rule)
                feature_ids.extend(spec.feature_ids)
                added_rules.append(spec.summary)
            summary = "; ".join(added_rules)
            self._attach_search_details(
                candidate_policy,
                strategy="guided_search",
                candidate_kind="rule_bundle_candidate",
                summary=summary,
                details={
                    "threshold_overrides": {},
                    "added_rules": added_rules,
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=(
                        "guided-bundle-"
                        f"{'-'.join(_slug_value(spec.rule.rule_id) for spec in bundle_specs)}"
                    ),
                    name=f"Guided bundle: {bundle_specs[0].rule.decision}",
                    description="Guided candidate with multiple generated rules.",
                    policy=candidate_policy,
                    feature_ids=feature_ids,
                    tags=["guided_search", "rule_bundle_candidate"],
                )
            )
        pack_limit = int(self.problem.search_defaults.get("policy_pack_candidate_limit", 4))
        for bundle_specs, feature in self.policy_pack_candidates(limit=pack_limit):
            candidate_policy = self.problem.policy
            feature_ids: list[str] = [feature.feature_id]
            added_rules: list[str] = []
            for spec in bundle_specs:
                candidate_policy = PolicyBuilder.add_rule(candidate_policy, spec.rule)
                feature_ids.extend(spec.feature_ids)
                added_rules.append(spec.summary)
            candidate_policy = PolicyBuilder.add_reject_rule_from_feature(
                candidate_policy,
                feature,
            )
            added_rules.append(f"reject when {feature.name} == True")
            summary = "; ".join(added_rules)
            self._attach_search_details(
                candidate_policy,
                strategy="guided_search",
                candidate_kind="policy_pack_candidate",
                summary=summary,
                details={
                    "threshold_overrides": {},
                    "added_rules": added_rules,
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=(
                        "guided-pack-"
                        f"{'-'.join(_slug_value(spec.rule.rule_id) for spec in bundle_specs)}-"
                        f"{_slug_value(feature.feature_id)}"
                    ),
                    name=f"Guided policy pack: {bundle_specs[0].rule.decision}",
                    description="Guided candidate with multiple new rules and a veto.",
                    policy=candidate_policy,
                    feature_ids=feature_ids,
                    tags=["guided_search", "policy_pack_candidate"],
                )
            )
        return deduplicate_candidates(candidates)

    def heuristic_candidates(self) -> list[ScenarioDefinition]:
        randomizer = Random(self.problem.search_defaults.get("seed", 17))
        positions = self.numeric_positions()
        rule_specs = self.all_rule_specs()
        if not positions and not rule_specs:
            return []

        sample_size = int(self.problem.search_defaults.get("heuristic_sample_size", 2))
        candidates: list[ScenarioDefinition] = []
        for index in range(self.problem.search_defaults.get("heuristic_trials", 6)):
            sampled = (
                randomizer.sample(positions, k=min(sample_size, len(positions)))
                if positions
                else []
            )
            overrides: dict[str, float | int] = {}
            for item in sampled:
                options = self.threshold_candidates(
                    field_name=item.field,
                    column=self.problem.snapshot[item.field],
                    baseline_value=item.value,
                )
                overrides[item.handle] = randomizer.choice(options)

            candidate_policy = PolicyBuilder.apply_threshold_overrides(
                self.problem.policy,
                overrides,
            )
            feature_ids: list[str] = []
            added_rules: list[str] = []
            added_rule_specs: list[RuleCandidateSpec] = []
            if rule_specs and (not sampled or randomizer.random() > 0.35):
                rule_bundle_size = min(
                    int(self.problem.search_defaults.get("heuristic_rule_bundle_size", 2)),
                    len(rule_specs),
                )
                add_bundle = (
                    rule_bundle_size > 1
                    and randomizer.random()
                    < float(
                        self.problem.search_defaults.get(
                            "heuristic_rule_bundle_probability",
                            0.45,
                        )
                    )
                )
                if add_bundle:
                    candidate_specs = randomizer.sample(
                        rule_specs,
                        k=rule_bundle_size,
                    )
                    if self._bundle_compatible_specs(candidate_specs):
                        added_rule_specs.extend(candidate_specs)
                if not added_rule_specs:
                    added_rule_specs.append(randomizer.choice(rule_specs))

                for spec in added_rule_specs:
                    candidate_policy = PolicyBuilder.add_rule(candidate_policy, spec.rule)
                    feature_ids.extend(spec.feature_ids)
                    added_rules.append(spec.summary)

            if self.problem.derived_features and randomizer.random() > 0.5:
                veto_features = self._candidate_veto_features(allow_with_positive_rule=True)
                feature_pool = veto_features or self.problem.derived_features
                feature = randomizer.choice(feature_pool)
                candidate_policy = PolicyBuilder.add_reject_rule_from_feature(
                    candidate_policy,
                    feature,
                )
                feature_ids.append(feature.feature_id)
                added_rules.append(f"reject when {feature.name} == True")

            self._attach_search_details(
                candidate_policy,
                strategy="heuristic_search",
                candidate_kind=self._heuristic_candidate_kind(
                    overrides=overrides,
                    added_rule_specs=added_rule_specs,
                    added_rules=added_rules,
                ),
                summary=(
                    "; ".join(
                        [
                            *[
                                self._override_summary(
                                    position,
                                    overrides[position.handle],
                                )
                                for position in sampled
                                if position.handle in overrides
                            ],
                            *added_rules,
                        ]
                    )
                    or f"heuristic candidate {index + 1}"
                ),
                details={
                    "threshold_overrides": [
                        {
                            "rule_name": position.rule_name,
                            "field": position.field,
                            "operator": position.operator.value,
                            "value": overrides[position.handle],
                        }
                        for position in sampled
                        if position.handle in overrides
                    ],
                    "added_rules": added_rules,
                },
            )
            candidates.append(
                ScenarioDefinition(
                    scenario_id=f"heuristic-{index + 1}",
                    name=f"Heuristic candidate {index + 1}",
                    description="Random bounded policy candidate.",
                    policy=candidate_policy,
                    feature_ids=feature_ids,
                    tags=["heuristic_search"],
                )
            )
        return deduplicate_candidates(candidates)

    def annealing_seed_candidates(self) -> list[ScenarioDefinition]:
        candidates = deduplicate_candidates(
            self.guided_candidates()
            + self.heuristic_candidates()
            + self.parameter_sweep_candidates()
        )
        return self._limited_search_candidates(
            candidates,
            limit_key="annealing_seed_limit",
            randomizer=Random(int(self.problem.search_defaults.get("seed", 17) or 17)),
        )

    def annealing_neighbor_candidates(
        self,
        randomizer: Random,
    ) -> list[ScenarioDefinition]:
        candidates = deduplicate_candidates(
            self.guided_candidates()
            + self.heuristic_candidates()
            + self.parameter_sweep_candidates()
        )
        return self._limited_search_candidates(
            candidates,
            limit_key="annealing_neighbor_limit",
            randomizer=randomizer,
        )

    def rule_bundles(self, *, limit: int) -> list[tuple[RuleCandidateSpec, ...]]:
        ranked_specs = self.all_rule_specs()
        if limit <= 0 or len(ranked_specs) < 2:
            return []
        feature_limit = int(self.problem.search_defaults.get("guided_rule_mix_limit", 4))
        bundles: list[tuple[RuleCandidateSpec, ...]] = []
        for bundle_specs in combinations(ranked_specs[:feature_limit], 2):
            if len(bundles) >= limit:
                break
            if self._bundle_compatible_specs(bundle_specs):
                bundles.append(bundle_specs)
        return bundles

    def guarded_rule_candidates(
        self,
        *,
        limit: int,
    ) -> list[tuple[RuleCandidateSpec, DerivedFeatureDefinition]]:
        if limit <= 0:
            return []
        features = self._candidate_veto_features(allow_with_positive_rule=True)
        if not features:
            return []
        ranked_specs = [
            spec
            for spec in self.all_rule_specs()
            if spec.rule.decision != self.problem.policy.default_decision
        ]
        candidates: list[tuple[RuleCandidateSpec, DerivedFeatureDefinition]] = []
        for spec in ranked_specs:
            for feature in features:
                if feature.feature_id in spec.feature_ids:
                    continue
                candidates.append((spec, feature))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def policy_pack_candidates(
        self,
        *,
        limit: int,
    ) -> list[tuple[tuple[RuleCandidateSpec, ...], DerivedFeatureDefinition]]:
        if limit <= 0:
            return []
        features = self._candidate_veto_features(allow_with_positive_rule=True)
        bundles = self.rule_bundles(limit=limit)
        if not features or not bundles:
            return []
        candidates: list[tuple[tuple[RuleCandidateSpec, ...], DerivedFeatureDefinition]] = []
        for bundle_specs in bundles:
            bundle_feature_ids = {
                feature_id for spec in bundle_specs for feature_id in spec.feature_ids
            }
            for feature in features:
                if feature.feature_id in bundle_feature_ids:
                    continue
                candidates.append((bundle_specs, feature))
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def numeric_positions(self) -> list[PredicatePosition]:
        positions: list[PredicatePosition] = []
        for rule_index, rule in enumerate(self.problem.policy.rules):
            for block_index, block in enumerate(rule.blocks):
                for predicate_index, predicate in enumerate(block.predicates):
                    if predicate.field not in self.problem.snapshot.columns:
                        continue
                    if not _is_numeric_dtype(
                        self.problem.snapshot.schema.get(predicate.field)
                    ):
                        continue
                    positions.append(
                        PredicatePosition(
                            handle=PolicyBuilder.predicate_handle(
                                rule_index,
                                block_index,
                                predicate_index,
                                predicate,
                            ),
                            rule_name=rule.name,
                            field=predicate.field,
                            operator=predicate.operator,
                            value=predicate.value,
                        )
                    )
        return positions

    def threshold_candidates(
        self,
        *,
        field_name: str,
        column: pl.Series,
        baseline_value: float | int,
    ) -> list[float | int]:
        config = self._field_search_config(field_name)
        lower, upper = self._bounded_range(
            column=column,
            baseline_value=baseline_value,
            config=config,
        )
        if lower > upper:
            lower, upper = upper, lower

        candidates: set[float | int] = {baseline_value}
        candidates.update(
            self._shift_candidates(
                baseline_value=baseline_value,
                lower=lower,
                upper=upper,
                config=config,
            )
        )
        candidates.update(
            self._quantile_candidates(
                column=column,
                lower=lower,
                upper=upper,
                config=config,
                baseline_value=baseline_value,
            )
        )
        candidates.update(
            self._grid_candidates(
                lower=lower,
                upper=upper,
                config=config,
                baseline_value=baseline_value,
            )
        )
        candidates.update(
            self._observed_value_candidates(
                column=column,
                lower=lower,
                upper=upper,
                config=config,
                baseline_value=baseline_value,
            )
        )
        return sorted(candidates)

    def _field_search_config(self, field_name: str) -> dict[str, Any]:
        variable_defaults = self.problem.search_defaults.get("variable_search", {})
        field_config = variable_defaults.get(field_name, {})
        if not isinstance(field_config, dict):
            field_config = {}
        return {
            **self.problem.search_defaults,
            **field_config,
        }

    def _limited_search_candidates(
        self,
        candidates: list[ScenarioDefinition],
        *,
        limit_key: str,
        randomizer: Random,
    ) -> list[ScenarioDefinition]:
        limit = int(self.problem.search_defaults.get(limit_key, 0) or 0)
        if limit <= 0 or len(candidates) <= limit:
            return candidates
        ranked = sorted(candidates, key=_candidate_preference_rank)
        head_size = min(max(limit // 2, 1), limit, len(ranked))
        selected = ranked[:head_size]
        remainder = ranked[head_size:]
        slots = limit - len(selected)
        if slots > 0 and remainder:
            if len(remainder) <= slots:
                selected.extend(remainder)
            else:
                selected.extend(randomizer.sample(remainder, k=slots))
        return selected

    def _override_summary(
        self,
        position: PredicatePosition,
        candidate_value: float | int,
    ) -> str:
        return (
            f"{position.rule_name}: "
            f"{position.field} {position.operator.value} {candidate_value}"
        )

    def _attach_search_details(
        self,
        policy: PolicyDefinition,
        *,
        strategy: str,
        candidate_kind: str,
        summary: str,
        details: dict[str, Any],
    ) -> None:
        policy.metadata = {
            **policy.metadata,
            "search_details": {
                "strategy": strategy,
                "candidate_kind": candidate_kind,
                "summary": summary,
                **details,
            },
        }

    def _policy_with_details(
        self,
        policy: PolicyDefinition,
        *,
        strategy: str,
        candidate_kind: str,
        summary: str,
        details: dict[str, Any],
    ) -> PolicyDefinition:
        self._attach_search_details(
            policy,
            strategy=strategy,
            candidate_kind=candidate_kind,
            summary=summary,
            details=details,
        )
        return policy

    def _candidate_decisions(self) -> list[str]:
        configured = self.problem.search_defaults.get("new_rule_decisions")
        if isinstance(configured, list) and configured:
            return [str(value) for value in configured]
        decisions: list[str] = []
        for rule in self.problem.policy.rules:
            if (
                rule.decision != self.problem.policy.default_decision
                and rule.decision not in decisions
            ):
                decisions.append(rule.decision)
        if not decisions:
            return ["approve"]
        if self.problem.objective_spec.primary_metric in {"risk", "churn", "complexity"}:
            return [decision for decision in decisions if decision != "review"] or decisions
        return decisions

    def _rank_rule_candidate_specs(
        self,
        specs: list[RuleCandidateSpec],
    ) -> list[RuleCandidateSpec]:
        return sorted(
            specs,
            key=self._score_rule_candidate_spec,
            reverse=True,
        )

    def _score_rule_candidate_spec(self, spec: RuleCandidateSpec) -> float:
        selected = self._selected_subset_for_rule(spec.rule)
        if selected.height == 0:
            return float("-inf")

        total = max(self.problem.snapshot.height, 1)
        approval_pp = (selected.height / total) * 100.0
        risk_column = self.problem.performance_columns.get("risk_event")
        profit_column = self.problem.performance_columns.get("profit")
        churn_column = self.problem.performance_columns.get("churn")
        risk_pct = (
            (selected.select(pl.col(risk_column).mean()).item() or 0.0) * 100.0
            if risk_column and risk_column in selected.columns
            else 0.0
        )
        churn_pct = (
            (selected.select(pl.col(churn_column).mean()).item() or 0.0) * 100.0
            if churn_column and churn_column in selected.columns
            else 0.0
        )
        profit_value = (
            selected.select(pl.col(profit_column).mean()).item() or 0.0
            if profit_column and profit_column in selected.columns
            else 0.0
        )
        complexity_penalty = len(spec.rule.blocks) * 0.5
        score = self._objective_value(
            metric_name=self.problem.objective_spec.primary_metric,
            approval_pp=approval_pp,
            risk_pct=risk_pct,
            profit_value=profit_value,
            churn_pct=churn_pct,
            complexity_penalty=complexity_penalty,
        )
        preserve_metric = self.problem.objective_spec.preserve_metric
        if preserve_metric:
            score -= self._preserve_penalty(
                metric_name=preserve_metric,
                approval_pp=approval_pp,
                risk_pct=risk_pct,
                profit_value=profit_value,
                churn_pct=churn_pct,
                complexity_penalty=complexity_penalty,
            )
        return round(score, 6)

    def _selected_subset(self, predicate: PredicateDefinition) -> pl.DataFrame:
        if predicate.field not in self.problem.snapshot.columns:
            return self.problem.snapshot.head(0)
        column = pl.col(predicate.field)
        if predicate.operator == Operator.GT:
            return self.problem.snapshot.filter(column > predicate.value)
        if predicate.operator == Operator.GTE:
            return self.problem.snapshot.filter(column >= predicate.value)
        if predicate.operator == Operator.LT:
            return self.problem.snapshot.filter(column < predicate.value)
        if predicate.operator == Operator.LTE:
            return self.problem.snapshot.filter(column <= predicate.value)
        if predicate.operator == Operator.EQ:
            return self.problem.snapshot.filter(column == predicate.value)
        if predicate.operator == Operator.NE:
            return self.problem.snapshot.filter(column != predicate.value)
        return self.problem.snapshot

    def _selected_subset_for_rule(self, rule: DecisionRuleDefinition) -> pl.DataFrame:
        if not rule.blocks:
            return self.problem.snapshot.head(0)
        return self.problem.snapshot.filter(self._rule_expression(rule))

    def _rule_expression(self, rule: DecisionRuleDefinition) -> pl.Expr:
        return self._combine_expressions(
            [self._block_expression(block) for block in rule.blocks],
            rule.block_combiner,
        )

    def _block_expression(self, block: RuleBlockDefinition) -> pl.Expr:
        return self._combine_expressions(
            [self._predicate_expression(predicate) for predicate in block.predicates],
            block.logical_operator,
        )

    def _predicate_expression(self, predicate: PredicateDefinition) -> pl.Expr:
        if predicate.field not in self.problem.snapshot.columns:
            return pl.lit(False)
        column = pl.col(predicate.field)
        if predicate.operator == Operator.GT:
            return column > predicate.value
        if predicate.operator == Operator.GTE:
            return column >= predicate.value
        if predicate.operator == Operator.LT:
            return column < predicate.value
        if predicate.operator == Operator.LTE:
            return column <= predicate.value
        if predicate.operator == Operator.EQ:
            return column == predicate.value
        if predicate.operator == Operator.NE:
            return column != predicate.value
        if predicate.operator == Operator.IN:
            return column.is_in(predicate.value)
        if predicate.operator == Operator.NOT_IN:
            return ~column.is_in(predicate.value)
        return pl.lit(False)

    def _combine_expressions(
        self,
        expressions: list[pl.Expr],
        logical_operator: LogicalOperator,
    ) -> pl.Expr:
        if not expressions:
            return pl.lit(True)
        combined = expressions[0]
        for expression in expressions[1:]:
            combined = (
                combined | expression
                if logical_operator == LogicalOperator.ANY
                else combined & expression
            )
        return combined

    def _supports_composite_rule(self, spec: RuleCandidateSpec) -> bool:
        if "composite_rule_candidate" in spec.tags:
            return False
        if len(spec.rule.blocks) != 1 or len(spec.rule.blocks[0].predicates) != 1:
            return False
        predicate = spec.rule.blocks[0].predicates[0]
        return predicate.field in self.problem.snapshot.columns

    def _supports_signal_bundle(self, spec: RuleCandidateSpec) -> bool:
        if "signal_bundle_candidate" in spec.tags:
            return False
        if len(spec.rule.blocks) != 1 or len(spec.rule.blocks[0].predicates) != 1:
            return False
        predicate = spec.rule.blocks[0].predicates[0]
        return (
            predicate.field in self.problem.snapshot.columns
            and predicate.operator in {Operator.EQ, Operator.IN}
            and _is_low_cardinality(
                self.problem.snapshot.schema.get(predicate.field),
                self.problem.snapshot[predicate.field],
            )
        )

    def _supports_layered_numeric_spec(self, spec: RuleCandidateSpec) -> bool:
        if len(spec.rule.blocks) != 1 or len(spec.rule.blocks[0].predicates) != 1:
            return False
        predicate = spec.rule.blocks[0].predicates[0]
        dtype = self.problem.snapshot.schema.get(predicate.field)
        return (
            predicate.field in self.problem.snapshot.columns
            and _is_numeric_dtype(dtype)
            and predicate.operator in {Operator.GT, Operator.GTE, Operator.LT, Operator.LTE}
        )

    def _supports_layered_signal_spec(self, spec: RuleCandidateSpec) -> bool:
        return "signal_bundle_candidate" in spec.tags and len(spec.rule.blocks) == 1

    def _spec_candidate_kind(self, spec: RuleCandidateSpec) -> str:
        if "policy_pack_candidate" in spec.tags:
            return "policy_pack_candidate"
        if "guarded_rule_candidate" in spec.tags:
            return "guarded_rule_candidate"
        if "grouped_rule_candidate" in spec.tags:
            return "grouped_rule_candidate"
        if "rule_bundle_candidate" in spec.tags:
            return "rule_bundle_candidate"
        if "layered_rule_candidate" in spec.tags:
            return "layered_rule_candidate"
        if "signal_bundle_candidate" in spec.tags:
            return "signal_bundle_candidate"
        if "composite_rule_candidate" in spec.tags:
            return "composite_rule_candidate"
        return "simple_rule_candidate"

    def _bundle_compatible_specs(
        self,
        specs: list[RuleCandidateSpec] | tuple[RuleCandidateSpec, ...],
    ) -> bool:
        if len(specs) < 2:
            return False
        decisions = {spec.rule.decision for spec in specs}
        if len(decisions) != 1:
            return False
        used_fields: set[str] = set()
        for spec in specs:
            fields = {
                predicate.field
                for block in spec.rule.blocks
                for predicate in block.predicates
            }
            if used_fields & fields:
                return False
            used_fields.update(fields)
        return True

    def _heuristic_candidate_kind(
        self,
        *,
        overrides: dict[str, float | int],
        added_rule_specs: list[RuleCandidateSpec],
        added_rules: list[str],
    ) -> str:
        has_feature_veto = any(summary.startswith("reject when ") for summary in added_rules)
        if not overrides and not has_feature_veto:
            if len(added_rule_specs) > 1:
                return "rule_bundle_candidate"
            if len(added_rule_specs) == 1:
                return self._spec_candidate_kind(added_rule_specs[0])
        if not overrides and has_feature_veto and len(added_rule_specs) > 1:
            return "policy_pack_candidate"
        if not overrides and has_feature_veto and added_rule_specs:
            return "guarded_rule_candidate"
        return "mixed_candidate"

    def _candidate_veto_features(
        self,
        *,
        allow_with_positive_rule: bool = False,
    ) -> list[DerivedFeatureDefinition]:
        if (
            not allow_with_positive_rule
            and not (
                self.problem.policy.rules
                or self.problem.policy.default_decision != "reject"
            )
        ):
            return []
        allowed_ids = set(self.problem.search_defaults.get("feature_candidates", []))
        return [
            feature
            for feature in self.problem.derived_features
            if feature.feature_id in allowed_ids
        ]

    def _objective_value(
        self,
        *,
        metric_name: str,
        approval_pp: float,
        risk_pct: float,
        profit_value: float,
        churn_pct: float,
        complexity_penalty: float,
    ) -> float:
        if metric_name == "risk":
            return approval_pp - (risk_pct * 1.5) - complexity_penalty
        if metric_name == "profit_index":
            return profit_value + (approval_pp * 0.1) - complexity_penalty
        if metric_name == "churn":
            return approval_pp - (churn_pct * 1.5) - complexity_penalty
        if metric_name == "complexity":
            return approval_pp - (complexity_penalty * 10.0)
        return approval_pp + (profit_value * 0.1) - risk_pct - complexity_penalty

    def _preserve_penalty(
        self,
        *,
        metric_name: str,
        approval_pp: float,
        risk_pct: float,
        profit_value: float,
        churn_pct: float,
        complexity_penalty: float,
    ) -> float:
        tolerance = self.problem.objective_spec.max_degradation or 0.0
        if metric_name == "risk":
            return max(risk_pct - tolerance, 0.0) * 2.0
        if metric_name == "churn":
            return max(churn_pct - tolerance, 0.0) * 2.0
        if metric_name == "profit_index":
            return max(tolerance - profit_value, 0.0) * 0.1
        if metric_name == "complexity":
            return max(complexity_penalty - tolerance, 0.0) * 2.0
        return max(tolerance - approval_pp, 0.0)

    def _baseline_for_new_field(self, field_name: str) -> float | int:
        series = self.problem.snapshot[field_name]
        median_value = series.median()
        if median_value is None:
            return 0
        if _is_integral_dtype(self.problem.snapshot.schema.get(field_name)):
            return int(round(float(median_value)))
        return round(float(median_value), 4)

    def _build_simple_rule(
        self,
        *,
        field_name: str,
        operator: Operator,
        value: Any,
        decision: str,
        existing_rule_ids: set[str],
    ) -> DecisionRuleDefinition:
        rule_id = f"candidate-{field_name}-{_operator_slug(operator)}"
        if value is not None:
            rule_id = f"{rule_id}-{_slug_value(value)}"
        if decision:
            rule_id = f"{rule_id}-{decision}"
        rule_id = _unique_rule_id(rule_id, existing_rule_ids)
        predicate = PredicateDefinition(field=field_name, operator=operator, value=value)
        return DecisionRuleDefinition(
            rule_id=rule_id,
            name=f"{decision} when {field_name} {operator.value} {value}",
            decision=decision,
            description="Simple rule candidate generated automatically.",
            block_combiner=LogicalOperator.ALL,
            blocks=[
                RuleBlockDefinition(
                    block_id=f"{rule_id}-block",
                    name=f"{field_name} candidate block",
                    logical_operator=LogicalOperator.ALL,
                    predicates=[predicate],
                )
            ],
        )

    def _bounded_range(
        self,
        *,
        column: pl.Series,
        baseline_value: float | int,
        config: dict[str, Any],
    ) -> tuple[float, float]:
        lower_quantile = float(config.get("range_lower_quantile", 0.1))
        upper_quantile = float(config.get("range_upper_quantile", 0.9))
        lower = column.quantile(lower_quantile) or baseline_value
        upper = column.quantile(upper_quantile) or baseline_value
        lower = float(config.get("min_value", lower))
        upper = float(config.get("max_value", upper))
        return float(lower), float(upper)

    def _shift_candidates(
        self,
        *,
        baseline_value: float | int,
        lower: float,
        upper: float,
        config: dict[str, Any],
    ) -> list[float | int]:
        if isinstance(baseline_value, int):
            shifts = config.get("integer_shifts", [-40, -20, 20, 40])
            return [
                int(max(min(int(baseline_value + shift), int(upper)), int(lower)))
                for shift in shifts
            ]
        shifts = config.get("float_shifts", [-0.08, -0.04, 0.04, 0.08])
        return [
            round(min(max(float(baseline_value + shift), lower), upper), 4)
            for shift in shifts
        ]

    def _quantile_candidates(
        self,
        *,
        column: pl.Series,
        lower: float,
        upper: float,
        config: dict[str, Any],
        baseline_value: float | int,
    ) -> list[float | int]:
        quantiles = config.get("candidate_quantiles", [0.1, 0.5, 0.9])
        values: list[float | int] = []
        for quantile in quantiles:
            observed = column.quantile(float(quantile))
            if observed is None:
                continue
            values.append(
                _coerce_numeric_candidate(
                    observed,
                    baseline_value=baseline_value,
                    lower=lower,
                    upper=upper,
                )
            )
        return values

    def _grid_candidates(
        self,
        *,
        lower: float,
        upper: float,
        config: dict[str, Any],
        baseline_value: float | int,
    ) -> list[float | int]:
        explicit_values = config.get("grid_values")
        if isinstance(explicit_values, list) and explicit_values:
            return [
                _coerce_numeric_candidate(
                    value,
                    baseline_value=baseline_value,
                    lower=lower,
                    upper=upper,
                )
                for value in explicit_values
            ]

        grid_size = int(config.get("grid_size", 0) or 0)
        if grid_size < 2 or lower == upper:
            return []

        step = (upper - lower) / (grid_size - 1)
        return [
            _coerce_numeric_candidate(
                lower + (step * index),
                baseline_value=baseline_value,
                lower=lower,
                upper=upper,
            )
            for index in range(grid_size)
        ]

    def _observed_value_candidates(
        self,
        *,
        column: pl.Series,
        lower: float,
        upper: float,
        config: dict[str, Any],
        baseline_value: float | int,
    ) -> list[float | int]:
        sample_size = int(config.get("observed_sample_size", 0) or 0)
        if sample_size <= 0:
            return []

        unique_values = sorted(
            {
                float(value)
                for value in column.drop_nulls().to_list()
                if value is not None and lower <= float(value) <= upper
            }
        )
        if not unique_values:
            return []
        if len(unique_values) <= sample_size:
            selected = unique_values
        else:
            selected = [
                unique_values[
                    round((len(unique_values) - 1) * index / (sample_size - 1))
                ]
                for index in range(sample_size)
            ]
        return [
            _coerce_numeric_candidate(
                value,
                baseline_value=baseline_value,
                lower=lower,
                upper=upper,
            )
            for value in selected
        ]


class ParameterSweepStrategyEngine:
    def generate(
        self,
        problem: SearchProblem,
        generator: CandidateGenerator,
    ) -> list[ScenarioDefinition]:
        _ = problem
        return generator.parameter_sweep_candidates()


class GuidedSearchStrategyEngine:
    def generate(
        self,
        problem: SearchProblem,
        generator: CandidateGenerator,
    ) -> list[ScenarioDefinition]:
        _ = problem
        return deduplicate_candidates(
            generator.parameter_sweep_candidates() + generator.guided_candidates()
        )


class HeuristicSearchStrategyEngine:
    def generate(
        self,
        problem: SearchProblem,
        generator: CandidateGenerator,
    ) -> list[ScenarioDefinition]:
        _ = problem
        return deduplicate_candidates(
            generator.parameter_sweep_candidates() + generator.heuristic_candidates()
        )


class SimulatedAnnealingSeedStrategyEngine:
    def generate(
        self,
        problem: SearchProblem,
        generator: CandidateGenerator,
    ) -> list[ScenarioDefinition]:
        _ = problem
        return generator.annealing_seed_candidates()


class PolicyOptimizer:
    def __init__(self) -> None:
        self._strategy_engines: dict[SearchStrategy, SearchStrategyEngine] = {
            SearchStrategy.PARAMETER_SWEEP: ParameterSweepStrategyEngine(),
            SearchStrategy.GUIDED_SEARCH: GuidedSearchStrategyEngine(),
            SearchStrategy.HEURISTIC_SEARCH: HeuristicSearchStrategyEngine(),
            SearchStrategy.SIMULATED_ANNEALING: SimulatedAnnealingSeedStrategyEngine(),
        }

    def generate_candidates(
        self,
        policy: PolicyDefinition,
        snapshot: pl.DataFrame,
        *,
        derived_features: list[DerivedFeatureDefinition],
        strategy: SearchStrategy,
        search_defaults: dict[str, Any],
        analysis_feature_columns: list[str] | None = None,
        performance_columns: dict[str, str] | None = None,
        objective_spec: SearchObjectiveSpec | None = None,
    ) -> list[ScenarioDefinition]:
        problem = SearchProblem(
            policy=policy,
            snapshot=snapshot,
            derived_features=derived_features,
            search_defaults=search_defaults,
            analysis_feature_columns=analysis_feature_columns or [],
            performance_columns=performance_columns or {},
            objective_spec=objective_spec or SearchObjectiveSpec(),
        )
        generator = CandidateGenerator(problem)
        engine = self._strategy_engines[strategy]
        return engine.generate(problem, generator)

    def generate_simulated_annealing_seed_candidates(
        self,
        policy: PolicyDefinition,
        snapshot: pl.DataFrame,
        *,
        derived_features: list[DerivedFeatureDefinition],
        search_defaults: dict[str, Any],
        analysis_feature_columns: list[str] | None = None,
        performance_columns: dict[str, str] | None = None,
        objective_spec: SearchObjectiveSpec | None = None,
    ) -> list[ScenarioDefinition]:
        problem = SearchProblem(
            policy=policy,
            snapshot=snapshot,
            derived_features=derived_features,
            search_defaults=search_defaults,
            analysis_feature_columns=analysis_feature_columns or [],
            performance_columns=performance_columns or {},
            objective_spec=objective_spec or SearchObjectiveSpec(),
        )
        return CandidateGenerator(problem).annealing_seed_candidates()

    def generate_simulated_annealing_neighbors(
        self,
        policy: PolicyDefinition,
        snapshot: pl.DataFrame,
        *,
        derived_features: list[DerivedFeatureDefinition],
        search_defaults: dict[str, Any],
        analysis_feature_columns: list[str] | None = None,
        performance_columns: dict[str, str] | None = None,
        objective_spec: SearchObjectiveSpec | None = None,
        random_seed: int | None = None,
    ) -> list[ScenarioDefinition]:
        problem = SearchProblem(
            policy=policy,
            snapshot=snapshot,
            derived_features=derived_features,
            search_defaults=search_defaults,
            analysis_feature_columns=analysis_feature_columns or [],
            performance_columns=performance_columns or {},
            objective_spec=objective_spec or SearchObjectiveSpec(),
        )
        randomizer = Random(random_seed or int(search_defaults.get("seed", 17) or 17))
        return CandidateGenerator(problem).annealing_neighbor_candidates(randomizer)

    def _candidate_thresholds(
        self,
        *,
        field_name: str | None = None,
        column: pl.Series,
        baseline_value: float | int,
        search_defaults: dict[str, Any],
    ) -> list[float | int]:
        problem = SearchProblem(
            policy=PolicyDefinition(
                policy_id="cutoff-preview",
                name="Cutoff preview",
                version="v0",
                decision_column="decision",
                default_decision="reject",
                rules=[],
            ),
            snapshot=pl.DataFrame({field_name or "__field__": column}),
            derived_features=[],
            search_defaults=search_defaults,
            analysis_feature_columns=[field_name or "__field__"],
            performance_columns={},
            objective_spec=SearchObjectiveSpec(),
        )
        generator = CandidateGenerator(problem)
        return generator.threshold_candidates(
            field_name=field_name or "__field__",
            column=column,
            baseline_value=baseline_value,
        )


def deduplicate_candidates(
    candidates: list[ScenarioDefinition],
) -> list[ScenarioDefinition]:
    unique: dict[str, ScenarioDefinition] = {}
    for candidate in candidates:
        key = _candidate_policy_key(candidate)
        existing = unique.get(key)
        if existing is None or _candidate_preference_rank(candidate) < _candidate_preference_rank(
            existing
        ):
            unique[key] = candidate
    return list(unique.values())


def _candidate_policy_key(candidate: ScenarioDefinition) -> str:
    policy_payload = candidate.policy.to_dict()
    metadata = dict(policy_payload.get("metadata") or {})
    metadata.pop("search_details", None)
    policy_payload["metadata"] = metadata
    payload = {
        "policy": policy_payload,
        "feature_ids": sorted(candidate.feature_ids),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _candidate_preference_rank(candidate: ScenarioDefinition) -> tuple[int, int, str]:
    candidate_kind = (
        candidate.policy.metadata.get("search_details", {}).get("candidate_kind", "")
    )
    priority = {
        "threshold_override": 0,
        "simple_rule_candidate": 1,
        "grouped_rule_candidate": 2,
        "layered_rule_candidate": 3,
        "guarded_rule_candidate": 4,
        "composite_rule_candidate": 5,
        "signal_bundle_candidate": 6,
        "rule_bundle_candidate": 7,
        "policy_pack_candidate": 8,
        "derived_veto": 9,
        "threshold_pair": 10,
        "mixed_candidate": 11,
    }
    return (
        priority.get(candidate_kind, 99),
        len(candidate.policy.rules),
        candidate.scenario_id,
    )


def _coerce_numeric_candidate(
    value: float | int,
    *,
    baseline_value: float | int,
    lower: float,
    upper: float,
) -> float | int:
    bounded = min(max(float(value), lower), upper)
    if isinstance(baseline_value, int):
        return int(round(bounded))
    return round(bounded, 4)


def _spread_values(values: list[float | int], limit: int) -> list[float | int]:
    unique_values = list(dict.fromkeys(values))
    if limit <= 0 or len(unique_values) <= limit:
        return unique_values
    return [
        unique_values[round((len(unique_values) - 1) * index / (limit - 1))]
        for index in range(limit)
    ]


def _spread_rule_specs(
    specs: list[RuleCandidateSpec],
    *,
    limit: int,
) -> list[RuleCandidateSpec]:
    if limit <= 0 or len(specs) <= limit:
        return specs
    if limit == 1:
        return [specs[0]]
    return [
        specs[round((len(specs) - 1) * index / (limit - 1))]
        for index in range(limit)
    ]


def _unique_rule_id(base: str, existing_rule_ids: set[str]) -> str:
    candidate = base
    suffix = 2
    while candidate in existing_rule_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _operator_slug(operator: Operator) -> str:
    mapping = {
        Operator.GT: "gt",
        Operator.GTE: "gte",
        Operator.LT: "lt",
        Operator.LTE: "lte",
        Operator.EQ: "eq",
        Operator.NE: "ne",
        Operator.IN: "in",
        Operator.NOT_IN: "not-in",
    }
    return mapping[operator]


def _slug_value(value: float | int | str) -> str:
    return str(value).replace(".", "_").replace("-", "m")


def _is_numeric_dtype(dtype: pl.DataType | None) -> bool:
    return bool(dtype is not None and getattr(dtype, "is_numeric", lambda: False)())


def _is_integral_dtype(dtype: pl.DataType | None) -> bool:
    integral_types = {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    }
    return dtype in integral_types


def _is_low_cardinality(dtype: pl.DataType | None, column: pl.Series) -> bool:
    if dtype is None:
        return False
    if _is_numeric_dtype(dtype) and not _is_integral_dtype(dtype):
        return False
    return column.n_unique() <= 6
