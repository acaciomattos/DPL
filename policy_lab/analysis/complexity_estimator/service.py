from __future__ import annotations

from policy_lab.domain import PolicyDefinition


class ComplexityEstimator:
    def estimate(self, policy: PolicyDefinition) -> float:
        rules_count = len(policy.rules)
        predicate_count = len(policy.iter_predicates())
        feature_count = len({predicate.field for predicate in policy.iter_predicates()})
        score = (rules_count * 12.0) + (predicate_count * 4.0) + (feature_count * 9.0)
        return min(round(score, 2), 100.0)
