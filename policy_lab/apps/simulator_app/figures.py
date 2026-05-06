from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
import polars as pl

from policy_lab.domain import PolicyDefinition, ScenarioResult

from .runtime import policy_executor
from .services import matrix_axis_labels, prepare_matrix_dimension


def build_comparison_figure(
    baseline_result: ScenarioResult,
    scenario_result: ScenarioResult,
) -> go.Figure:
    figure = go.Figure()
    categories = ["Aprovacao", "Indice de lucro", "Risco", "Churn", "Complexidade"]
    figure.add_bar(
        name="Baseline",
        x=categories,
        y=[
            baseline_result.metrics.approval_rate * 100,
            baseline_result.metrics.expected_profit_index or 0.0,
            (baseline_result.metrics.risk_estimate or 0.0) * 100,
            (baseline_result.metrics.churn_estimate or 0.0) * 100,
            baseline_result.metrics.complexity_score or 0.0,
        ],
    )
    figure.add_bar(
        name="Candidata",
        x=categories,
        y=[
            scenario_result.metrics.approval_rate * 100,
            scenario_result.metrics.expected_profit_index or 0.0,
            (scenario_result.metrics.risk_estimate or 0.0) * 100,
            (scenario_result.metrics.churn_estimate or 0.0) * 100,
            scenario_result.metrics.complexity_score or 0.0,
        ],
    )
    return themed_figure(
        figure,
        title="Perfil comparativo de metricas",
        layout_updates={"barmode": "group"},
    )


def build_transition_figure(transitions: list[dict[str, Any]], title: str) -> go.Figure:
    if not transitions:
        return empty_figure(title)
    from_values = sorted({row["from_decision"] for row in transitions})
    to_values = sorted({row["to_decision"] for row in transitions})
    matrix = []
    for from_value in from_values:
        row = []
        for to_value in to_values:
            count = next(
                (
                    item["count"]
                    for item in transitions
                    if item["from_decision"] == from_value
                    and item["to_decision"] == to_value
                ),
                0,
            )
            row.append(count)
        matrix.append(row)
    figure = go.Figure(
        data=go.Heatmap(z=matrix, x=to_values, y=from_values, colorscale="Viridis")
    )
    return themed_figure(figure, title=title)


def build_rule_flow_figure(snapshot: pl.DataFrame, policy: PolicyDefinition) -> go.Figure:
    remaining = snapshot
    total = max(snapshot.height, 1)
    stages: list[str] = ["Pool inicial"]
    decision_counts: dict[str, list[int]] = {policy.default_decision: [snapshot.height]}
    cumulative_counts: dict[str, int] = {}
    for rule in policy.rules:
        expression = policy_executor._rule_expression(rule)
        matched = remaining.filter(expression)
        remaining = remaining.filter(~expression)
        stages.append(rule.name)
        cumulative_counts[rule.decision] = cumulative_counts.get(rule.decision, 0) + matched.height
        decisions = {policy.default_decision, *cumulative_counts.keys()}
        for decision in decisions:
            decision_counts.setdefault(decision, [0] * (len(stages) - 1))
        for decision, values in decision_counts.items():
            if decision == policy.default_decision:
                values.append(cumulative_counts.get(decision, 0) + remaining.height)
            else:
                values.append(cumulative_counts.get(decision, 0))

    stages.append("Pool final")
    decisions = {policy.default_decision, *cumulative_counts.keys()}
    for decision in decisions:
        decision_counts.setdefault(decision, [0] * (len(stages) - 1))
    for decision, values in decision_counts.items():
        if decision == policy.default_decision:
            values.append(cumulative_counts.get(decision, 0) + remaining.height)
        else:
            values.append(cumulative_counts.get(decision, 0))

    figure = go.Figure()
    ordered_decisions = sorted(decision_counts, key=lambda item: decision_sort_key(item))
    for decision in ordered_decisions:
        values = decision_counts[decision]
        customdata = [[value, value / total] for value in values]
        figure.add_bar(
            name=decision_label(decision),
            orientation="h",
            y=stages,
            x=values,
            customdata=customdata,
            text=[_format_count(value) if value else "" for value in values],
            textposition="inside",
            insidetextanchor="middle",
            marker={"color": decision_color(decision)},
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"Decisao: {decision_label(decision)}<br>"
                "Registros: %{customdata[0]:,}<br>"
                "% do pool: %{customdata[1]:.1%}<extra></extra>"
            ),
        )
    return themed_figure(
        figure,
        title=(
            "Fluxo por decisao acumulada"
            "<br><sup>Barras somam o publico filtrado; remanescentes assumem "
            f"default: {decision_label(policy.default_decision)}.</sup>"
        ),
        layout_updates={
            "barmode": "stack",
            "xaxis_title": "Registros",
            "yaxis": {"autorange": "reversed"},
            "legend": {
                "orientation": "h",
                "y": -0.24,
                "x": 0,
                "yanchor": "top",
                "bgcolor": "rgba(16, 22, 29, 0.72)",
            },
            "margin": dict(l=180, r=40, t=104, b=96),
            "uniformtext": {"mode": "hide", "minsize": 10},
        },
    )


def _format_count(value: int | float) -> str:
    return f"{int(value):,}".replace(",", ".")


def _repelled_label_offsets(points: list[tuple[float, float, str]]) -> list[tuple[int, int]]:
    if not points:
        return []

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    x_span = max(max_x - min_x, 1.0)
    y_span = max(max_y - min_y, 1.0)
    candidate_offsets = [
        (36, -24),
        (-36, -24),
        (36, 24),
        (-36, 24),
        (52, 0),
        (-52, 0),
        (0, 42),
        (0, -42),
        (62, 32),
        (-62, 32),
        (62, -32),
        (-62, -32),
        (76, 0),
        (-76, 0),
        (0, 62),
        (0, -62),
    ]
    placed_boxes: list[tuple[float, float, float, float]] = []
    offsets_by_point: dict[tuple[int, int], set[tuple[int, int]]] = {}
    offsets: list[tuple[int, int]] = []
    point_boxes = [
        (
            ((point[0] - min_x) / x_span) - 0.018,
            ((point[0] - min_x) / x_span) + 0.018,
            ((point[1] - min_y) / y_span) - 0.026,
            ((point[1] - min_y) / y_span) + 0.026,
        )
        for point in points
    ]
    for x_value, y_value, text in points:
        x_norm = (x_value - min_x) / x_span
        y_norm = (y_value - min_y) / y_span
        point_key = (round(x_norm * 1000), round(y_norm * 1000))
        used_offsets = offsets_by_point.setdefault(point_key, set())
        width = min(0.26, 0.046 + len(text) * 0.0066)
        height = 0.064
        best_offset = candidate_offsets[0]
        best_score = float("inf")
        best_box = (0.0, 0.0, 0.0, 0.0)
        for x_shift, y_shift in candidate_offsets:
            shifted_x = x_norm + (x_shift / 760)
            shifted_y = y_norm + (y_shift / 460)
            box = (
                shifted_x - width / 2,
                shifted_x + width / 2,
                shifted_y - height / 2,
                shifted_y + height / 2,
            )
            overlap_penalty = sum(_box_overlap_area(box, placed) for placed in placed_boxes)
            point_overlap_penalty = sum(
                _box_overlap_area(box, point_box) for point_box in point_boxes
            )
            distance_penalty = (abs(x_shift) + abs(y_shift)) * 0.0005
            out_of_bounds_penalty = (
                max(-box[0], 0)
                + max(box[1] - 1, 0)
                + max(-box[2], 0)
                + max(box[3] - 1, 0)
            )
            reused_offset_penalty = 1.0 if (x_shift, y_shift) in used_offsets else 0.0
            score = (
                overlap_penalty * 1000
                + point_overlap_penalty * 1600
                + out_of_bounds_penalty * 5
                + reused_offset_penalty * 10
                + distance_penalty
            )
            if score < best_score:
                best_score = score
                best_offset = (x_shift, y_shift)
                best_box = box
        offsets.append(best_offset)
        placed_boxes.append(best_box)
        used_offsets.add(best_offset)
    return offsets


def _box_overlap_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x_overlap = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    y_overlap = max(0.0, min(first[3], second[3]) - max(first[2], second[2]))
    return x_overlap * y_overlap


def decision_label(decision: str) -> str:
    labels = {
        "approve": "Aprovados",
        "reject": "Rejeitados",
        "review": "Enviados para analise",
    }
    return labels.get(decision, decision)


def decision_color(decision: str) -> str:
    colors = {
        "approve": "#5bb98d",
        "reject": "#ea7b66",
        "review": "#64a9c7",
    }
    return colors.get(decision, "#b6a6e8")


def decision_sort_key(decision: str) -> tuple[int, str]:
    order = {"approve": 0, "review": 1, "reject": 2}
    return order.get(decision, 10), decision


def _add_point_label(
    figure: go.Figure,
    *,
    x: float,
    y: float,
    text: str,
    offset: tuple[int, int],
) -> None:
    x_shift, y_shift = offset
    figure.add_annotation(
        x=x,
        y=y,
        text=text,
        showarrow=False,
        xshift=x_shift,
        yshift=y_shift,
        font={"size": 10, "color": "#dce6e9"},
        bgcolor="rgba(16, 22, 29, 0.68)",
        bordercolor="rgba(105, 145, 155, 0.22)",
        borderpad=2,
    )


def build_recommendation_figure(
    results: list[ScenarioResult],
    baseline_result: ScenarioResult,
    *,
    reference_label: str = "Baseline",
) -> go.Figure:
    if not results:
        return empty_figure("Nenhuma recomendacao disponivel.")
    figure = go.Figure()
    figure.add_scatter(
        x=[baseline_result.metrics.approval_rate * 100],
        y=[baseline_result.metrics.expected_profit_index or 0.0],
        mode="markers",
        name=reference_label,
        marker=dict(size=12, color="#f4e285"),
        hovertemplate=(
            f"<b>{reference_label}</b><br>"
            "Aprovacao: %{x:.2f}%<br>"
            "Indice de lucro: %{y:.2f}<extra></extra>"
        ),
    )
    candidate_x = [result.metrics.approval_rate * 100 for result in results]
    candidate_y = [result.metrics.expected_profit_index or 0.0 for result in results]
    label_points = [
        (
            baseline_result.metrics.approval_rate * 100,
            baseline_result.metrics.expected_profit_index or 0.0,
            reference_label,
        ),
        *[
            (candidate_x[index], candidate_y[index], result.scenario_name)
            for index, result in enumerate(results)
        ],
    ]
    label_offsets = _repelled_label_offsets(label_points)
    _add_point_label(
        figure,
        x=baseline_result.metrics.approval_rate * 100,
        y=baseline_result.metrics.expected_profit_index or 0.0,
        text=reference_label,
        offset=label_offsets[0],
    )
    figure.add_scatter(
        x=candidate_x,
        y=candidate_y,
        mode="markers",
        name="Candidatas",
        text=[result.scenario_name for result in results],
        marker=dict(
            size=10,
            color=[result.lineage.get("objective_performance", 0.0) for result in results],
            colorscale="Tealgrn",
            showscale=True,
            colorbar={"title": "Desempenho", "x": 1.12},
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Aprovacao: %{x:.2f}%<br>"
            "Indice de lucro: %{y:.2f}<extra></extra>"
        ),
    )
    for index, result in enumerate(results):
        _add_point_label(
            figure,
            x=candidate_x[index],
            y=candidate_y[index],
            text=result.scenario_name,
            offset=label_offsets[index + 1],
        )
    return themed_figure(
        figure,
        title="Fronteira de candidatos: aprovacao x indice de lucro",
        layout_updates={
            "xaxis_title": "Aprovacao (%)",
            "yaxis_title": "Indice de lucro esperado",
            "legend": {"orientation": "h", "y": 1.12, "x": 0},
            "margin": dict(l=64, r=170, t=76, b=64),
        },
    )


def build_matrix_preview(
    snapshot: pl.DataFrame,
    row_variable: str,
    column_variable: str,
    event_column: str | None = None,
    cell_decisions: list[dict[str, str]] | None = None,
    interaction_token: str | None = None,
    axis_specs: dict[str, dict[str, Any]] | None = None,
) -> go.Figure:
    if snapshot.is_empty():
        return empty_figure("Nao ha publico elegivel para montar a matriz.")

    event_expression = (
        pl.col(event_column)
        if event_column and event_column in snapshot.columns
        else pl.lit(None)
    )
    frame = snapshot.select(
        [
            prepare_matrix_dimension(
                snapshot,
                row_variable,
                (axis_specs or {}).get("row"),
            ).alias("_row"),
            prepare_matrix_dimension(
                snapshot,
                column_variable,
                (axis_specs or {}).get("column"),
            ).alias("_column"),
            event_expression.alias("_event"),
        ]
    )
    matrix = (
        frame.group_by(["_row", "_column"])
        .agg(pl.col("_event").mean().alias("event_rate"), pl.len().alias("records"))
        .sort(["_row", "_column"])
    )
    rows = matrix_axis_labels((axis_specs or {}).get("row")) or sorted(
        matrix.get_column("_row").unique().to_list()
    )
    cols = matrix_axis_labels((axis_specs or {}).get("column")) or sorted(
        matrix.get_column("_column").unique().to_list()
    )
    z: list[list[float]] = []
    text: list[list[str]] = []
    hover_text: list[list[str]] = []
    total_records = max(snapshot.height, 1)
    for row_label in rows:
        z_row: list[float] = []
        text_row: list[str] = []
        hover_row: list[str] = []
        for col_label in cols:
            match = matrix.filter(
                (pl.col("_row") == row_label) & (pl.col("_column") == col_label)
            )
            if match.height == 0:
                z_row.append(0.0)
                text_row.append("Vol 0%<br>Tx 0%")
                hover_row.append("Volume=0.0%<br>Taxa=0.0%<br>n=0")
            else:
                event_rate = float(match["event_rate"][0] or 0.0)
                records = int(match["records"][0])
                volume_share = records / total_records
                z_row.append(event_rate)
                text_row.append(f"Vol {volume_share:.1%}<br>Tx {event_rate:.1%}")
                hover_row.append(
                    f"Volume={volume_share:.2%}<br>Taxa={event_rate:.2%}<br>n={records}"
                )
        z.append(z_row)
        text.append(text_row)
        hover_text.append(hover_row)
    overlay_marker_size = max(
        28,
        min(
            74,
            int(min(520 / max(len(cols), 1), 420 / max(len(rows), 1)) * 0.72),
        ),
    )
    figure = go.Figure(
        data=go.Heatmap(
            z=z,
            x=cols,
            y=rows,
            text=text,
            customdata=hover_text,
            texttemplate="%{text}",
            textfont={"size": 9, "color": "#f6fbfc"},
            hovertemplate="%{customdata}<extra></extra>",
            colorscale="Teal",
            xgap=1,
            ygap=1,
        )
    )
    figure.add_scatter(
        x=[col_label for row_label in rows for col_label in cols],
        y=[row_label for row_label in rows for _ in cols],
        customdata=[
            {"row": str(row_label), "column": str(col_label), "token": interaction_token}
            for row_label in rows
            for col_label in cols
        ],
        mode="markers",
        marker={
            "symbol": "square",
            "size": overlay_marker_size,
            "opacity": 0.012,
            "color": "#10161d",
        },
        hoverinfo="skip",
        showlegend=False,
        selected={"marker": {"opacity": 0.012}},
        unselected={"marker": {"opacity": 0.012}},
    )
    cell_decisions = cell_decisions or []
    if cell_decisions:
        decisions = sorted(
            {str(cell.get("decision")) for cell in cell_decisions if cell.get("decision")},
            key=decision_sort_key,
        )
        assignment_map = {
            (str(cell["row"]), str(cell["column"])): str(cell["decision"])
            for cell in cell_decisions
            if cell.get("row") is not None
            and cell.get("column") is not None
            and cell.get("decision")
        }
        for decision in decisions:
            decision_pairs = [
                (row_label, col_label)
                for row_label in rows
                for col_label in cols
                if assignment_map.get((str(row_label), str(col_label))) == decision
            ]
            if not decision_pairs:
                continue
            decision_z = [
                [
                    1 if assignment_map.get((str(row_label), str(col_label))) == decision else None
                    for col_label in cols
                ]
                for row_label in rows
            ]
            base_color = decision_color(decision)
            figure.add_heatmap(
                z=decision_z,
                x=cols,
                y=rows,
                colorscale=[
                    [0.0, "rgba(0, 0, 0, 0.0)"],
                    [1.0, rgba_from_hex(base_color, 0.16)],
                ],
                zmin=0,
                zmax=1,
                showscale=False,
                hoverinfo="skip",
                xgap=1,
                ygap=1,
                showlegend=False,
            )
            figure.add_scatter(
                x=[column for row, column in decision_pairs],
                y=[row for row, column in decision_pairs],
                customdata=[
                    {
                        "row": str(row),
                        "column": str(column),
                        "token": interaction_token,
                        "decision": decision,
                    }
                    for row, column in decision_pairs
                ],
                mode="markers",
                marker={
                    "symbol": "square-open",
                    "size": overlay_marker_size + 10,
                    "color": base_color,
                    "line": {"color": base_color, "width": 2.5},
                },
                hoverinfo="skip",
                showlegend=False,
            )
    return themed_figure(
        figure,
        title=f"Matriz do publico elegivel: {row_variable} x {column_variable}",
        layout_updates={"dragmode": "lasso", "clickmode": "event+select"},
    )


def rgba_from_hex(hex_color: str, alpha: float) -> str:
    normalized = hex_color.lstrip("#")
    if len(normalized) != 6:
        return f"rgba(220, 230, 233, {alpha})"
    red = int(normalized[0:2], 16)
    green = int(normalized[2:4], 16)
    blue = int(normalized[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha})"

def themed_figure(
    figure: go.Figure,
    *,
    title: str,
    layout_updates: dict[str, Any] | None = None,
) -> go.Figure:
    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#10161d",
        plot_bgcolor="#10161d",
        margin=dict(l=40, r=20, t=40, b=40),
        title=title,
    )
    if layout_updates:
        figure.update_layout(**layout_updates)
    return figure


def empty_figure(title: str) -> go.Figure:
    return themed_figure(go.Figure(), title=title)
