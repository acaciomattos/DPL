from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
import json
from math import exp
from random import Random

import polars as pl

from policy_lab.analysis.complexity_estimator import ComplexityEstimator
from policy_lab.analysis.impact_estimator import ImpactEstimator
from policy_lab.analysis.uncertainty_estimator import UncertaintyEstimator
from policy_lab.domain import (
    PolicyDefinition,
    ScenarioDefinition,
    ScenarioMetrics,
    ScenarioResult,
    SearchObjectiveSpec,
    SearchStrategy,
    StudyContext,
)
from policy_lab.engine.counterfactual_engine import CounterfactualEngine
from policy_lab.engine.feature_resolution import FeatureResolver
from policy_lab.engine.optimizer import PolicyOptimizer
from policy_lab.engine.policy_executor import PolicyExecutor
from policy_lab.storage.feature_repository import FeatureRepository
from policy_lab.storage.result_repository import ResultRepository
from policy_lab.storage.scenario_repository import ScenarioRepository
from policy_lab.storage.studies_repository import StudyRepository


@dataclass(slots=True)
class ScenarioRunBundle:
    result: ScenarioResult
    frame: pl.DataFrame | None


@dataclass(slots=True)
class SearchCandidateEvaluation:
    scenario: ScenarioDefinition
    bundle: ScenarioRunBundle


@dataclass(slots=True)
class RankedSearchCandidate:
    scenario: ScenarioDefinition
    result: ScenarioResult
    score: float
    passes_gate: bool


class SearchObjectiveEvaluator:
    def evaluate(
        self,
        result: ScenarioResult,
        reference_result: ScenarioResult,
        *,
        objective_spec: SearchObjectiveSpec,
        constraint_reference_result: ScenarioResult | None = None,
        search_defaults: dict[str, float | int | dict[str, float] | list[float] | str],
    ) -> dict[str, float | dict[str, float]]:
        weights = search_defaults.get("objective_weights", {})
        if not isinstance(weights, dict):
            weights = {}
        support_weight = float(weights.get("support_penalty", 120.0))
        complexity_weight = float(weights.get("complexity_penalty", 0.12))

        constraint_reference_result = constraint_reference_result or reference_result
        primary_gain = self._metric_gain(
            metric_name=objective_spec.primary_metric,
            direction=objective_spec.direction,
            result=result,
            reference_result=reference_result,
        )
        support_penalty = (result.metrics.out_of_support_ratio or 0.0) * support_weight
        complexity_penalty = (
            0.0
            if objective_spec.primary_metric == "complexity"
            else (result.metrics.complexity_score or 0.0) * complexity_weight
        )
        constraint_delta = self._constraint_delta(
            objective_spec=objective_spec,
            result=result,
            reference_result=constraint_reference_result,
        )
        constraint_violated = (
            objective_spec.max_degradation is not None
            and constraint_delta is not None
            and constraint_delta > objective_spec.max_degradation
        )
        score = round(primary_gain - support_penalty - complexity_penalty, 4)
        return {
            "score": score,
            "components": {
                "primary_metric": objective_spec.primary_metric,
                "direction": objective_spec.direction,
                "primary_gain": round(primary_gain, 4),
                "preserve_metric": objective_spec.preserve_metric or "",
                "max_degradation": (
                    round(objective_spec.max_degradation, 4)
                    if objective_spec.max_degradation is not None
                    else None
                ),
                "constraint_delta": (
                    round(constraint_delta, 4) if constraint_delta is not None else None
                ),
                "constraint_violated": constraint_violated,
                "support_penalty": round(support_penalty, 4),
                "complexity_penalty": round(complexity_penalty, 4),
            },
        }

    def _metric_gain(
        self,
        *,
        metric_name: str,
        direction: str,
        result: ScenarioResult,
        reference_result: ScenarioResult,
    ) -> float:
        result_value = self._metric_value(result, metric_name)
        reference_value = self._metric_value(reference_result, metric_name)
        if direction == "minimize":
            return reference_value - result_value
        return result_value - reference_value

    def _constraint_delta(
        self,
        *,
        objective_spec: SearchObjectiveSpec,
        result: ScenarioResult,
        reference_result: ScenarioResult,
    ) -> float | None:
        metric_name = objective_spec.preserve_metric
        if not metric_name:
            return None
        result_value = self._metric_value(result, metric_name)
        reference_value = self._metric_value(reference_result, metric_name)
        if metric_name in {"approval", "profit_index"}:
            return max(reference_value - result_value, 0.0)
        return max(result_value - reference_value, 0.0)

    def _metric_value(self, result: ScenarioResult, metric_name: str) -> float:
        if metric_name == "approval":
            return (result.metrics.approval_rate or 0.0) * 100.0
        if metric_name == "risk":
            return (result.metrics.risk_estimate or 0.0) * 100.0
        if metric_name == "profit_index":
            return result.metrics.expected_profit_index or 0.0
        if metric_name == "churn":
            return (result.metrics.churn_estimate or 0.0) * 100.0
        if metric_name == "complexity":
            return result.metrics.complexity_score or 0.0
        return 0.0


class ScenarioOrchestrator:
    def __init__(
        self,
        study_repository: StudyRepository,
        feature_repository: FeatureRepository,
        scenario_repository: ScenarioRepository,
        result_repository: ResultRepository,
    ) -> None:
        self.study_repository = study_repository
        self.feature_repository = feature_repository
        self.scenario_repository = scenario_repository
        self.result_repository = result_repository
        self.feature_resolver = FeatureResolver()
        self.policy_executor = PolicyExecutor()
        self.counterfactual_engine = CounterfactualEngine()
        self.impact_estimator = ImpactEstimator()
        self.uncertainty_estimator = UncertaintyEstimator()
        self.complexity_estimator = ComplexityEstimator()
        self.optimizer = PolicyOptimizer()
        self.objective_evaluator = SearchObjectiveEvaluator()

    def run_baseline(self, study: StudyContext) -> ScenarioRunBundle:
        return self.run_baseline_with_snapshot(study)

    def run_baseline_with_snapshot(
        self,
        study: StudyContext,
        snapshot_override: pl.DataFrame | None = None,
    ) -> ScenarioRunBundle:
        snapshot = (
            snapshot_override
            if snapshot_override is not None
            else self.study_repository.load_snapshot(study)
        )
        features = self.feature_repository.load(study)
        enriched = self.feature_resolver.resolve(snapshot, features, [])
        executed = self.policy_executor.execute(enriched, study.manifest.baseline_policy)
        metrics = self.impact_estimator.estimate(
            executed,
            study.manifest.baseline_policy,
            performance_columns=study.manifest.snapshot.performance_columns,
        )
        out_of_support, uncertainty = self.uncertainty_estimator.estimate(
            executed,
            study.manifest.baseline_policy,
            reference_decision_column=study.manifest.snapshot.historical_decision_column,
        )
        metrics.out_of_support_ratio = out_of_support
        metrics.uncertainty_label = uncertainty
        metrics.complexity_score = self.complexity_estimator.estimate(
            study.manifest.baseline_policy
        )
        result = ScenarioResult(
            scenario_id="baseline",
            scenario_name="Baseline reproduction",
            policy_id=study.manifest.baseline_policy.policy_id,
            study_id=study.study_id,
            metrics=metrics,
            transitions=self.counterfactual_engine.transitions(
                executed,
                study.manifest.snapshot.historical_decision_column,
                study.manifest.baseline_policy.decision_column,
            ),
            decision_distribution=self.counterfactual_engine.distribution(
                executed,
                study.manifest.baseline_policy.decision_column,
            ),
            lineage={"type": "baseline"},
        )
        return ScenarioRunBundle(result=result, frame=executed)

    def run_scenario(
        self,
        study: StudyContext,
        scenario: ScenarioDefinition,
        *,
        baseline_bundle: ScenarioRunBundle | None = None,
        snapshot_override: pl.DataFrame | None = None,
        derived_features_override: list | None = None,
        profit_reference_expected_profit: float | None = None,
        include_frame: bool = True,
        save_artifacts: bool = True,
    ) -> ScenarioRunBundle:
        baseline_bundle = baseline_bundle or self.run_baseline_with_snapshot(
            study,
            snapshot_override=snapshot_override,
        )
        snapshot = (
            snapshot_override
            if snapshot_override is not None
            else self.study_repository.load_snapshot(study)
        )
        features = (
            derived_features_override
            if derived_features_override is not None
            else self.feature_repository.load(study)
        )
        enriched = self.feature_resolver.resolve(snapshot, features, scenario.feature_ids)
        executed = self.policy_executor.execute(enriched, scenario.policy)
        metrics = self.impact_estimator.estimate(
            executed,
            scenario.policy,
            baseline_expected_profit=(
                profit_reference_expected_profit
                if profit_reference_expected_profit is not None
                else baseline_bundle.result.metrics.expected_profit
            ),
            performance_columns=study.manifest.snapshot.performance_columns,
        )
        out_of_support, uncertainty = self.uncertainty_estimator.estimate(
            executed,
            scenario.policy,
            reference_decision_column=study.manifest.snapshot.historical_decision_column,
        )
        metrics.out_of_support_ratio = out_of_support
        metrics.uncertainty_label = uncertainty
        metrics.complexity_score = self.complexity_estimator.estimate(scenario.policy)

        entity_id = study.manifest.snapshot.entity_id_column
        comparison_frame = baseline_bundle.frame.select(
            [entity_id, study.manifest.baseline_policy.decision_column]
        ).join(
            executed.select([entity_id, scenario.policy.decision_column]),
            on=entity_id,
            suffix="_candidate",
        )
        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            policy_id=scenario.policy.policy_id,
            study_id=study.study_id,
            metrics=metrics,
            transitions=self.counterfactual_engine.transitions(
                comparison_frame,
                study.manifest.baseline_policy.decision_column,
                f"{scenario.policy.decision_column}_candidate",
            ),
            decision_distribution=self.counterfactual_engine.distribution(
                executed,
                scenario.policy.decision_column,
            ),
            lineage={
                "type": "scenario",
                "baseline_scenario_id": baseline_bundle.result.scenario_id,
                "feature_ids": scenario.feature_ids,
                "tags": scenario.tags,
                "search_details": scenario.policy.metadata.get("search_details", {}),
                "candidate_scenario": scenario.to_dict(),
            },
        )
        if save_artifacts:
            self.scenario_repository.save(study, scenario)
            self.result_repository.save(study, result)
        return ScenarioRunBundle(
            result=result,
            frame=executed if include_frame else None,
        )

    def run_search(
        self,
        study: StudyContext,
        *,
        strategy: SearchStrategy,
        baseline_bundle: ScenarioRunBundle | None = None,
        search_reference_bundle: ScenarioRunBundle | None = None,
        constraint_reference_bundle: ScenarioRunBundle | None = None,
        snapshot_override: pl.DataFrame | None = None,
        base_policy: PolicyDefinition | None = None,
        objective_spec: SearchObjectiveSpec | None = None,
    ) -> list[ScenarioResult]:
        baseline_bundle = baseline_bundle or self.run_baseline_with_snapshot(
            study,
            snapshot_override=snapshot_override,
        )
        search_reference_bundle = search_reference_bundle or baseline_bundle
        constraint_reference_bundle = constraint_reference_bundle or search_reference_bundle
        objective_spec = objective_spec or SearchObjectiveSpec()
        snapshot = (
            snapshot_override
            if snapshot_override is not None
            else self.study_repository.load_snapshot(study)
        )
        derived_features = self.feature_repository.load(study)
        search_policy = (
            PolicyDefinition.from_dict(base_policy.to_dict())
            if base_policy is not None
            else study.manifest.baseline_policy
        )
        if strategy == SearchStrategy.SIMULATED_ANNEALING:
            return self._run_simulated_annealing_search(
                study,
                baseline_bundle=baseline_bundle,
                search_reference_bundle=search_reference_bundle,
                constraint_reference_bundle=constraint_reference_bundle,
                snapshot=snapshot,
                derived_features=derived_features,
                search_policy=search_policy,
                objective_spec=objective_spec,
            )
        candidates = self.optimizer.generate_candidates(
            search_policy,
            snapshot,
            derived_features=derived_features,
            strategy=strategy,
            search_defaults=study.manifest.search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
            performance_columns=study.manifest.snapshot.performance_columns,
            objective_spec=objective_spec,
        )
        retained_results: list[tuple[ScenarioDefinition, ScenarioResult]] = []
        evaluations = self._evaluate_search_candidates(
            study,
            candidates,
            baseline_bundle=search_reference_bundle,
            snapshot=snapshot,
            derived_features=derived_features,
            profit_reference_expected_profit=baseline_bundle.result.metrics.expected_profit,
            search_defaults=study.manifest.search_defaults,
        )
        for evaluation in evaluations:
            ranked_candidate = self._rank_search_candidate(
                evaluation.scenario,
                evaluation.bundle.result,
                reference_result=search_reference_bundle.result,
                constraint_reference_result=constraint_reference_bundle.result,
                objective_spec=objective_spec,
                search_defaults=study.manifest.search_defaults,
            )
            if ranked_candidate is None or not ranked_candidate.passes_gate:
                continue
            retained_results.append((ranked_candidate.scenario, ranked_candidate.result))
        self._annotate_pareto_fronts([result for _, result in retained_results])
        ranked = sorted(
            retained_results,
            key=lambda item: (
                item[1].lineage.get("pareto_front", 999),
                -float(item[1].lineage.get("objective_performance", 0.0)),
            ),
        )
        selected = self._diversified_top_results(
            [result for _, result in ranked],
            top_k=study.manifest.search_defaults.get("top_k", 8),
        )
        selected_ids = {result.scenario_id for result in selected}
        for scenario, result in retained_results:
            if result.scenario_id not in selected_ids:
                continue
            self.scenario_repository.save(study, scenario)
            self.result_repository.save(study, result)
        return selected

    def _evaluate_search_candidates(
        self,
        study: StudyContext,
        candidates: list[ScenarioDefinition],
        *,
        baseline_bundle: ScenarioRunBundle,
        snapshot: pl.DataFrame,
        derived_features: list,
        profit_reference_expected_profit: float | None,
        search_defaults: dict[str, object],
    ) -> list[SearchCandidateEvaluation]:
        if not candidates:
            return []
        max_workers = _resolve_search_max_workers(
            search_defaults=search_defaults,
            candidate_count=len(candidates),
        )
        runner = partial(
            self.run_scenario,
            study,
            baseline_bundle=baseline_bundle,
            snapshot_override=snapshot,
            derived_features_override=derived_features,
            profit_reference_expected_profit=profit_reference_expected_profit,
            include_frame=False,
            save_artifacts=False,
        )
        if max_workers <= 1:
            return [
                SearchCandidateEvaluation(
                    scenario=candidate,
                    bundle=runner(candidate),
                )
                for candidate in candidates
            ]
        evaluations: list[SearchCandidateEvaluation] = []
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="search-eval",
        ) as executor:
            future_to_candidate = {
                executor.submit(runner, candidate): candidate for candidate in candidates
            }
            for future in as_completed(future_to_candidate):
                candidate = future_to_candidate[future]
                evaluations.append(
                    SearchCandidateEvaluation(
                        scenario=candidate,
                        bundle=future.result(),
                    )
                )
        return evaluations

    def _annotate_pareto_fronts(self, results: list[ScenarioResult]) -> None:
        for index, front in enumerate(_pareto_fronts(results), start=1):
            for result in front:
                result.lineage["pareto_front"] = index

    def _diversified_top_results(
        self,
        ranked_results: list[ScenarioResult],
        *,
        top_k: int,
    ) -> list[ScenarioResult]:
        selected: list[ScenarioResult] = []
        seen_ids: set[str] = set()
        seen_kinds: set[str] = set()

        for result in ranked_results:
            kind = (
                result.lineage.get("search_details", {}).get("candidate_kind")
                or "unknown"
            )
            if kind in seen_kinds:
                continue
            selected.append(result)
            seen_ids.add(result.scenario_id)
            seen_kinds.add(kind)
            if len(selected) >= top_k:
                return selected[:top_k]

        for result in ranked_results:
            if result.scenario_id in seen_ids:
                continue
            selected.append(result)
            if len(selected) >= top_k:
                break
        return selected[:top_k]

    def _is_effective_candidate(
        self,
        result: ScenarioResult,
        baseline_result: ScenarioResult,
    ) -> bool:
        approval_delta = abs(
            (result.metrics.approval_rate or 0.0)
            - (baseline_result.metrics.approval_rate or 0.0)
        )
        profit_index_delta = abs((result.metrics.expected_profit_index or 100.0) - 100.0)
        risk_delta = abs(
            (result.metrics.risk_estimate or 0.0)
            - (baseline_result.metrics.risk_estimate or 0.0)
        )
        support_delta = abs(
            (result.metrics.out_of_support_ratio or 0.0)
            - (baseline_result.metrics.out_of_support_ratio or 0.0)
        )
        same_distribution = (
            result.decision_distribution == baseline_result.decision_distribution
        )
        return not (
            same_distribution
            and approval_delta < 1e-9
            and profit_index_delta < 1e-9
            and risk_delta < 1e-9
            and support_delta < 1e-9
        )

    def _passes_progress_gate(
        self,
        result: ScenarioResult,
        reference_result: ScenarioResult,
        *,
        objective_spec: SearchObjectiveSpec,
        constraint_reference_result: ScenarioResult,
    ) -> bool:
        primary_gain = self.objective_evaluator._metric_gain(
            metric_name=objective_spec.primary_metric,
            direction=objective_spec.direction,
            result=result,
            reference_result=reference_result,
        )
        if primary_gain <= 0:
            return False

        if objective_spec.preserve_metric and objective_spec.max_degradation is not None:
            constraint_delta = self.objective_evaluator._constraint_delta(
                objective_spec=objective_spec,
                result=result,
                reference_result=constraint_reference_result,
            )
            if (
                constraint_delta is not None
                and constraint_delta > objective_spec.max_degradation
            ):
                return False
        return True

    def _run_simulated_annealing_search(
        self,
        study: StudyContext,
        *,
        baseline_bundle: ScenarioRunBundle,
        search_reference_bundle: ScenarioRunBundle,
        constraint_reference_bundle: ScenarioRunBundle,
        snapshot: pl.DataFrame,
        derived_features: list,
        search_policy: PolicyDefinition,
        objective_spec: SearchObjectiveSpec,
    ) -> list[ScenarioResult]:
        search_defaults = study.manifest.search_defaults
        randomizer = Random(int(search_defaults.get("seed", 17) or 17))
        temperature = float(
            search_defaults.get("annealing_initial_temperature", 1.25) or 1.25
        )
        cooling_rate = float(
            search_defaults.get("annealing_cooling_rate", 0.85) or 0.85
        )
        iterations = int(search_defaults.get("annealing_iterations", 10) or 10)
        seed_candidates = self.optimizer.generate_simulated_annealing_seed_candidates(
            search_policy,
            snapshot,
            derived_features=derived_features,
            search_defaults=search_defaults,
            analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
            performance_columns=study.manifest.snapshot.performance_columns,
            objective_spec=objective_spec,
        )
        seed_candidates = self._unique_annealing_candidates(
            seed_candidates,
            prefix="anneal-seed",
        )
        seed_evaluations = self._evaluate_search_candidates(
            study,
            seed_candidates,
            baseline_bundle=search_reference_bundle,
            snapshot=snapshot,
            derived_features=derived_features,
            profit_reference_expected_profit=baseline_bundle.result.metrics.expected_profit,
            search_defaults=search_defaults,
        )
        ranked_seed_candidates = [
            ranked
            for evaluation in seed_evaluations
            if (
                ranked := self._rank_search_candidate(
                    evaluation.scenario,
                    evaluation.bundle.result,
                    reference_result=search_reference_bundle.result,
                    constraint_reference_result=constraint_reference_bundle.result,
                    objective_spec=objective_spec,
                    search_defaults=search_defaults,
                )
            )
            is not None
        ]
        if not ranked_seed_candidates:
            return []

        current = max(ranked_seed_candidates, key=lambda item: item.score)
        best = current
        retained_candidates: dict[str, RankedSearchCandidate] = {}
        self._maybe_retain_ranked_candidate(retained_candidates, current)

        for iteration in range(1, iterations + 1):
            neighbors = self.optimizer.generate_simulated_annealing_neighbors(
                current.scenario.policy,
                snapshot,
                derived_features=derived_features,
                search_defaults=search_defaults,
                analysis_feature_columns=study.manifest.snapshot.analysis_feature_columns,
                performance_columns=study.manifest.snapshot.performance_columns,
                objective_spec=objective_spec,
                random_seed=randomizer.randint(0, 10_000_000),
            )
            neighbors = self._unique_annealing_candidates(
                neighbors,
                prefix=f"anneal-{iteration}",
            )
            if not neighbors:
                temperature *= cooling_rate
                continue
            neighbor_evaluations = self._evaluate_search_candidates(
                study,
                neighbors,
                baseline_bundle=search_reference_bundle,
                snapshot=snapshot,
                derived_features=derived_features,
                profit_reference_expected_profit=baseline_bundle.result.metrics.expected_profit,
                search_defaults=search_defaults,
            )
            ranked_neighbors = [
                ranked
                for evaluation in neighbor_evaluations
                if (
                    ranked := self._rank_search_candidate(
                        evaluation.scenario,
                        evaluation.bundle.result,
                        reference_result=search_reference_bundle.result,
                        constraint_reference_result=constraint_reference_bundle.result,
                        objective_spec=objective_spec,
                        search_defaults=search_defaults,
                    )
                )
                is not None
            ]
            if not ranked_neighbors:
                temperature *= cooling_rate
                continue

            proposed = randomizer.choice(ranked_neighbors)
            delta = proposed.score - current.score
            acceptance_probability = (
                1.0 if delta >= 0 else exp(delta / max(temperature, 1e-9))
            )
            proposed.result.lineage["annealing"] = {
                "iteration": iteration,
                "temperature": round(temperature, 6),
                "delta": round(delta, 6),
                "acceptance_probability": round(acceptance_probability, 6),
                "accepted": False,
            }
            if delta >= 0 or randomizer.random() < acceptance_probability:
                proposed.result.lineage["annealing"]["accepted"] = True
                current = proposed
            if proposed.score > best.score:
                best = proposed
            self._maybe_retain_ranked_candidate(retained_candidates, proposed)
            temperature *= cooling_rate

        self._maybe_retain_ranked_candidate(retained_candidates, best)
        retained_pairs = [
            (candidate.scenario, candidate.result)
            for candidate in retained_candidates.values()
            if candidate.passes_gate
        ]
        if not retained_pairs:
            retained_pairs = [(best.scenario, best.result)]
        self._annotate_pareto_fronts([result for _, result in retained_pairs])
        ranked = sorted(
            retained_pairs,
            key=lambda item: (
                item[1].lineage.get("pareto_front", 999),
                -float(item[1].lineage.get("objective_performance", 0.0)),
            ),
        )
        selected = self._diversified_top_results(
            [result for _, result in ranked],
            top_k=study.manifest.search_defaults.get("top_k", 8),
        )
        selected_ids = {result.scenario_id for result in selected}
        for scenario, result in retained_pairs:
            if result.scenario_id not in selected_ids:
                continue
            self.scenario_repository.save(study, scenario)
            self.result_repository.save(study, result)
        return selected

    def _rank_search_candidate(
        self,
        scenario: ScenarioDefinition,
        result: ScenarioResult,
        *,
        reference_result: ScenarioResult,
        constraint_reference_result: ScenarioResult,
        objective_spec: SearchObjectiveSpec,
        search_defaults: dict[str, object],
    ) -> RankedSearchCandidate | None:
        if not self._is_effective_candidate(result, reference_result):
            return None
        objective_evaluation = self.objective_evaluator.evaluate(
            result,
            reference_result,
            objective_spec=objective_spec,
            constraint_reference_result=constraint_reference_result,
            search_defaults=search_defaults,
        )
        result.lineage["objective_performance"] = objective_evaluation["score"]
        result.lineage["objective_performance_details"] = objective_evaluation["components"]
        result.lineage["objective_spec"] = objective_spec.to_dict()
        passes_gate = self._passes_progress_gate(
            result,
            reference_result,
            objective_spec=objective_spec,
            constraint_reference_result=constraint_reference_result,
        )
        return RankedSearchCandidate(
            scenario=scenario,
            result=result,
            score=float(objective_evaluation["score"]),
            passes_gate=passes_gate,
        )

    def _unique_annealing_candidates(
        self,
        candidates: list[ScenarioDefinition],
        *,
        prefix: str,
    ) -> list[ScenarioDefinition]:
        unique: list[ScenarioDefinition] = []
        for index, candidate in enumerate(candidates, start=1):
            scenario = ScenarioDefinition.from_dict(candidate.to_dict())
            scenario.scenario_id = f"{prefix}-{index}"
            unique.append(scenario)
        return unique

    def _maybe_retain_ranked_candidate(
        self,
        retained_candidates: dict[str, RankedSearchCandidate],
        candidate: RankedSearchCandidate,
    ) -> None:
        key = _search_candidate_key(candidate.scenario)
        existing = retained_candidates.get(key)
        if existing is None or candidate.score > existing.score:
            retained_candidates[key] = candidate


def _resolve_search_max_workers(
    *,
    search_defaults: dict[str, object],
    candidate_count: int,
) -> int:
    configured = search_defaults.get("search_parallel_workers", 0)
    try:
        configured_workers = int(configured)
    except (TypeError, ValueError):
        configured_workers = 0
    if configured_workers <= 0:
        cpu_bound_default = max((os.cpu_count() or 2) // 2, 1)
        configured_workers = min(4, cpu_bound_default)
    return max(1, min(candidate_count, configured_workers))


def _search_candidate_key(scenario: ScenarioDefinition) -> str:
    policy_payload = scenario.policy.to_dict()
    metadata = dict(policy_payload.get("metadata") or {})
    metadata.pop("search_details", None)
    policy_payload["metadata"] = metadata
    payload = {
        "policy": policy_payload,
        "feature_ids": sorted(scenario.feature_ids),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _pareto_fronts(results: list[ScenarioResult]) -> list[list[ScenarioResult]]:
    remaining = list(results)
    fronts: list[list[ScenarioResult]] = []
    while remaining:
        front: list[ScenarioResult] = []
        for candidate in remaining:
            if not any(
                _pareto_dominates(other.metrics, candidate.metrics)
                for other in remaining
                if other.scenario_id != candidate.scenario_id
            ):
                front.append(candidate)
        if not front:
            break
        fronts.append(front)
        front_ids = {result.scenario_id for result in front}
        remaining = [
            candidate
            for candidate in remaining
            if candidate.scenario_id not in front_ids
        ]
    if remaining:
        fronts.append(remaining)
    return fronts


def _pareto_dominates(left: ScenarioMetrics, right: ScenarioMetrics) -> bool:
    comparisons = [
        (
            _safe_metric(left.approval_rate, maximize=True),
            _safe_metric(right.approval_rate, maximize=True),
        ),
        (
            _safe_metric(left.expected_profit_index, maximize=True),
            _safe_metric(right.expected_profit_index, maximize=True),
        ),
        (
            _safe_metric(left.risk_estimate, maximize=False),
            _safe_metric(right.risk_estimate, maximize=False),
        ),
        (
            _safe_metric(left.churn_estimate, maximize=False),
            _safe_metric(right.churn_estimate, maximize=False),
        ),
        (
            _safe_metric(left.out_of_support_ratio, maximize=False),
            _safe_metric(right.out_of_support_ratio, maximize=False),
        ),
        (
            _safe_metric(left.complexity_score, maximize=False),
            _safe_metric(right.complexity_score, maximize=False),
        ),
    ]
    no_worse = all(left_value >= right_value for left_value, right_value in comparisons)
    strictly_better = any(
        left_value > right_value + 1e-12 for left_value, right_value in comparisons
    )
    return no_worse and strictly_better


def _safe_metric(value: float | None, *, maximize: bool) -> float:
    if value is None:
        return float("-inf") if maximize else float("-inf")
    return value if maximize else -value
