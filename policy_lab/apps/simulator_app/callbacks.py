from __future__ import annotations

from dash import ALL, Input, Output, State

from . import callback_handlers as handlers


def register_callbacks(app) -> None:
    app.callback(
        Output("manual-lab-container", "style"),
        Output("rule-composition-container", "style"),
        Output("automatic-optimization-container", "style"),
        Input("main-tabs", "value"),
    )(handlers.render_tab)

    app.callback(
        Output("custom-rule-store", "data"),
        Input("study-dropdown", "value"),
    )(handlers.load_custom_rule_store)

    app.callback(
        Output("predicate-editor-store", "data"),
        Input("study-dropdown", "value"),
    )(handlers.load_predicate_editor_state)

    app.callback(
        Output("manual-config-store", "data"),
        Input("study-dropdown", "value"),
    )(handlers.load_manual_config_store)

    app.callback(
        Output("asset-editor-store", "data"),
        Input("study-dropdown", "value"),
        Input({"type": "open-rule-editor", "rule_id": ALL}, "n_clicks"),
        Input({"type": "open-feature-editor", "feature_id": ALL}, "n_clicks"),
        Input({"type": "open-custom-editor", "rule_id": ALL}, "n_clicks"),
        Input("asset-editor-close", "n_clicks"),
        State("asset-editor-store", "data"),
        State("custom-rule-store", "data"),
    )(handlers.update_asset_editor_state)

    app.callback(
        Output("asset-editor-drawer", "className"),
        Output("asset-editor-body", "children"),
        Output("asset-editor-status", "children"),
        Output("asset-editor-save", "disabled"),
        Output("asset-editor-save", "style"),
        Output("asset-editor-toolbar-title", "children"),
        Output("asset-cutoff-panel", "style"),
        Input("study-dropdown", "value"),
        Input("asset-editor-store", "data"),
        Input("predicate-editor-store", "data"),
        Input("custom-rule-store", "data"),
        Input("cutoff-handle", "value"),
    )(handlers.render_asset_editor)

    app.callback(
        Output("predicate-editor-store", "data", allow_duplicate=True),
        Output("custom-rule-store", "data", allow_duplicate=True),
        Output("rule-state-store", "data", allow_duplicate=True),
        Output("asset-editor-store", "data", allow_duplicate=True),
        Output("asset-editor-status", "children", allow_duplicate=True),
        Input("asset-editor-save", "n_clicks"),
        State("study-dropdown", "value"),
        State("asset-editor-store", "data"),
        State({"type": "editor-predicate-input", "handle": ALL}, "id"),
        State({"type": "editor-predicate-input", "handle": ALL}, "value"),
        State("predicate-editor-store", "data"),
        State("custom-rule-store", "data"),
        State("rule-state-store", "data"),
        State("variant-rule-name", "value"),
        State("variant-replace-policy", "value"),
        prevent_initial_call=True,
    )(handlers.save_asset_editor_values)

    app.callback(
        Output("cutoff-handle", "value", allow_duplicate=True),
        Output("asset-editor-status", "children", allow_duplicate=True),
        Input({"type": "select-cutoff-handle", "handle": ALL}, "n_clicks"),
        State("study-dropdown", "value"),
        prevent_initial_call=True,
    )(handlers.select_cutoff_target)

    app.callback(
        Output("rule-state-store", "data"),
        Input("study-dropdown", "value"),
        Input({"type": "add-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "remove-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "move-up-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "move-down-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "add-custom-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "remove-custom-rule", "rule_id": ALL}, "n_clicks"),
        Input({"type": "add-feature", "feature_id": ALL}, "n_clicks"),
        Input({"type": "remove-feature", "feature_id": ALL}, "n_clicks"),
        Input("custom-rule-store", "data"),
        State("rule-state-store", "data"),
    )(handlers.update_rule_state)

    app.callback(
        Output("rule-state-store", "data", allow_duplicate=True),
        Input("rule-library-dnd-payload", "value"),
        State("study-dropdown", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        prevent_initial_call=True,
    )(handlers.apply_rule_library_drag_drop)

    app.callback(
        Output("manual-config-select", "options"),
        Output("manual-config-select", "value"),
        Output("manual-config-name", "value"),
        Input("study-dropdown", "value"),
        Input("manual-config-store", "data"),
        State("manual-config-current-store", "data"),
    )(handlers.load_manual_config_controls)

    app.callback(
        Output("month-filter", "options"),
        Output("month-filter", "value"),
        Output("segment-field", "options"),
        Output("segment-field", "value"),
        Input("study-dropdown", "value"),
        State("manual-ui-state-store", "data"),
    )(handlers.load_filter_controls)

    app.callback(
        Output("study-meta", "children"),
        Output("baseline-metrics", "children"),
        Input("study-dropdown", "value"),
        Input("month-filter", "value"),
        Input("segment-field", "value"),
        Input("segment-values", "value"),
    )(handlers.update_baseline_context)

    app.callback(
        Output("manual-ui-state-store", "data"),
        Input("study-dropdown", "value"),
        Input("month-filter", "value"),
        Input("segment-field", "value"),
        Input("segment-values", "value"),
        Input("cutoff-objective", "value"),
        Input("cutoff-handle", "value"),
        Input("target-approval-rate", "value"),
        State("manual-ui-state-store", "data"),
    )(handlers.persist_manual_ui_state)

    app.callback(
        Output("segment-values", "options"),
        Output("segment-values", "value"),
        Input("study-dropdown", "value"),
        Input("segment-field", "value"),
        Input("month-filter", "value"),
        State("manual-ui-state-store", "data"),
    )(handlers.update_segment_values)

    app.callback(
        Output("cutoff-objective", "value"),
        Output("cutoff-handle", "value"),
        Output("target-approval-rate", "value"),
        Input("study-dropdown", "value"),
        State("manual-ui-state-store", "data"),
    )(handlers.restore_cutoff_controls)

    app.callback(
        Output("manual-config-store", "data", allow_duplicate=True),
        Output("manual-config-current-store", "data"),
        Output("manual-config-status", "children"),
        Input("save-manual-config", "n_clicks"),
        State("study-dropdown", "value"),
        State("manual-config-name", "value"),
        State("manual-config-current-store", "data"),
        State("manual-ui-state-store", "data"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        prevent_initial_call=True,
    )(handlers.save_manual_config)

    app.callback(
        Output("manual-ui-state-store", "data", allow_duplicate=True),
        Output("rule-state-store", "data", allow_duplicate=True),
        Output("cutoff-override-store", "data", allow_duplicate=True),
        Output("manual-config-current-store", "data", allow_duplicate=True),
        Output("month-filter", "value", allow_duplicate=True),
        Output("segment-field", "value", allow_duplicate=True),
        Output("segment-values", "value", allow_duplicate=True),
        Output("cutoff-objective", "value", allow_duplicate=True),
        Output("cutoff-handle", "value", allow_duplicate=True),
        Output("target-approval-rate", "value", allow_duplicate=True),
        Output("scenario-metrics", "children", allow_duplicate=True),
        Output("comparison-table", "data", allow_duplicate=True),
        Output("comparison-table", "columns", allow_duplicate=True),
        Output("comparison-figure", "figure", allow_duplicate=True),
        Output("transition-figure", "figure", allow_duplicate=True),
        Output("rule-flow-figure", "figure", allow_duplicate=True),
        Output("last-simulation-store", "data", allow_duplicate=True),
        Output("manual-config-status", "children", allow_duplicate=True),
        Input("load-manual-config", "n_clicks"),
        State("study-dropdown", "value"),
        State("manual-config-select", "value"),
        State("manual-config-store", "data"),
        State("custom-rule-store", "data"),
        prevent_initial_call=True,
    )(handlers.load_manual_config)

    app.callback(
        Output("rule-library", "children"),
        Output("cutoff-handle", "options"),
        Input("study-dropdown", "value"),
        Input("rule-state-store", "data"),
        Input("custom-rule-store", "data"),
    )(handlers.render_rule_library)

    app.callback(
        Output("matrix-rule-decision", "options"),
        Output("matrix-rule-decision", "value"),
        Input("study-dropdown", "value"),
    )(handlers.load_matrix_rule_decisions)

    app.callback(
        Output("matrix-filter-count-store", "data"),
        Input("study-dropdown", "value"),
        Input("add-matrix-filter", "n_clicks"),
        State("matrix-filter-count-store", "data"),
        State("matrix-config-store", "data"),
    )(handlers.update_matrix_filter_count)

    app.callback(
        Output("matrix-filter-container", "children"),
        Input("study-dropdown", "value"),
        Input("matrix-filter-count-store", "data"),
        State("matrix-config-store", "data"),
    )(handlers.render_matrix_filters)

    app.callback(
        Output("matrix-config-store", "data"),
        Input("study-dropdown", "value"),
        Input("matrix-row-variable", "value"),
        Input("matrix-column-variable", "value"),
        Input("matrix-filter-count-store", "data"),
        Input({"type": "matrix-filter-variable", "index": ALL}, "value"),
        Input({"type": "matrix-filter-operator", "index": ALL}, "value"),
        Input({"type": "matrix-filter-value", "index": ALL}, "value"),
        State("matrix-config-store", "data"),
    )(handlers.persist_matrix_config)

    app.callback(
        Output("matrix-row-variable", "options"),
        Output("matrix-column-variable", "options"),
        Input("study-dropdown", "value"),
        Input("matrix-row-variable", "value"),
        Input("matrix-column-variable", "value"),
    )(handlers.update_matrix_variable_options)

    app.callback(
        Output("matrix-row-variable", "value"),
        Output("matrix-column-variable", "value"),
        Input("study-dropdown", "value"),
        Input("matrix-config-store", "data"),
        State("matrix-config-store", "data"),
    )(handlers.restore_matrix_variables)

    app.callback(
        Output("cutoff-target-label", "children"),
        Input("cutoff-objective", "value"),
    )(handlers.update_cutoff_target_label)

    app.callback(
        Output("cutoff-suggestion", "children"),
        Output("cutoff-override-store", "data"),
        Input("find-cutoff", "n_clicks"),
        State("study-dropdown", "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("predicate-editor-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
    )(handlers.suggest_cutoff)

    app.callback(
        Output("scenario-metrics", "children"),
        Output("comparison-table", "data"),
        Output("comparison-table", "columns"),
        Output("comparison-figure", "figure"),
        Output("transition-figure", "figure"),
        Output("rule-flow-figure", "figure"),
        Output("last-simulation-store", "data"),
        Input("run-scenario", "n_clicks"),
        State("study-dropdown", "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
    )(handlers.run_manual_scenario)

    app.callback(
        Output("policy-download", "data"),
        Input("export-manual-policy", "n_clicks"),
        State("study-dropdown", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
        prevent_initial_call=True,
    )(handlers.export_manual_policy)

    app.callback(
        Output("recommendation-table", "data"),
        Output("recommendation-table", "columns"),
        Output("recommendation-figure", "figure"),
        Output("search-results-store", "data"),
        Input("run-search", "n_clicks"),
        State("study-dropdown", "value"),
        State("search-strategy", "value"),
        State("search-base", "value"),
        State("search-primary-metric", "value"),
        State("search-direction", "value"),
        State("search-preserve-metric", "value"),
        State("search-max-degradation", "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("last-simulation-store", "data"),
    )(handlers.run_search)

    app.callback(
        Output("custom-rule-store", "data", allow_duplicate=True),
        Output("rule-state-store", "data", allow_duplicate=True),
        Output("scenario-metrics", "children", allow_duplicate=True),
        Output("comparison-table", "data", allow_duplicate=True),
        Output("comparison-table", "columns", allow_duplicate=True),
        Output("comparison-figure", "figure", allow_duplicate=True),
        Output("transition-figure", "figure", allow_duplicate=True),
        Output("rule-flow-figure", "figure", allow_duplicate=True),
        Output("last-simulation-store", "data", allow_duplicate=True),
        Output("main-tabs", "value", allow_duplicate=True),
        Output("transfer-search-status", "children"),
        Input("transfer-search-candidate", "n_clicks"),
        State("study-dropdown", "value"),
        State("recommendation-table", "selected_rows"),
        State("search-results-store", "data"),
        State("custom-rule-store", "data"),
        State("rule-state-store", "data"),
        State("last-simulation-store", "data"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("predicate-editor-store", "data"),
        prevent_initial_call=True,
    )(handlers.transfer_search_candidate_to_manual_lab)

    app.callback(
        Output("matrix-config-store", "data", allow_duplicate=True),
        Output("matrix-figure", "figure"),
        Output("matrix-summary", "children"),
        Output("matrix-selection-store", "data"),
        Input("generate-matrix", "n_clicks"),
        State("study-dropdown", "value"),
        State("matrix-row-variable", "value"),
        State("matrix-column-variable", "value"),
        State({"type": "matrix-filter-variable", "index": ALL}, "value"),
        State({"type": "matrix-filter-operator", "index": ALL}, "value"),
        State({"type": "matrix-filter-value", "index": ALL}, "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
        State("matrix-config-store", "data"),
        prevent_initial_call=True,
    )(handlers.render_matrix_preview)

    app.callback(
        Output("matrix-selection-store", "data", allow_duplicate=True),
        Input("matrix-figure", "clickData"),
        Input("matrix-figure", "selectedData"),
        State("study-dropdown", "value"),
        State("matrix-row-variable", "value"),
        State("matrix-column-variable", "value"),
        State("matrix-rule-decision", "value"),
        State("matrix-selection-store", "data"),
        prevent_initial_call=True,
    )(handlers.update_matrix_selection)

    app.callback(
        Output("matrix-figure", "figure", allow_duplicate=True),
        Output("matrix-summary", "children", allow_duplicate=True),
        Output("matrix-selection-summary", "children"),
        Input("matrix-selection-store", "data"),
        Input("matrix-editing-rule-store", "data"),
        State("matrix-config-store", "data"),
        State("study-dropdown", "value"),
        State("matrix-rule-decision", "value"),
        State("matrix-row-variable", "value"),
        State("matrix-column-variable", "value"),
        State({"type": "matrix-filter-variable", "index": ALL}, "value"),
        State({"type": "matrix-filter-operator", "index": ALL}, "value"),
        State({"type": "matrix-filter-value", "index": ALL}, "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
        prevent_initial_call=True,
    )(handlers.render_selected_matrix)

    app.callback(
        Output("matrix-rule-preview", "children"),
        Input("preview-matrix-rule", "n_clicks"),
        State("study-dropdown", "value"),
        State("matrix-row-variable", "value"),
        State("matrix-column-variable", "value"),
        State("matrix-selection-store", "data"),
        State("matrix-rule-decision", "value"),
        State("matrix-rule-name", "value"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
    )(handlers.preview_matrix_rule)

    app.callback(
        Output("custom-rule-store", "data", allow_duplicate=True),
        Output("matrix-save-status", "children"),
        Output("overwrite-rule-confirm", "displayed"),
        Output("pending-matrix-rule-store", "data"),
        Input("save-matrix-rule", "n_clicks"),
        State("study-dropdown", "value"),
        State("matrix-row-variable", "value"),
        State("matrix-column-variable", "value"),
        State("matrix-selection-store", "data"),
        State("matrix-rule-decision", "value"),
        State("matrix-rule-name", "value"),
        State("custom-rule-store", "data"),
        State("month-filter", "value"),
        State("segment-field", "value"),
        State("segment-values", "value"),
        State("rule-state-store", "data"),
        State({"type": "matrix-filter-variable", "index": ALL}, "value"),
        State({"type": "matrix-filter-operator", "index": ALL}, "value"),
        State({"type": "matrix-filter-value", "index": ALL}, "value"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
        State("matrix-editing-rule-store", "data"),
        prevent_initial_call=True,
    )(handlers.save_matrix_rule)

    app.callback(
        Output("custom-rule-store", "data", allow_duplicate=True),
        Output("matrix-save-status", "children", allow_duplicate=True),
        Output("pending-matrix-rule-store", "data", allow_duplicate=True),
        Input("overwrite-rule-confirm", "submit_n_clicks"),
        State("study-dropdown", "value"),
        State("pending-matrix-rule-store", "data"),
        State("custom-rule-store", "data"),
        prevent_initial_call=True,
    )(handlers.confirm_overwrite_matrix_rule)

    app.callback(
        Output("pending-matrix-edit-store", "data"),
        Output("matrix-edit-alert", "message"),
        Output("matrix-edit-alert", "displayed"),
        Input({"type": "edit-custom-rule", "rule_id": ALL}, "n_clicks"),
        State("study-dropdown", "value"),
        State("custom-rule-store", "data"),
        State("manual-ui-state-store", "data"),
        State("rule-state-store", "data"),
        prevent_initial_call=True,
    )(handlers.prepare_custom_rule_matrix_edit)

    app.callback(
        Output("main-tabs", "value"),
        Output("manual-ui-state-store", "data", allow_duplicate=True),
        Output("month-filter", "value", allow_duplicate=True),
        Output("segment-field", "value", allow_duplicate=True),
        Output("segment-values", "value", allow_duplicate=True),
        Output("matrix-row-variable", "value", allow_duplicate=True),
        Output("matrix-column-variable", "value", allow_duplicate=True),
        Output("matrix-config-store", "data", allow_duplicate=True),
        Output("matrix-filter-count-store", "data", allow_duplicate=True),
        Output("matrix-selection-store", "data", allow_duplicate=True),
        Output("matrix-rule-name", "value", allow_duplicate=True),
        Output("matrix-rule-decision", "value", allow_duplicate=True),
        Output("matrix-save-status", "children", allow_duplicate=True),
        Output("matrix-editing-rule-store", "data"),
        Output("pending-matrix-edit-store", "data", allow_duplicate=True),
        Output("matrix-figure", "figure", allow_duplicate=True),
        Output("matrix-summary", "children", allow_duplicate=True),
        Output("matrix-selection-summary", "children", allow_duplicate=True),
        Output("scenario-metrics", "children", allow_duplicate=True),
        Output("comparison-table", "data", allow_duplicate=True),
        Output("comparison-table", "columns", allow_duplicate=True),
        Output("comparison-figure", "figure", allow_duplicate=True),
        Output("transition-figure", "figure", allow_duplicate=True),
        Output("rule-flow-figure", "figure", allow_duplicate=True),
        Output("last-simulation-store", "data", allow_duplicate=True),
        Input("matrix-edit-alert", "submit_n_clicks"),
        Input("matrix-edit-alert", "cancel_n_clicks"),
        State("study-dropdown", "value"),
        State("pending-matrix-edit-store", "data"),
        State("rule-state-store", "data"),
        State("custom-rule-store", "data"),
        State("cutoff-override-store", "data"),
        State("cutoff-handle", "value"),
        State("cutoff-objective", "value"),
        State("target-approval-rate", "value"),
        State("predicate-editor-store", "data"),
        prevent_initial_call=True,
    )(handlers.apply_custom_rule_matrix_edit)
