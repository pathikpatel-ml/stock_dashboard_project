import dash_bootstrap_components as dbc
from dash import dcc, html


def create_admin_layout():
    return dbc.Container(
        fluid=True,
        className="p-4",
        children=[
            html.H4([
                html.I(className="fas fa-shield-alt me-2 text-warning"),
                "Admin Panel",
            ], className="mb-4"),

            # ── Pending Signups ─────────────────────────────────────────────
            dbc.Card(className="mb-4 section-container", children=dbc.CardBody([
                html.Div(
                    className="d-flex justify-content-between align-items-center mb-3",
                    children=[
                        html.H6([
                            html.I(className="fas fa-user-clock me-2 text-warning"),
                            "Pending Signup Requests",
                        ], className="mb-0"),
                        dbc.Button(
                            [html.I(className="fas fa-sync me-1"), "Refresh"],
                            id="admin-refresh-btn",
                            size="sm",
                            color="secondary",
                            outline=True,
                            n_clicks=0,
                        ),
                    ],
                ),
                html.Div(id="admin-pending-table"),
            ])),

            # ── Active Users ────────────────────────────────────────────────
            dbc.Card(className="mb-4 section-container", children=dbc.CardBody([
                html.H6([
                    html.I(className="fas fa-users me-2 text-success"),
                    "Active Users",
                ], className="mb-3"),
                html.Div(id="admin-active-table"),
            ])),

            # ── Active Sessions ─────────────────────────────────────────────
            dbc.Card(className="section-container", children=dbc.CardBody([
                html.H6([
                    html.I(className="fas fa-lock me-2 text-info"),
                    "Active Sessions",
                ], className="mb-3"),
                html.P(
                    "All currently valid sessions. Revoking a session logs the user out immediately.",
                    className="text-muted small mb-3",
                ),
                html.Div(id="admin-sessions-table"),
            ])),

            # ── Reject-with-reason modal ─────────────────────────────────────
            dbc.Modal(
                id="reject-reason-modal",
                is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle([
                        html.I(className="fas fa-times-circle me-2 text-danger"),
                        "Reject Access Request",
                    ])),
                    dbc.ModalBody([
                        html.P("Provide a reason — this will be emailed to the user.",
                               className="text-muted small"),
                        dbc.Textarea(
                            id="reject-reason-input",
                            placeholder="e.g. We're not accepting new members at this time.",
                            rows=3,
                            maxLength=500,
                        ),
                    ]),
                    dbc.ModalFooter([
                        dbc.Button("Cancel", id="reject-cancel-btn",
                                   color="secondary", outline=True, n_clicks=0),
                        dbc.Button([html.I(className="fas fa-times me-1"), "Confirm Reject"],
                                   id="reject-confirm-btn", color="danger", n_clicks=0),
                    ]),
                ],
            ),

            # Stores and result
            dcc.Store(id="admin-reject-user-id"),
            html.Div(id="admin-action-result", className="mt-2 small"),
        ],
    )
