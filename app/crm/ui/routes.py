from __future__ import annotations

from flask import Blueprint, render_template


crm_ui = Blueprint(
    "crm_ui",
    __name__,
    template_folder="templates",
)


@crm_ui.route("/crm/login", methods=["GET"])
def crm_login_page():
    return render_template("crm/login.html")


@crm_ui.route("/crm", methods=["GET"])
@crm_ui.route("/crm/dashboard", methods=["GET"])
def crm_dashboard_page():
    return render_template("crm/page.html", page="dashboard", page_title="Dashboard")


@crm_ui.route("/crm/contacts", methods=["GET"])
def crm_contacts_page():
    return render_template("crm/page.html", page="contacts", page_title="Contacts")


@crm_ui.route("/crm/contacts/<contact_id>", methods=["GET"])
def crm_contact_detail_page(contact_id: str):
    return render_template("crm/contact_detail.html", contact_id=contact_id, page_title="Contact Detail")


@crm_ui.route("/crm/deals", methods=["GET"])
def crm_deals_page():
    return render_template("crm/page.html", page="deals", page_title="Deals")


@crm_ui.route("/crm/tasks", methods=["GET"])
def crm_tasks_page():
    return render_template("crm/page.html", page="tasks", page_title="Tasks")


@crm_ui.route("/crm/conversations", methods=["GET"])
def crm_conversations_page():
    return render_template("crm/page.html", page="conversations", page_title="Conversations")


@crm_ui.route("/crm/automations", methods=["GET"])
def crm_automations_page():
    return render_template("crm/page.html", page="automations", page_title="Automations")


@crm_ui.route("/crm/reports", methods=["GET"])
def crm_reports_page():
    return render_template("crm/page.html", page="reports", page_title="Reports")


@crm_ui.route("/crm/settings", methods=["GET"])
def crm_settings_page():
    return render_template("crm/page.html", page="settings", page_title="Settings")
