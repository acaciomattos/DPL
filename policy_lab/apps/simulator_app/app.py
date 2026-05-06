from __future__ import annotations

from dash import Dash, html

from .callbacks import register_callbacks
from .layout import build_app_layout

app = Dash(
    __name__,
    title="Decision Policy Lab",
    update_title="DPL | executando busca...",
    suppress_callback_exceptions=True,
)
app.layout = html.Div()
register_callbacks(app)
app.layout = build_app_layout()


def main() -> None:
    app.run(debug=False)


if __name__ == "__main__":
    main()
