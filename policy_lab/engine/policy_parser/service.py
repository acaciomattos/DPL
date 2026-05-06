from __future__ import annotations

from typing import Any

from policy_lab.adapters.base import PolicyAdapter
from policy_lab.adapters.python import PythonPolicyAdapter
from policy_lab.domain import (
    DecisionRuleDefinition,
    DerivedFeatureDefinition,
    LogicalOperator,
    Operator,
    PolicyDefinition,
    PredicateDefinition,
    RuleBlockDefinition,
)


class PolicyParser:
    def __init__(self, adapters: dict[str, PolicyAdapter] | None = None) -> None:
        self._adapters = adapters or {"python": PythonPolicyAdapter()}

    def register(self, adapter: PolicyAdapter) -> None:
        self._adapters[adapter.adapter_name] = adapter

    def parse(
        self,
        source: dict[str, Any],
        adapter_name: str = "python",
    ) -> PolicyDefinition:
        if adapter_name not in self._adapters:
            raise KeyError(f"Unsupported adapter '{adapter_name}'")
        return self._adapters[adapter_name].normalize(source)


class PolicyBuilder:
    @staticmethod
    def predicate_handle(
        rule_index: int,
        block_index: int,
        predicate_index: int,
        predicate: PredicateDefinition,
    ) -> str:
        return (
            f"{rule_index}:{block_index}:{predicate_index}:{predicate.field}:"
            f"{predicate.operator.value}"
        )

    @staticmethod
    def clone(policy: PolicyDefinition) -> PolicyDefinition:
        return PolicyDefinition.from_dict(policy.to_dict())

    @staticmethod
    def apply_threshold_overrides(
        policy: PolicyDefinition,
        overrides: dict[str, Any],
    ) -> PolicyDefinition:
        candidate = PolicyBuilder.clone(policy)
        for rule_index, rule in enumerate(candidate.rules):
            for block_index, block in enumerate(rule.blocks):
                for predicate_index, predicate in enumerate(block.predicates):
                    handle = PolicyBuilder.predicate_handle(
                        rule_index,
                        block_index,
                        predicate_index,
                        predicate,
                    )
                    if handle in overrides:
                        predicate.value = overrides[handle]
        return candidate

    @staticmethod
    def add_reject_rule_from_feature(
        policy: PolicyDefinition,
        feature: DerivedFeatureDefinition,
        *,
        description: str = "",
    ) -> PolicyDefinition:
        candidate = PolicyBuilder.clone(policy)
        veto_rule = DecisionRuleDefinition(
            rule_id=f"derived-{feature.feature_id}",
            name=f"Derived veto: {feature.name}",
            decision="reject",
            description=description or feature.description,
            block_combiner=LogicalOperator.ALL,
            blocks=[
                RuleBlockDefinition(
                    block_id=f"derived-block-{feature.feature_id}",
                    name=f"{feature.name} block",
                    logical_operator=LogicalOperator.ALL,
                    predicates=[
                        PredicateDefinition(
                            field=feature.name,
                            operator=Operator.EQ,
                            value=True,
                            description=f"Reject when {feature.name} is triggered.",
                        )
                    ],
                )
            ],
        )
        candidate.rules = [veto_rule, *candidate.rules]
        return candidate

    @staticmethod
    def add_rule(
        policy: PolicyDefinition,
        rule: DecisionRuleDefinition,
        *,
        position: str = "append",
    ) -> PolicyDefinition:
        candidate = PolicyBuilder.clone(policy)
        next_rule = DecisionRuleDefinition.from_dict(rule.to_dict())
        if position == "prepend":
            candidate.rules = [next_rule, *candidate.rules]
        else:
            candidate.rules = [*candidate.rules, next_rule]
        return candidate
