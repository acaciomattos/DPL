from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Operator(str, Enum):
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NE = "!="
    IN = "in"
    NOT_IN = "not_in"


class LogicalOperator(str, Enum):
    ALL = "all"
    ANY = "any"


class FeatureMode(str, Enum):
    VIRTUAL = "virtual"
    MATERIALIZED = "materialized"


class SearchStrategy(str, Enum):
    PARAMETER_SWEEP = "parameter_sweep"
    GUIDED_SEARCH = "guided_search"
    HEURISTIC_SEARCH = "heuristic_search"
    SIMULATED_ANNEALING = "simulated_annealing"


@dataclass(slots=True)
class SearchObjectiveSpec:
    primary_metric: str = "approval"
    direction: str = "maximize"
    preserve_metric: str | None = "risk"
    max_degradation: float | None = 2.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> SearchObjectiveSpec:
        data = dict(payload or {})
        return cls(
            primary_metric=str(data.get("primary_metric", "approval")),
            direction=str(data.get("direction", "maximize")),
            preserve_metric=(
                str(data["preserve_metric"])
                if data.get("preserve_metric") not in (None, "", "none")
                else None
            ),
            max_degradation=(
                float(data["max_degradation"])
                if data.get("max_degradation") not in (None, "")
                else None
            ),
        )


@dataclass(slots=True)
class Workspace:
    workspace_id: str
    name: str
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Workspace:
        return cls(**payload)


@dataclass(slots=True)
class PolicyFamily:
    policy_family_id: str
    name: str
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PolicyFamily:
        return cls(**payload)


@dataclass(slots=True)
class StudySnapshotDefinition:
    file_name: str
    format: str
    entity_id_column: str
    historical_decision_column: str
    outcome_columns: list[str]
    metadata_columns: list[str] = field(default_factory=list)
    date_column: str | None = None
    analysis_feature_columns: list[str] = field(default_factory=list)
    performance_columns: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StudySnapshotDefinition:
        return cls(**payload)


@dataclass(slots=True)
class DerivedFeatureDefinition:
    feature_id: str
    name: str
    expression: str
    dependencies: list[str]
    data_type: str = "float"
    mode: FeatureMode = FeatureMode.VIRTUAL
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DerivedFeatureDefinition:
        data = dict(payload)
        data["mode"] = FeatureMode(data.get("mode", FeatureMode.VIRTUAL.value))
        return cls(**data)


@dataclass(slots=True)
class PredicateDefinition:
    field: str
    operator: Operator
    value: Any
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operator"] = self.operator.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PredicateDefinition:
        data = dict(payload)
        data["operator"] = Operator(data["operator"])
        return cls(**data)


@dataclass(slots=True)
class RuleBlockDefinition:
    block_id: str
    name: str
    predicates: list[PredicateDefinition]
    logical_operator: LogicalOperator = LogicalOperator.ALL

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["logical_operator"] = self.logical_operator.value
        payload["predicates"] = [predicate.to_dict() for predicate in self.predicates]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RuleBlockDefinition:
        data = dict(payload)
        data["logical_operator"] = LogicalOperator(
            data.get("logical_operator", LogicalOperator.ALL.value)
        )
        data["predicates"] = [
            PredicateDefinition.from_dict(predicate)
            for predicate in data.get("predicates", [])
        ]
        return cls(**data)


@dataclass(slots=True)
class DecisionRuleDefinition:
    rule_id: str
    name: str
    decision: str
    blocks: list[RuleBlockDefinition]
    block_combiner: LogicalOperator = LogicalOperator.ALL
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["block_combiner"] = self.block_combiner.value
        payload["blocks"] = [block.to_dict() for block in self.blocks]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DecisionRuleDefinition:
        data = dict(payload)
        data["block_combiner"] = LogicalOperator(
            data.get("block_combiner", LogicalOperator.ALL.value)
        )
        data["blocks"] = [
            RuleBlockDefinition.from_dict(block) for block in data.get("blocks", [])
        ]
        return cls(**data)


@dataclass(slots=True)
class PolicyDefinition:
    policy_id: str
    name: str
    version: str
    decision_column: str
    default_decision: str
    rules: list[DecisionRuleDefinition]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rules"] = [rule.to_dict() for rule in self.rules]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PolicyDefinition:
        data = dict(payload)
        data["rules"] = [
            DecisionRuleDefinition.from_dict(rule) for rule in data.get("rules", [])
        ]
        return cls(**data)

    def iter_predicates(self) -> list[PredicateDefinition]:
        predicates: list[PredicateDefinition] = []
        for rule in self.rules:
            for block in rule.blocks:
                predicates.extend(block.predicates)
        return predicates

    def clone_with(
        self,
        *,
        policy_id: str | None = None,
        name: str | None = None,
        version: str | None = None,
        rules: list[DecisionRuleDefinition] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyDefinition:
        return PolicyDefinition(
            policy_id=policy_id or self.policy_id,
            name=name or self.name,
            version=version or self.version,
            decision_column=self.decision_column,
            default_decision=self.default_decision,
            rules=rules or self.rules,
            metadata=metadata or dict(self.metadata),
        )


@dataclass(slots=True)
class ScenarioDefinition:
    scenario_id: str
    name: str
    description: str
    policy: PolicyDefinition
    feature_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["policy"] = self.policy.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioDefinition:
        data = dict(payload)
        data["policy"] = PolicyDefinition.from_dict(data["policy"])
        return cls(**data)


@dataclass(slots=True)
class SearchRunDefinition:
    search_run_id: str
    name: str
    strategy: SearchStrategy
    objective: str
    constraints: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["strategy"] = self.strategy.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchRunDefinition:
        data = dict(payload)
        data["strategy"] = SearchStrategy(data["strategy"])
        return cls(**data)


@dataclass(slots=True)
class ScenarioMetrics:
    approval_rate: float
    review_rate: float
    rejection_rate: float
    expected_profit: float | None
    expected_profit_index: float | None
    risk_estimate: float | None
    churn_estimate: float | None
    out_of_support_ratio: float | None
    uncertainty_label: str | None
    complexity_score: float | None
    features_used: list[str]
    rules_count: int
    records_evaluated: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioMetrics:
        return cls(**payload)


@dataclass(slots=True)
class ScenarioResult:
    scenario_id: str
    scenario_name: str
    policy_id: str
    study_id: str
    metrics: ScenarioMetrics
    transitions: list[dict[str, Any]]
    decision_distribution: list[dict[str, Any]]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metrics"] = asdict(self.metrics)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioResult:
        data = dict(payload)
        data["metrics"] = ScenarioMetrics.from_dict(data["metrics"])
        return cls(**data)


@dataclass(slots=True)
class StudyManifest:
    study_id: str
    name: str
    description: str
    workspace: Workspace
    policy_family: PolicyFamily
    baseline_version: str
    snapshot: StudySnapshotDefinition
    baseline_policy: PolicyDefinition
    derived_features: list[DerivedFeatureDefinition] = field(default_factory=list)
    search_defaults: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "name": self.name,
            "description": self.description,
            "workspace": asdict(self.workspace),
            "policy_family": asdict(self.policy_family),
            "baseline_version": self.baseline_version,
            "snapshot": asdict(self.snapshot),
            "baseline_policy": self.baseline_policy.to_dict(),
            "derived_features": [
                feature.to_dict() for feature in self.derived_features
            ],
            "search_defaults": self.search_defaults,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StudyManifest:
        return cls(
            study_id=payload["study_id"],
            name=payload["name"],
            description=payload.get("description", ""),
            workspace=Workspace.from_dict(payload["workspace"]),
            policy_family=PolicyFamily.from_dict(payload["policy_family"]),
            baseline_version=payload["baseline_version"],
            snapshot=StudySnapshotDefinition.from_dict(payload["snapshot"]),
            baseline_policy=PolicyDefinition.from_dict(payload["baseline_policy"]),
            derived_features=[
                DerivedFeatureDefinition.from_dict(feature)
                for feature in payload.get("derived_features", [])
            ],
            search_defaults=payload.get("search_defaults", {}),
        )


@dataclass(slots=True)
class StudyContext:
    manifest: StudyManifest
    study_root: Path

    @property
    def study_id(self) -> str:
        return self.manifest.study_id

    @property
    def snapshot_path(self) -> Path:
        return self.study_root / self.manifest.snapshot.file_name
