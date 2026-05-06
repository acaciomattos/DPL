from __future__ import annotations

from functools import reduce

import polars as pl

from policy_lab.domain import (
    DecisionRuleDefinition,
    LogicalOperator,
    Operator,
    PolicyDefinition,
    PredicateDefinition,
    RuleBlockDefinition,
)


class PolicyExecutor:
    def execute(self, frame: pl.DataFrame, policy: PolicyDefinition) -> pl.DataFrame:
        decision_column = policy.decision_column
        result = frame.with_columns(
            [
                pl.lit(policy.default_decision).alias(decision_column),
                pl.lit("default").alias("_matched_rule"),
                pl.lit(False).alias("_rule_matched"),
            ]
        )

        for rule in policy.rules:
            rule_expr = self._rule_expression(rule)
            active_expr = (~pl.col("_rule_matched")) & rule_expr
            result = result.with_columns(
                [
                    pl.when(active_expr)
                    .then(pl.lit(rule.decision))
                    .otherwise(pl.col(decision_column))
                    .alias(decision_column),
                    pl.when(active_expr)
                    .then(pl.lit(rule.name))
                    .otherwise(pl.col("_matched_rule"))
                    .alias("_matched_rule"),
                    (pl.col("_rule_matched") | active_expr).alias("_rule_matched"),
                ]
            )

        return result.drop("_rule_matched")

    def _rule_expression(self, rule: DecisionRuleDefinition) -> pl.Expr:
        return self._combine(
            [self._block_expression(block) for block in rule.blocks],
            rule.block_combiner,
        )

    def _block_expression(self, block: RuleBlockDefinition) -> pl.Expr:
        return self._combine(
            [self._predicate_expression(predicate) for predicate in block.predicates],
            block.logical_operator,
        )

    def _predicate_expression(self, predicate: PredicateDefinition) -> pl.Expr:
        left = pl.col(predicate.field)
        operator = predicate.operator
        value = predicate.value
        if operator == Operator.GT:
            return left > value
        if operator == Operator.GTE:
            return left >= value
        if operator == Operator.LT:
            return left < value
        if operator == Operator.LTE:
            return left <= value
        if operator == Operator.EQ:
            return left == value
        if operator == Operator.NE:
            return left != value
        if operator == Operator.IN:
            return left.is_in(value)
        if operator == Operator.NOT_IN:
            return ~left.is_in(value)
        raise ValueError(f"Unsupported operator '{operator}'")

    def _combine(
        self,
        expressions: list[pl.Expr],
        logical_operator: LogicalOperator,
    ) -> pl.Expr:
        if not expressions:
            return pl.lit(True)
        if logical_operator == LogicalOperator.ANY:
            return reduce(lambda left, right: left | right, expressions)
        return reduce(lambda left, right: left & right, expressions)

