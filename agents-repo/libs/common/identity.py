"""AgentCore Identity helpers: fetch outbound credentials from the token vault.

Agents fetch Jira API keys / OAuth2 tokens at runtime via the AgentCore Identity
APIs rather than embedding secrets. Backed by IAM perms:
bedrock-agentcore:GetResourceApiKey / GetResourceOauth2Token.
"""

from __future__ import annotations

import boto3

from common.config import Settings, get_settings


class IdentityClient:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self._c = boto3.client("bedrock-agentcore", region_name=self.s.region)

    def api_key(self, provider_name: str | None = None) -> str:
        """Return an API key (e.g. Jira) from a credential provider."""
        name = provider_name or self.s.jira_api_key_provider
        resp = self._c.get_resource_api_key(resourceCredentialProviderName=name)
        return resp["apiKey"]

    def oauth2_token(self, provider_name: str | None = None, scopes: list[str] | None = None) -> str:
        """Return an OAuth2 access token (e.g. gateway Cognito) from the vault."""
        name = provider_name or self.s.gateway_oauth2_provider
        resp = self._c.get_resource_oauth2_token(
            resourceCredentialProviderName=name,
            scopes=scopes or [self.s.cognito_scope],
        )
        return resp["accessToken"]
