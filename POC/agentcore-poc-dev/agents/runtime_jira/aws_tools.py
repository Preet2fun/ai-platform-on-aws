"""Jira agent tools — ticket management + shared AWS API caller."""
from langchain_core.tools import tool

@tool
def manage_jira_ticket(action: str = "list") -> str:
    """Manage Jira tickets. Jira is not configured for this environment."""
    return "Jira integration is not configured. Set JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN."

def get_tools():
    return [manage_jira_ticket]
