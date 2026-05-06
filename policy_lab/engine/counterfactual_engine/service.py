from __future__ import annotations

import polars as pl


class CounterfactualEngine:
    def transitions(
        self,
        frame: pl.DataFrame,
        from_column: str,
        to_column: str,
    ) -> list[dict[str, object]]:
        transitions = (
            frame.group_by([from_column, to_column])
            .len()
            .sort([from_column, to_column])
            .rename(
                {
                    from_column: "from_decision",
                    to_column: "to_decision",
                    "len": "count",
                }
            )
        )
        return transitions.to_dicts()

    def distribution(self, frame: pl.DataFrame, decision_column: str) -> list[dict[str, object]]:
        distribution = (
            frame.group_by(decision_column)
            .len()
            .sort(decision_column)
            .rename({decision_column: "decision", "len": "count"})
        )
        return distribution.to_dicts()
