import logging

import dash
import dash_bootstrap_components as dbc
import flask_login
from dash import ALL, Input, Output, State, html

from modules.auth import user_store
from modules.auth.session_store import get_all_active_sessions, revoke_session

logger = logging.getLogger(__name__)

ADMIN_EMAIL_KEY = "ADMIN_EMAIL"


def _time_ago(ts_str: str) -> str:
    if not ts_str:
        return "never"
    try:
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            from datetime import timezone
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return ts_str[:10] if ts_str else "unknown"


def register_admin_callbacks(app):

    @app.callback(
        Output("admin-pending-table", "children"),
        Output("admin-active-table", "children"),
        Output("admin-sessions-table", "children"),
        Input("admin-refresh-btn", "n_clicks"),
        Input("admin-action-result", "children"),
        Input("strategy-tabs", "value"),
    )
    def load_admin_tables(n_clicks, action_result, active_tab):
        if active_tab != "tab-admin":
            raise dash.exceptions.PreventUpdate

        # ── Pending users table ─────────────────────────────────────────
        pending = user_store.get_pending_users()
        if not pending:
            pending_table = html.P(
                "No pending requests.", className="text-muted small"
            )
        else:
            rows = []
            for u in pending:
                rows.append(html.Tr([
                    html.Td(u.get("name") or "—"),
                    html.Td(u.get("email", "")),
                    html.Td(_time_ago(u.get("created_at", ""))),
                    html.Td([
                        dbc.Button(
                            [html.I(className="fas fa-check me-1"), "Approve"],
                            id={"type": "admin-approve", "user_id": u["id"]},
                            color="success",
                            size="sm",
                            className="me-2",
                            n_clicks=0,
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-times me-1"), "Reject"],
                            id={"type": "admin-reject", "user_id": u["id"]},
                            color="danger",
                            size="sm",
                            outline=True,
                            n_clicks=0,
                        ),
                    ]),
                ]))
            pending_table = dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("Name"), html.Th("Email"),
                        html.Th("Requested"), html.Th("Actions"),
                    ])),
                    html.Tbody(rows),
                ],
                bordered=True, hover=True, size="sm", responsive=True,
            )

        # ── Active / all users table ────────────────────────────────────
        all_users = user_store.get_all_active_users()
        if not all_users:
            active_table = html.P("No active users.", className="text-muted small")
        else:
            rows = []
            for u in all_users:
                status = u.get("status", "active")
                is_admin = u.get("email") == app.server.config.get(
                    "ADMIN_EMAIL", "pathikc129@gmail.com"
                )
                badge_color = {"active": "success", "deactivated": "secondary",
                               "rejected": "danger"}.get(status, "secondary")
                toggle_btn = html.Span("Admin", className="text-muted small") if is_admin else (
                    dbc.Button(
                        "Deactivate" if u.get("is_active") else "Activate",
                        id={"type": "admin-toggle", "user_id": u["id"]},
                        color="warning" if u.get("is_active") else "success",
                        size="sm", outline=True, n_clicks=0,
                    )
                )
                rows.append(html.Tr([
                    html.Td(u.get("name") or "—"),
                    html.Td(u.get("email", "")),
                    html.Td(_time_ago(u.get("last_login_at", ""))),
                    html.Td(dbc.Badge(status, color=badge_color)),
                    html.Td(toggle_btn),
                ]))
            active_table = dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("Name"), html.Th("Email"),
                        html.Th("Last Login"), html.Th("Status"), html.Th(""),
                    ])),
                    html.Tbody(rows),
                ],
                bordered=True, hover=True, size="sm", responsive=True,
            )

        # ── Active sessions table ─────────────────────────────────────────
        sessions = get_all_active_sessions()
        if not sessions:
            sessions_table = html.P("No active sessions.", className="text-muted small")
        else:
            rows = []
            for s in sessions:
                rows.append(html.Tr([
                    html.Td(s.get("name") or "—"),
                    html.Td(s.get("email", "—")),
                    html.Td(s.get("ip_address") or "—"),
                    html.Td(_time_ago(s.get("last_active", ""))),
                    html.Td(_time_ago(s.get("expires_at", ""))),
                    html.Td(dbc.Badge("Remember Me", color="info") if s.get("remember_me")
                            else dbc.Badge("Normal", color="secondary")),
                    html.Td(dbc.Button(
                        [html.I(className="fas fa-times me-1"), "Revoke"],
                        id={"type": "admin-revoke-session", "sid": s["id"]},
                        color="danger", size="sm", outline=True, n_clicks=0,
                    )),
                ]))
            sessions_table = dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("Name"), html.Th("Email"), html.Th("IP"),
                        html.Th("Last Active"), html.Th("Expires"), html.Th("Type"), html.Th(""),
                    ])),
                    html.Tbody(rows),
                ],
                bordered=True, hover=True, size="sm", responsive=True,
            )

        return pending_table, active_table, sessions_table

    @app.callback(
        Output("admin-action-result", "children", allow_duplicate=True),
        Input({"type": "admin-revoke-session", "sid": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def revoke_session_cb(n_clicks_list):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            raise dash.exceptions.PreventUpdate
        triggered_id = ctx.triggered[0]["prop_id"]
        import json
        id_dict = json.loads(triggered_id.split(".")[0])
        sid = id_dict["sid"]
        try:
            revoke_session(sid)
            return dbc.Alert("Session revoked.", color="warning",
                             duration=3000, dismissable=True)
        except Exception:
            logger.exception("Failed to revoke session %s", sid)
            return dbc.Alert("Failed to revoke session.", color="danger", dismissable=True)

    # ── Approve ──────────────────────────────────────────────────────────
    @app.callback(
        Output("admin-action-result", "children"),
        Input({"type": "admin-approve", "user_id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def approve_user(n_clicks_list):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            raise dash.exceptions.PreventUpdate
        triggered_id = ctx.triggered[0]["prop_id"]
        import json
        id_dict = json.loads(triggered_id.split(".")[0])
        user_id = id_dict["user_id"]
        try:
            user_store.approve_user(user_id)
            logger.info("Admin approved user_id=%s", user_id)
            return dbc.Alert(f"User {user_id} approved.", color="success",
                             duration=3000, dismissable=True)
        except Exception:
            logger.exception("Failed to approve user_id=%s", user_id)
            return dbc.Alert("Failed to approve user.", color="danger", dismissable=True)

    # ── Reject ───────────────────────────────────────────────────────────
    @app.callback(
        Output("admin-action-result", "children", allow_duplicate=True),
        Input({"type": "admin-reject", "user_id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def reject_user(n_clicks_list):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            raise dash.exceptions.PreventUpdate
        triggered_id = ctx.triggered[0]["prop_id"]
        import json
        id_dict = json.loads(triggered_id.split(".")[0])
        user_id = id_dict["user_id"]
        try:
            user_store.reject_user(user_id)
            logger.info("Admin rejected user_id=%s", user_id)
            return dbc.Alert(f"User {user_id} rejected.", color="warning",
                             duration=3000, dismissable=True)
        except Exception:
            logger.exception("Failed to reject user_id=%s", user_id)
            return dbc.Alert("Failed to reject user.", color="danger", dismissable=True)

    # ── Toggle activate/deactivate ────────────────────────────────────────
    @app.callback(
        Output("admin-action-result", "children", allow_duplicate=True),
        Input({"type": "admin-toggle", "user_id": ALL}, "n_clicks"),
        State({"type": "admin-toggle", "user_id": ALL}, "children"),
        prevent_initial_call=True,
    )
    def toggle_user(n_clicks_list, labels):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            raise dash.exceptions.PreventUpdate
        triggered_id = ctx.triggered[0]["prop_id"]
        import json
        id_dict = json.loads(triggered_id.split(".")[0])
        user_id = id_dict["user_id"]
        idx = next(i for i, t in enumerate(ctx.triggered_id if hasattr(ctx, "triggered_id") else [])
                   if True) if False else 0
        # Find which button was clicked by matching user_id
        for i, n in enumerate(n_clicks_list):
            if n:
                label = labels[i] if i < len(labels) else "Deactivate"
                break
        else:
            raise dash.exceptions.PreventUpdate
        try:
            if label == "Deactivate":
                user_store.deactivate_user(user_id)
                return dbc.Alert(f"User {user_id} deactivated.", color="warning",
                                 duration=3000, dismissable=True)
            else:
                user_store.reactivate_user(user_id)
                return dbc.Alert(f"User {user_id} reactivated.", color="success",
                                 duration=3000, dismissable=True)
        except Exception:
            logger.exception("Failed to toggle user_id=%s", user_id)
            return dbc.Alert("Action failed.", color="danger", dismissable=True)
