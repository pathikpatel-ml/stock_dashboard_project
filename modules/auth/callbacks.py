import dash
import flask_login
from dash import Input, Output, State

from modules.auth import user_store


def register_auth_callbacks(app):
    @app.callback(
        Output("login-error-msg", "children"),
        Output("login-redirect", "href"),
        Input("login-submit-btn", "n_clicks"),
        State("login-email", "value"),
        State("login-password", "value"),
        prevent_initial_call=True,
    )
    def handle_login(n_clicks, email, password):
        if not email or not password:
            return "Please enter your email and password.", dash.no_update

        user = user_store.verify_password(email, password)
        if user is None:
            return "Invalid email or password.", dash.no_update

        flask_login.login_user(user, remember=True)
        return "", "/"

    @app.callback(
        Output("login-submit-btn", "disabled"),
        Input("login-email", "value"),
        Input("login-password", "value"),
    )
    def toggle_submit_btn(email, password):
        return not (email and password)
