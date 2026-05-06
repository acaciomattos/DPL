from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import polars as pl

from policy_lab.domain import (
    DecisionRuleDefinition,
    LogicalOperator,
    Operator,
    PolicyDefinition,
    PredicateDefinition,
    RuleBlockDefinition,
    StudyContext,
)
from policy_lab.engine.policy_parser import PolicyBuilder

from .runtime import feature_repository, policy_executor, policy_optimizer


def iter_baseline_predicates(study: StudyContext):
    for rule_index, rule in enumerate(study.manifest.baseline_policy.rules):
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                yield rule_index, rule, block_index, block, predicate_index, predicate


def baseline_asset_id(rule_id: str) -> str:
    return f"baseline:{rule_id}"


def custom_asset_id(rule_id: str) -> str:
    return f"custom:{rule_id}"


def feature_asset_id(feature_id: str) -> str:
    return f"feature:{feature_id}"


def parse_asset_id(asset_id: str) -> tuple[str, str]:
    if ":" not in asset_id:
        return "baseline", asset_id
    kind, raw_id = asset_id.split(":", maxsplit=1)
    return kind, raw_id


def default_rule_state(
    study: StudyContext,
    custom_rules: list[DecisionRuleDefinition] | None = None,
    custom_rule_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return enrich_rule_state(
        study,
        {
            "study_id": study.study_id,
            "used_asset_ids": [
                baseline_asset_id(rule.rule_id)
                for rule in study.manifest.baseline_policy.rules
            ],
            "used_rule_ids": [
                rule.rule_id for rule in study.manifest.baseline_policy.rules
            ],
            "used_custom_rule_ids": [],
            "selected_feature_ids": [],
        },
        custom_rules=custom_rules,
        custom_rule_entries=custom_rule_entries,
    )


def enrich_rule_state(
    study: StudyContext,
    state: dict[str, Any],
    *,
    custom_rules: list[DecisionRuleDefinition] | None = None,
    custom_rule_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    known_rule_ids = [rule.rule_id for rule in study.manifest.baseline_policy.rules]
    if custom_rule_entries is not None:
        known_custom_rule_ids = [
            str(entry.get("rule_id"))
            for entry in custom_rule_entries
            if entry.get("rule_id")
        ]
    else:
        known_custom_rule_ids = [rule.rule_id for rule in custom_rules or []]
    known_feature_ids = [feature.feature_id for feature in feature_repository.load(study)]
    raw_used_asset_ids = state.get("used_asset_ids")
    if isinstance(raw_used_asset_ids, list):
        used_asset_ids: list[str] = []
        for asset_id in raw_used_asset_ids:
            if not isinstance(asset_id, str):
                continue
            kind, raw_id = parse_asset_id(asset_id)
            if kind == "baseline" and raw_id in known_rule_ids:
                used_asset_ids.append(baseline_asset_id(raw_id))
            elif kind == "custom" and raw_id in known_custom_rule_ids:
                used_asset_ids.append(custom_asset_id(raw_id))
            elif kind == "feature" and raw_id in known_feature_ids:
                used_asset_ids.append(feature_asset_id(raw_id))
    else:
        used_rule_ids_seed = [
            rule_id for rule_id in state.get("used_rule_ids", []) if rule_id in known_rule_ids
        ]
        used_custom_rule_ids_seed = [
            rule_id
            for rule_id in state.get("used_custom_rule_ids", [])
            if rule_id in known_custom_rule_ids
        ]
        used_asset_ids = [
            *[baseline_asset_id(rule_id) for rule_id in used_rule_ids_seed],
            *[custom_asset_id(rule_id) for rule_id in used_custom_rule_ids_seed],
            *[
                feature_asset_id(feature_id)
                for feature_id in state.get("selected_feature_ids", [])
                if feature_id in known_feature_ids
            ],
        ]
    used_rule_ids = [
        raw_id
        for asset_id in used_asset_ids
        for kind, raw_id in [parse_asset_id(asset_id)]
        if kind == "baseline"
    ]
    used_custom_rule_ids = [
        raw_id
        for asset_id in used_asset_ids
        for kind, raw_id in [parse_asset_id(asset_id)]
        if kind == "custom"
    ]
    selected_feature_ids = [
        raw_id
        for asset_id in used_asset_ids
        for kind, raw_id in [parse_asset_id(asset_id)]
        if kind == "feature"
    ]
    available_rule_ids = [rule_id for rule_id in known_rule_ids if rule_id not in used_rule_ids]
    available_custom_rule_ids = [
        rule_id for rule_id in known_custom_rule_ids if rule_id not in used_custom_rule_ids
    ]
    available_feature_ids = [
        feature_id
        for feature_id in known_feature_ids
        if feature_id not in selected_feature_ids
    ]
    return {
        "study_id": study.study_id,
        "used_asset_ids": used_asset_ids,
        "used_rule_ids": used_rule_ids,
        "available_rule_ids": available_rule_ids,
        "used_custom_rule_ids": used_custom_rule_ids,
        "available_custom_rule_ids": available_custom_rule_ids,
        "selected_feature_ids": selected_feature_ids,
        "available_feature_ids": available_feature_ids,
    }


def normalize_rule_state(
    study: StudyContext,
    state: dict[str, Any] | None,
    *,
    custom_rules: list[DecisionRuleDefinition] | None = None,
    custom_rule_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    default_state = default_rule_state(
        study,
        custom_rules,
        custom_rule_entries=custom_rule_entries,
    )
    if not state or state.get("study_id") != study.study_id:
        return default_state

    return enrich_rule_state(
        study,
        state,
        custom_rules=custom_rules,
        custom_rule_entries=custom_rule_entries,
    )


def default_predicate_editor_state(study: StudyContext) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for (
        _rule_index,
        rule,
        block_index,
        _block,
        predicate_index,
        predicate,
    ) in iter_baseline_predicates(study):
        handle = ui_predicate_handle(
            rule.rule_id,
            block_index,
            predicate_index,
            predicate.field,
            predicate.operator.value,
        )
        values[handle] = predicate.value
    return {
        "study_id": study.study_id,
        "values": values,
    }


def normalize_predicate_editor_state(
    study: StudyContext,
    state: dict[str, Any] | None,
) -> dict[str, Any]:
    default_state = default_predicate_editor_state(study)
    if not state or state.get("study_id") != study.study_id:
        return default_state

    values = dict(default_state["values"])
    for handle, value in (state.get("values") or {}).items():
        if handle in values:
            values[handle] = value
    return {
        "study_id": study.study_id,
        "values": values,
    }


def predicate_value_from_editor_state(
    study: StudyContext,
    state: dict[str, Any] | None,
    handle: str,
) -> Any:
    normalized = normalize_predicate_editor_state(study, state)
    return normalized.get("values", {}).get(handle, value_from_handle(study, handle))


def custom_rule_member_payloads(entry: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(entry.get("rules"), list):
        return [
            dict(payload)
            for payload in entry.get("rules", [])
            if isinstance(payload, dict)
        ]
    payload = entry.get("rule")
    if isinstance(payload, dict):
        return [dict(payload)]
    return []


def custom_rules_from_store(
    study: StudyContext,
    custom_rule_state: dict[str, Any] | None,
) -> list[DecisionRuleDefinition]:
    if not custom_rule_state or custom_rule_state.get("study_id") != study.study_id:
        return []
    rules: list[DecisionRuleDefinition] = []
    entries = custom_rule_state.get("entries")
    payloads = (
        [
            payload
            for entry in entries
            if isinstance(entry, dict)
            for payload in custom_rule_member_payloads(entry)
        ]
        if isinstance(entries, list)
        else custom_rule_state.get("rules", [])
    )
    for payload in payloads:
        try:
            rules.append(DecisionRuleDefinition.from_dict(payload))
        except (KeyError, TypeError, ValueError):
            continue
    return rules


def custom_rule_entries_from_store(
    study: StudyContext,
    custom_rule_state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not custom_rule_state or custom_rule_state.get("study_id") != study.study_id:
        return []
    entries = custom_rule_state.get("entries")
    if isinstance(entries, list):
        return [dict(entry) for entry in entries if isinstance(entry, dict)]
    rules = custom_rule_state.get("rules", [])
    return [
        {"rule": dict(rule), "rule_id": rule.get("rule_id")}
        for rule in rules
        if isinstance(rule, dict)
    ]


def custom_rule_store_payload(
    study: StudyContext,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    rules = [
        payload
        for entry in entries
        if isinstance(entry, dict)
        for payload in custom_rule_member_payloads(entry)
    ]
    return {
        "study_id": study.study_id,
        "entries": entries,
        "rules": rules,
    }


def feature_ids_used_by_rules(
    study: StudyContext,
    rules: list[DecisionRuleDefinition],
) -> list[str]:
    feature_by_name = {
        feature.name: feature.feature_id for feature in feature_repository.load(study)
    }
    used_feature_ids: list[str] = []
    for rule in rules:
        for block in rule.blocks:
            for predicate in block.predicates:
                feature_id = feature_by_name.get(predicate.field)
                if feature_id and feature_id not in used_feature_ids:
                    used_feature_ids.append(feature_id)
    return used_feature_ids


def available_segment_columns(frame: pl.DataFrame, study: StudyContext) -> list[str]:
    columns: list[str] = []
    date_column = study.manifest.snapshot.date_column
    for column in study.manifest.snapshot.metadata_columns:
        if column == date_column or column not in frame.columns:
            continue
        if not _is_numeric_dtype(frame.schema.get(column)) or frame[column].n_unique() <= 30:
            columns.append(column)
    return columns


def available_matrix_columns(frame: pl.DataFrame, study: StudyContext | None = None) -> list[str]:
    if study is not None and study.manifest.snapshot.analysis_feature_columns:
        derived_feature_names = [feature.name for feature in feature_repository.load(study)]
        allowed_columns = [
            *study.manifest.snapshot.analysis_feature_columns,
            *derived_feature_names,
        ]
        return [
            column
            for column in allowed_columns
            if column in frame.columns and _is_supported_matrix_dtype(frame.schema.get(column))
        ]

    excluded_columns: set[str] = set()
    if study is not None:
        excluded_columns.update(study.manifest.snapshot.outcome_columns)
        excluded_columns.update(study.manifest.snapshot.metadata_columns)
        excluded_columns.update(study.manifest.snapshot.performance_columns.values())
        excluded_columns.add(study.manifest.snapshot.entity_id_column)
        excluded_columns.add(study.manifest.snapshot.historical_decision_column)
        excluded_columns.add(study.manifest.baseline_policy.decision_column)
        if study.manifest.snapshot.date_column:
            excluded_columns.add(study.manifest.snapshot.date_column)

    options: list[str] = []
    for column in frame.columns:
        if column in excluded_columns:
            continue
        dtype = frame.schema.get(column)
        if not _is_supported_matrix_dtype(dtype):
            continue
        options.append(column)
    return options


def policy_variable_columns(study: StudyContext) -> set[str]:
    columns: set[str] = set()
    for rule in study.manifest.baseline_policy.rules:
        for block in rule.blocks:
            for predicate in block.predicates:
                columns.add(predicate.field)
    for feature in feature_repository.load(study):
        columns.update(feature.dependencies)
    return columns


def filter_snapshot(
    frame: pl.DataFrame,
    months: list[str] | None,
    segment_field: str | None,
    segment_values: list[str] | None,
    date_column: str | None = None,
) -> pl.DataFrame:
    filtered = frame
    if months and date_column and date_column in filtered.columns:
        filtered = filtered.filter(
            pl.col(date_column).cast(pl.String).str.slice(0, 6).is_in(months)
        )
    if segment_field and segment_values and segment_field in filtered.columns:
        filtered = filtered.filter(
            pl.col(segment_field).cast(pl.String).is_in([str(value) for value in segment_values])
        )
    return filtered


def apply_optional_matrix_filter(
    frame: pl.DataFrame,
    column_name: str | None,
    operator: str | None,
    value: float | None,
) -> pl.DataFrame:
    if (
        frame.is_empty()
        or not column_name
        or operator is None
        or value is None
        or column_name not in frame.columns
    ):
        return frame
    expression = pl.col(column_name)
    if operator == "<":
        return frame.filter(expression < value)
    if operator == "<=":
        return frame.filter(expression <= value)
    if operator == ">":
        return frame.filter(expression > value)
    if operator == ">=":
        return frame.filter(expression >= value)
    return frame


def build_candidate_policy(
    study: StudyContext,
    *,
    rule_state: dict[str, Any],
    predicate_ids: list[dict[str, str]] | None = None,
    predicate_values: list[Any] | None = None,
    predicate_editor_state: dict[str, Any] | None = None,
    custom_rules: list[DecisionRuleDefinition] | None = None,
    custom_rule_entries: list[dict[str, Any]] | None = None,
    cutoff_override: dict[str, Any] | None = None,
) -> PolicyDefinition:
    baseline_policy = PolicyBuilder.clone(study.manifest.baseline_policy)
    overrides: dict[str, Any] = {}
    modified_rule_ids: set[str] = set()

    if predicate_editor_state is not None:
        editor_state = normalize_predicate_editor_state(study, predicate_editor_state)
        for handle, value in editor_state.get("values", {}).items():
            rule_id = rule_id_from_handle(study, handle)
            if rule_id is None:
                continue
            baseline_value = value_from_handle(study, handle)
            engine_handle = engine_handle_from_ui_handle(study, handle)
            override_value = coerce_override_value(baseline_value, value)
            overrides[engine_handle] = override_value
            if override_value != baseline_value:
                modified_rule_ids.add(rule_id)
    elif predicate_ids is not None and predicate_values is not None:
        for descriptor, value in zip(predicate_ids, predicate_values, strict=False):
            handle = descriptor["handle"]
            rule_id = descriptor["rule_id"]
            baseline_value = value_from_handle(study, handle)
            engine_handle = engine_handle_from_ui_handle(study, handle)
            if value is None:
                override_value = baseline_value
            elif isinstance(baseline_value, int) and not isinstance(baseline_value, bool):
                override_value = int(value)
            elif isinstance(baseline_value, float):
                override_value = float(value)
            else:
                override_value = value
            overrides[engine_handle] = override_value
            if override_value != baseline_value:
                modified_rule_ids.add(rule_id)

    if cutoff_override and cutoff_override.get("study_id") == study.study_id:
        handle = cutoff_override.get("handle")
        if handle:
            baseline_value = value_from_handle(study, handle)
            engine_handle = engine_handle_from_ui_handle(study, handle)
            override_value = coerce_override_value(baseline_value, cutoff_override.get("value"))
            overrides[engine_handle] = override_value
            rule_id = rule_id_from_handle(study, handle)
            if override_value != baseline_value and rule_id is not None:
                modified_rule_ids.add(rule_id)

    candidate_policy = PolicyBuilder.apply_threshold_overrides(baseline_policy, overrides)
    rule_map = {rule.rule_id: rule for rule in candidate_policy.rules}
    baseline_rules_in_use = {
        rule_id
        for rule_id in rule_state.get("used_rule_ids", [])
        if rule_id in rule_map
    }
    for rule_id in baseline_rules_in_use:
        rule = rule_map[rule_id]
        if rule.rule_id in modified_rule_ids and "(ajustada)" not in rule.name:
            rule.name = f"{rule.name} (ajustada)"
    if custom_rule_entries is not None:
        custom_rule_map = {
            str(entry.get("rule_id")): [
                DecisionRuleDefinition.from_dict(payload)
                for payload in custom_rule_member_payloads(entry)
            ]
            for entry in custom_rule_entries
            if entry.get("rule_id")
        }
    else:
        custom_rule_map = {rule.rule_id: rule for rule in custom_rules or []}
    ordered_rules: list[DecisionRuleDefinition] = []
    used_asset_ids = rule_state.get("used_asset_ids") or [
        *[baseline_asset_id(rule_id) for rule_id in rule_state.get("used_rule_ids", [])],
        *[custom_asset_id(rule_id) for rule_id in rule_state.get("used_custom_rule_ids", [])],
        *[
            feature_asset_id(feature_id)
            for feature_id in rule_state.get("selected_feature_ids", [])
        ],
    ]
    feature_map = {feature.feature_id: feature for feature in feature_repository.load(study)}
    for asset_id in used_asset_ids:
        kind, raw_id = parse_asset_id(str(asset_id))
        if kind == "baseline" and raw_id in rule_map:
            ordered_rules.append(rule_map[raw_id])
        elif kind == "custom":
            for rule in custom_rule_map.get(raw_id, []):
                ordered_rules.append(DecisionRuleDefinition.from_dict(rule.to_dict()))
        elif kind == "feature":
            feature = feature_map.get(raw_id)
            if feature is not None:
                ordered_rules.append(
                    DecisionRuleDefinition(
                        rule_id=f"derived-{feature.feature_id}",
                        name=f"Derived veto: {feature.name}",
                        decision="reject",
                        description=feature.description,
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
                                        description=(
                                            f"Reject when {feature.name} is triggered."
                                        ),
                                    )
                                ],
                            )
                        ],
                    )
                )
    candidate_policy.rules = ordered_rules

    for feature_id in rule_state["selected_feature_ids"]:
        if feature_asset_id(feature_id) in used_asset_ids:
            continue
        feature = feature_map.get(feature_id)
        if feature is not None:
            candidate_policy = PolicyBuilder.add_reject_rule_from_feature(
                candidate_policy,
                feature,
                description=feature.description,
            )
    return candidate_policy


def append_rule_to_policy(
    policy: PolicyDefinition,
    rule: DecisionRuleDefinition,
) -> PolicyDefinition:
    candidate = PolicyBuilder.clone(policy)
    candidate.rules = [
        *candidate.rules,
        DecisionRuleDefinition.from_dict(rule.to_dict()),
    ]
    return candidate


def build_matrix_rule(
    *,
    snapshot: pl.DataFrame,
    row_variable: str,
    column_variable: str,
    selected_cells: list[dict[str, str]],
    decision: str,
    name: str,
    existing_rule_ids: set[str],
) -> DecisionRuleDefinition:
    if not selected_cells:
        raise ValueError("Selecione ao menos uma celula da matriz.")
    row_dtype = snapshot.schema.get(row_variable)
    column_dtype = snapshot.schema.get(column_variable)
    blocks: list[RuleBlockDefinition] = []
    for index, cell in enumerate(selected_cells, start=1):
        row_label = str(cell["row"])
        column_label = str(cell["column"])
        predicates = [
            *predicates_from_matrix_label(row_variable, row_label, row_dtype),
            *predicates_from_matrix_label(column_variable, column_label, column_dtype),
        ]
        blocks.append(
            RuleBlockDefinition(
                block_id=f"matrix-cell-{index}",
                name=f"Celula {row_label} x {column_label}",
                predicates=predicates,
                logical_operator=LogicalOperator.ALL,
            )
        )

    return DecisionRuleDefinition(
        rule_id=unique_rule_id(slugify(name) or "regra-matriz", existing_rule_ids),
        name=name.strip() or "Regra criada pela matriz",
        decision=decision,
        blocks=blocks,
        block_combiner=LogicalOperator.ANY,
        description=(
            "Regra criada na matriz de combinacao. "
            f"Variaveis: {row_variable} x {column_variable}. "
            f"Celulas selecionadas: {len(selected_cells)}."
        ),
    )


def build_matrix_rule_set(
    *,
    snapshot: pl.DataFrame,
    row_variable: str,
    column_variable: str,
    cell_decisions: list[dict[str, str]],
    name: str,
    existing_rule_ids: set[str],
    decision_order: list[str] | None = None,
) -> list[DecisionRuleDefinition]:
    decisions_to_cells: dict[str, list[dict[str, str]]] = {}
    for assignment in cell_decisions:
        decision = str(assignment.get("decision") or "").strip()
        row = assignment.get("row")
        column = assignment.get("column")
        if not decision or row is None or column is None:
            continue
        decisions_to_cells.setdefault(decision, []).append(
            {"row": str(row), "column": str(column)}
        )

    if not decisions_to_cells:
        raise ValueError("Atribua ao menos uma decisao a uma celula da matriz.")

    ordered_decisions = decision_order or list(decisions_to_cells)
    rules: list[DecisionRuleDefinition] = []
    used_ids = set(existing_rule_ids)
    multiple_decisions = len(decisions_to_cells) > 1
    for decision in ordered_decisions:
        selected_cells = decisions_to_cells.get(decision, [])
        if not selected_cells:
            continue
        rule_name = (
            f"{name.strip() or 'Regra criada pela matriz'} :: {decision}"
            if multiple_decisions
            else (name.strip() or "Regra criada pela matriz")
        )
        rule = build_matrix_rule(
            snapshot=snapshot,
            row_variable=row_variable,
            column_variable=column_variable,
            selected_cells=selected_cells,
            decision=decision,
            name=rule_name,
            existing_rule_ids=used_ids,
        )
        used_ids.add(rule.rule_id)
        rules.append(rule)
    return rules


def matrix_axis_spec(snapshot: pl.DataFrame, column_name: str) -> dict[str, Any]:
    dtype = snapshot.schema.get(column_name)
    if not _is_numeric_dtype(dtype):
        labels = sorted(
            snapshot.get_column(column_name).drop_nulls().cast(pl.String).unique().to_list()
        )
        return {"type": "discrete", "labels": labels}

    values = snapshot.get_column(column_name).drop_nulls()
    if values.len() == 0:
        return {"type": "discrete", "labels": ["sem dados"]}
    unique_values = values.unique().sort()
    if unique_values.len() <= 10:
        labels = [format_matrix_axis_value(value) for value in unique_values.to_list()]
        return {"type": "discrete", "labels": labels}

    boundaries: list[float] = []
    for index in range(11):
        quantile = index / 10
        raw_value = values.quantile(quantile)
        if raw_value is None:
            continue
        value = float(raw_value)
        if not boundaries or value > boundaries[-1]:
            boundaries.append(value)

    if len(boundaries) < 2:
        labels = [format_matrix_axis_value(value) for value in unique_values.to_list()]
        return {"type": "discrete", "labels": labels}

    labels: list[str] = []
    for index, (lower, upper) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        is_last = index == len(boundaries) - 2
        lower_label = format_matrix_axis_value(lower)
        upper_label = format_matrix_axis_value(upper)
        labels.append(
            f"[{lower_label}, {upper_label}]"
            if is_last
            else f"[{lower_label}, {upper_label})"
        )
    return {"type": "binned", "boundaries": boundaries, "labels": labels}


def matrix_axis_labels(axis_spec: dict[str, Any] | None) -> list[str]:
    if not axis_spec:
        return []
    labels = axis_spec.get("labels", [])
    return [str(label) for label in labels if label is not None]


def predicates_from_matrix_label(
    column_name: str,
    label: str,
    dtype: pl.DataType | None,
) -> list[PredicateDefinition]:
    if label in {"sem dados", "fora da faixa"}:
        raise ValueError(f"A faixa '{label}' nao pode ser salva como regra no MVP.")
    if label.startswith("[") and "," in label and label.endswith((")", "]")):
        lower_raw, upper_raw = label[1:-1].split(",", maxsplit=1)
        upper_operator = Operator.LTE if label.endswith("]") else Operator.LT
        return [
            PredicateDefinition(
                field=column_name,
                operator=Operator.GTE,
                value=parse_numeric_label(lower_raw.strip(), dtype),
            ),
            PredicateDefinition(
                field=column_name,
                operator=upper_operator,
                value=parse_numeric_label(upper_raw.strip(), dtype),
            ),
        ]
    return [
        PredicateDefinition(
            field=column_name,
            operator=Operator.EQ,
            value=parse_scalar_label(label, dtype),
        )
    ]


def parse_scalar_label(label: str, dtype: pl.DataType | None) -> Any:
    if dtype == pl.Boolean:
        return label.lower() in {"true", "1", "sim"}
    if _is_numeric_dtype(dtype):
        return parse_numeric_label(label, dtype)
    return label


def parse_numeric_label(label: str, dtype: pl.DataType | None) -> int | float:
    value = float(label)
    if bool(dtype is not None and getattr(dtype, "is_integer", lambda: False)()):
        return int(value)
    return value


def slugify(value: str) -> str:
    chars: list[str] = []
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    return "".join(chars).strip("-")


def unique_asset_id(base_slug: str, existing_ids: set[str], *, prefix: str) -> str:
    candidate = f"{prefix}-{base_slug}"
    index = 2
    while candidate in existing_ids:
        candidate = f"{prefix}-{base_slug}-{index}"
        index += 1
    return candidate


def unique_rule_id(base_slug: str, existing_rule_ids: set[str]) -> str:
    base = f"matrix-{base_slug}"
    candidate = base
    index = 2
    while candidate in existing_rule_ids:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def next_variant_name(base_name: str, existing_names: set[str]) -> str:
    if base_name not in existing_names:
        return base_name
    index = 2
    while f"{base_name} ({index})" in existing_names:
        index += 1
    return f"{base_name} ({index})"


def custom_entry_predicate_handle(
    asset_id: str,
    rule_index: int,
    block_index: int,
    predicate_index: int,
) -> str:
    return f"{asset_id}:{rule_index}:{block_index}:{predicate_index}"


def coerce_override_value(baseline_value: Any, raw_value: Any) -> Any:
    if raw_value is None:
        return baseline_value
    if isinstance(baseline_value, int) and not isinstance(baseline_value, bool):
        return int(raw_value)
    if isinstance(baseline_value, float):
        return float(raw_value)
    return raw_value


def variant_entry_from_editor_state(
    study: StudyContext,
    origin_rule_id: str,
    predicate_editor_state: dict[str, Any] | None,
    existing_entries: list[dict[str, Any]],
    *,
    variant_name: str | None,
    author: str = "local_user",
) -> dict[str, Any]:
    origin_rule = next(
        (rule for rule in study.manifest.baseline_policy.rules if rule.rule_id == origin_rule_id),
        None,
    )
    if origin_rule is None:
        raise KeyError(f"Unknown baseline rule '{origin_rule_id}'")

    normalized_state = normalize_predicate_editor_state(study, predicate_editor_state)
    variant_rule = DecisionRuleDefinition.from_dict(origin_rule.to_dict())
    changed = False
    for block_index, block in enumerate(variant_rule.blocks):
        for predicate_index, predicate in enumerate(block.predicates):
            handle = ui_predicate_handle(
                variant_rule.rule_id,
                block_index,
                predicate_index,
                predicate.field,
                predicate.operator.value,
            )
            new_value = normalized_state.get("values", {}).get(handle, predicate.value)
            coerced_value = coerce_override_value(predicate.value, new_value)
            if coerced_value != predicate.value:
                changed = True
            predicate.value = coerced_value
    if not changed:
        raise ValueError("Nenhuma alteracao real foi detectada na regra baseline.")

    existing_entry_ids = {
        str(entry.get("rule_id"))
        for entry in existing_entries
        if entry.get("rule_id")
    }
    existing_rule_ids = {
        rule.rule_id for rule in study.manifest.baseline_policy.rules
    } | {
        str(payload.get("rule_id"))
        for entry in existing_entries
        for payload in custom_rule_member_payloads(entry)
        if payload.get("rule_id")
    }
    existing_names = {
        str(entry.get("rule_name"))
        for entry in existing_entries
        if entry.get("rule_name")
    }
    base_name = variant_name.strip() if variant_name and variant_name.strip() else origin_rule.name
    resolved_name = next_variant_name(base_name, existing_names)
    now = datetime.now(timezone.utc).isoformat()
    origin_versions = [
        int(entry.get("version") or 1)
        for entry in existing_entries
        if entry.get("source_type") == "baseline_rule_variant"
        and entry.get("origin_rule_id") == origin_rule.rule_id
    ]
    version = max(origin_versions, default=0) + 1
    asset_id = unique_asset_id(
        slugify(resolved_name) or slugify(origin_rule.name) or "variante-regra",
        existing_entry_ids,
        prefix="variant",
    )
    variant_rule.rule_id = unique_asset_id(
        slugify(resolved_name) or slugify(origin_rule.name) or "regra-variante",
        existing_rule_ids,
        prefix="rule",
    )
    variant_rule.name = resolved_name
    variant_rule.description = (
        f"Variante governada da regra baseline '{origin_rule.name}'. "
        f"Origem: {origin_rule.rule_id}. Versao: {version}."
    )
    return {
        "rule_id": asset_id,
        "rule_name": resolved_name,
        "rule": variant_rule.to_dict(),
        "source_type": "baseline_rule_variant",
        "origin_rule_id": origin_rule.rule_id,
        "origin_rule_name": origin_rule.name,
        "origin_policy_name": study.manifest.baseline_policy.name,
        "version": version,
        "author": author,
        "created_at": now,
        "updated_at": now,
    }


def reset_editor_state_for_rule(
    study: StudyContext,
    predicate_editor_state: dict[str, Any] | None,
    rule_id: str,
) -> dict[str, Any]:
    normalized_state = normalize_predicate_editor_state(study, predicate_editor_state)
    values = dict(normalized_state.get("values", {}))
    for (
        _rule_index,
        rule,
        block_index,
        _block,
        predicate_index,
        predicate,
    ) in iter_baseline_predicates(study):
        if rule.rule_id != rule_id:
            continue
        handle = ui_predicate_handle(
            rule.rule_id,
            block_index,
            predicate_index,
            predicate.field,
            predicate.operator.value,
        )
        values[handle] = predicate.value
    return {
        "study_id": study.study_id,
        "values": values,
    }


def apply_variant_to_rule_state(
    study: StudyContext,
    rule_state: dict[str, Any] | None,
    *,
    variant_asset_id: str,
    origin_rule_id: str,
    replace_current: bool,
    custom_rule_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    state = normalize_rule_state(
        study,
        rule_state,
        custom_rule_entries=custom_rule_entries,
    )
    if not replace_current:
        return enrich_rule_state(
            study,
            {
                "study_id": study.study_id,
                "used_asset_ids": list(state.get("used_asset_ids", [])),
                "selected_feature_ids": state.get("selected_feature_ids", []),
            },
            custom_rule_entries=custom_rule_entries,
        )
    asset_ids = list(state.get("used_asset_ids", []))
    variant_token = custom_asset_id(variant_asset_id)
    origin_token = baseline_asset_id(origin_rule_id)
    asset_ids = [asset_id for asset_id in asset_ids if asset_id != variant_token]
    if replace_current and origin_token in asset_ids:
        origin_index = asset_ids.index(origin_token)
        asset_ids[origin_index] = variant_token
    elif replace_current:
        asset_ids.append(variant_token)
    else:
        asset_ids.append(variant_token)
    return enrich_rule_state(
        study,
        {
            "study_id": study.study_id,
            "used_asset_ids": asset_ids,
            "selected_feature_ids": state.get("selected_feature_ids", []),
        },
        custom_rule_entries=custom_rule_entries,
    )


def rule_id_from_handle(study: StudyContext, handle: str) -> str | None:
    for rule in study.manifest.baseline_policy.rules:
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                if (
                    ui_predicate_handle(
                        rule.rule_id,
                        block_index,
                        predicate_index,
                        predicate.field,
                        predicate.operator.value,
                    )
                    == handle
                ):
                    return rule.rule_id
    return None


def predicate_handle_for_rule(
    study: StudyContext,
    rule_id: str,
    block_index: int,
    predicate_index: int,
) -> str:
    for rule in study.manifest.baseline_policy.rules:
        if rule.rule_id != rule_id:
            continue
        predicate = rule.blocks[block_index].predicates[predicate_index]
        return ui_predicate_handle(
            rule.rule_id,
            block_index,
            predicate_index,
            predicate.field,
            predicate.operator.value,
        )
    raise KeyError(f"Unknown rule_id '{rule_id}'")


def extract_eligible_population(
    snapshot: pl.DataFrame,
    policy: PolicyDefinition,
) -> pl.DataFrame:
    remaining = snapshot
    for rule in policy.rules:
        expression = policy_executor._rule_expression(rule)
        remaining = remaining.filter(~expression)
    return remaining


def extract_anchor_population_for_predicate(
    snapshot: pl.DataFrame,
    policy: PolicyDefinition,
    predicate_handle: str,
) -> pl.DataFrame:
    target_rule_id = rule_id_from_ui_handle(predicate_handle)
    if not target_rule_id:
        return snapshot

    remaining = snapshot
    for rule in policy.rules:
        if rule.rule_id == target_rule_id:
            break
        expression = policy_executor._rule_expression(rule)
        remaining = remaining.filter(~expression)
    return remaining


def prepare_matrix_dimension(
    snapshot: pl.DataFrame,
    column_name: str,
    axis_spec: dict[str, Any] | None = None,
) -> pl.Expr:
    dtype = snapshot.schema.get(column_name)
    spec = axis_spec or matrix_axis_spec(snapshot, column_name)
    if not _is_numeric_dtype(dtype) or spec.get("type") == "discrete":
        return pl.col(column_name).cast(pl.String)

    boundaries = [float(value) for value in spec.get("boundaries", [])]
    labels = [str(label) for label in spec.get("labels", [])]
    if len(boundaries) < 2:
        return pl.col(column_name).map_elements(
            format_matrix_axis_value,
            return_dtype=pl.String,
        )

    expression = None
    for index, (lower, upper) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        is_first = index == 0
        is_last = index == len(boundaries) - 2
        label = (
            labels[index]
            if index < len(labels)
            else (
                f"[{format_matrix_axis_value(lower)}, {format_matrix_axis_value(upper)}]"
                if is_last
                else f"[{format_matrix_axis_value(lower)}, {format_matrix_axis_value(upper)})"
            )
        )
        if is_first and is_last:
            condition = pl.col(column_name).is_not_null()
        elif is_first:
            condition = pl.col(column_name) < upper
        elif is_last:
            condition = pl.col(column_name) >= lower
        else:
            condition = (pl.col(column_name) >= lower) & (pl.col(column_name) < upper)
        expression = (
            pl.when(condition).then(pl.lit(label))
            if expression is None
            else expression.when(condition).then(pl.lit(label))
        )
    return expression.otherwise(pl.lit("fora da faixa"))


def format_matrix_axis_value(value: Any) -> str:
    if value is None:
        return "sem dados"
    numeric_value = float(value)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return f"{numeric_value:.2f}".rstrip("0").rstrip(".")


def find_cutoff_suggestion(
    policy: PolicyDefinition,
    snapshot: pl.DataFrame,
    predicate_handle: str,
    target_metric: str,
    target_value: float,
    performance_columns: dict[str, str] | None = None,
    candidate_source_snapshot: pl.DataFrame | None = None,
) -> dict[str, Any]:
    search_snapshot = (
        candidate_source_snapshot if candidate_source_snapshot is not None else snapshot
    )
    for rule_index, rule in enumerate(policy.rules):
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                handle = ui_predicate_handle(
                    rule.rule_id,
                    block_index,
                    predicate_index,
                    predicate.field,
                    predicate.operator.value,
                )
                if handle != predicate_handle or predicate.field not in snapshot.columns:
                    continue
                engine_handle = PolicyBuilder.predicate_handle(
                    rule_index,
                    block_index,
                    predicate_index,
                    predicate,
                )
                candidates = policy_optimizer._candidate_thresholds(
                    field_name=predicate.field,
                    column=search_snapshot[predicate.field],
                    baseline_value=predicate.value,
                    search_defaults={},
                )
                best_value = predicate.value
                best_gap = float("inf")
                best_metric_value = 0.0
                for candidate_value in candidates:
                    candidate_policy = PolicyBuilder.apply_threshold_overrides(
                        policy,
                        {engine_handle: candidate_value},
                    )
                    executed = policy_executor.execute(snapshot, candidate_policy)
                    metric_value = evaluate_cutoff_metric(
                        executed,
                        decision_column=candidate_policy.decision_column,
                        metric=target_metric,
                        performance_columns=performance_columns,
                    )
                    if metric_value is None:
                        continue
                    gap = abs(metric_value - target_value)
                    if gap < best_gap:
                        best_gap = gap
                        best_value = candidate_value
                        best_metric_value = metric_value
                if best_gap == float("inf"):
                    return {
                        "message": "Nao foi possivel calcular a metrica alvo para esta sugestao.",
                        "override": None,
                    }

                metric_label = "aprovacao" if target_metric == "approval" else "risco"
                metric_grammar = "estimada" if target_metric == "approval" else "estimado"
                return {
                    "message": (
                        f"Sugestao: ajustar {predicate.field} para {best_value}. "
                        f"{metric_label.capitalize()} {metric_grammar} no publico filtrado: "
                        f"{best_metric_value * 100:.2f}%."
                    ),
                    "override": {
                        "handle": predicate_handle,
                        "value": best_value,
                        "metric": target_metric,
                        "metric_value": best_metric_value,
                        "source": "cutoff_suggestion",
                    },
                }
    return {
        "message": "Nenhuma sugestao disponivel para a variavel selecionada.",
        "override": None,
    }


def evaluate_cutoff_metric(
    frame: pl.DataFrame,
    *,
    decision_column: str,
    metric: str,
    performance_columns: dict[str, str] | None = None,
) -> float | None:
    approved = pl.col(decision_column) == "approve"
    if metric == "approval":
        return float(frame.select(approved.mean()).item() or 0.0)
    risk_column = (performance_columns or {}).get("risk_event")
    if metric == "risk" and risk_column and risk_column in frame.columns:
        approved_frame = frame.filter(approved)
        if approved_frame.is_empty():
            return None
        return float(approved_frame.select(pl.col(risk_column).mean()).item() or 0.0)
    return None


def value_from_handle(study: StudyContext, handle: str) -> Any:
    for rule in study.manifest.baseline_policy.rules:
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                if (
                    ui_predicate_handle(
                        rule.rule_id,
                        block_index,
                        predicate_index,
                        predicate.field,
                        predicate.operator.value,
                    )
                    == handle
                ):
                    return predicate.value
    raise KeyError(f"Unknown predicate handle '{handle}'")


def rule_id_from_ui_handle(handle: str) -> str | None:
    parts = str(handle).split(":", maxsplit=1)
    if not parts or not parts[0]:
        return None
    return parts[0]


def engine_handle_from_ui_handle(study: StudyContext, handle: str) -> str:
    for rule_index, rule in enumerate(study.manifest.baseline_policy.rules):
        for block_index, block in enumerate(rule.blocks):
            for predicate_index, predicate in enumerate(block.predicates):
                if (
                    ui_predicate_handle(
                        rule.rule_id,
                        block_index,
                        predicate_index,
                        predicate.field,
                        predicate.operator.value,
                    )
                    == handle
                ):
                    return PolicyBuilder.predicate_handle(
                        rule_index,
                        block_index,
                        predicate_index,
                        predicate,
                    )
    raise KeyError(f"Unknown predicate handle '{handle}'")


def ui_predicate_handle(
    rule_id: str,
    block_index: int,
    predicate_index: int,
    field: str,
    operator: str,
) -> str:
    return f"{rule_id}:{block_index}:{predicate_index}:{field}:{operator}"


def _is_numeric_dtype(dtype: pl.DataType | None) -> bool:
    return bool(dtype is not None and getattr(dtype, "is_numeric", lambda: False)())


def _is_supported_matrix_dtype(dtype: pl.DataType | None) -> bool:
    return bool(_is_numeric_dtype(dtype) or dtype == pl.String or dtype == pl.Boolean)
