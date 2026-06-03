import dash_bootstrap_components as dbc
from dash import dcc, html


def create_login_layout():
    return html.Div(
        className="login-wrapper",
        children=[
            dbc.Card(
                className="login-card shadow-lg",
                children=dbc.CardBody([
                    html.Div(
                        className="login-logo-area",
                        children=[
                            html.I(className="fas fa-chart-line login-logo-icon"),
                            html.H4("Stock Signal Dashboard", className="login-title"),
                            html.P("Sign in to access your signals", className="login-subtitle"),
                        ],
                    ),
                    html.Hr(className="login-divider"),
                    dbc.InputGroup(
                        className="mb-3",
                        children=[
                            dbc.InputGroupText(html.I(className="fas fa-envelope")),
                            dbc.Input(
                                id="login-email",
                                type="email",
                                placeholder="Email address",
                                autocomplete="email",
                                debounce=False,
                            ),
                        ],
                    ),
                    dbc.InputGroup(
                        className="mb-3",
                        children=[
                            dbc.InputGroupText(html.I(className="fas fa-lock")),
                            dbc.Input(
                                id="login-password",
                                type="password",
                                placeholder="Password",
                                autocomplete="current-password",
                                debounce=False,
                            ),
                        ],
                    ),
                    html.Div(id="login-error-msg", className="login-error mb-2"),
                    dbc.Button(
                        [html.I(className="fas fa-sign-in-alt me-2"), "Sign In"],
                        id="login-submit-btn",
                        color="primary",
                        className="w-100 login-btn",
                        n_clicks=0,
                    ),
                    # Hidden location component — triggers redirect after successful login
                    dcc.Location(id="login-redirect", refresh=True),
                    html.Hr(className="login-divider mt-3"),
                    html.Div(
                        html.A(
                            [html.I(className="fas fa-user-plus me-1"), "Request Access"],
                            href="/signup",
                            className="text-center d-block",
                            style={"color": "#64748b", "fontSize": "0.82rem",
                                   "textDecoration": "none"},
                        ),
                        className="text-center",
                    ),
                ]),
            )
        ],
    )
