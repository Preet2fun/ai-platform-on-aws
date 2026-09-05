// ApiClient — Axios-based HTTP client with SSE streaming and cookie auth.
import axios, { AxiosInstance } from 'axios';

let _configLoaded = false;
let _apiUrl = '/api/v1';

// In-memory bearer token. Set by AuthProvider after sign-in / session restore.
// Sent as an Authorization header so auth works even when the httpOnly session
// cookie is blocked as a third-party cookie (frontend and API are on different
// domains: CloudFront vs execute-api). The backend checks the Authorization
// header before falling back to the cookie.
let _authToken: string | null = null;
export function setAuthToken(token: string | null) { _authToken = token; }
export function getAuthToken(): string | null { return _authToken; }

async function loadConfig() {
  if (_configLoaded) return;
  try {
    const resp = await fetch('/config.json');
    const cfg = await resp.json();
    (window as any).__CONFIG__ = cfg;
    _apiUrl = cfg.apiUrl || '/api/v1';
    _configLoaded = true;
  } catch { /* use defaults */ }
}

// Load config immediately
loadConfig();

class ApiClient {
  client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: '/api/v1',
      withCredentials: true,
      timeout: 300000,
    });
    this.client.interceptors.request.use(async (config) => {
      // Ensure config is loaded before first request
      if (!_configLoaded) await loadConfig();
      const cfg = (window as any).__CONFIG__;
      if (cfg?.apiUrl) config.baseURL = cfg.apiUrl;
      // Auth: prefer the in-memory bearer token (works cross-domain); the
      // httpOnly session_token cookie (withCredentials) is a fallback that only
      // works when the browser allows the third-party cookie.
      if (_authToken) {
        config.headers = config.headers || {};
        (config.headers as any).Authorization = `Bearer ${_authToken}`;
      }
      return config;
    });
  }

  async sendMessage(message: string, accountName: string, conversationId: string, options?: { workflow_enabled?: boolean }) {
    const maxRetries = 3;
    for (let i = 0; i < maxRetries; i++) {
      try {
        const resp = await this.client.post('/chat', {
          message,
          account_name: accountName,
          conversation_id: conversationId,
          ...options,
        });
        return resp.data;
      } catch (e: any) {
        if (e?.response?.status === 504 || e.code === 'ECONNABORTED') continue;
        throw e;
      }
    }
    throw new Error('Request timed out after 5 minutes');
  }

  async sendMessageStream(params: { message: string; account_name: string; workflow_enabled?: boolean; full_automation?: boolean; conversation_id?: string }, onEvent?: (event: any) => void) {
    const resp = await this.client.post('/chat', params);
    const requestId = resp.data.request_id;
    if (!requestId) return resp.data;

    // Try SSE streaming first (via CloudFront → ALB, no timeout)
    try {
      const streamUrl = `/api/v1/chat/${requestId}/stream`;
      // Auth via httpOnly session_token cookie (sent automatically by browser)
      const eventSource = new EventSource(streamUrl, { withCredentials: true } as any);
      
      return await new Promise((resolve, reject) => {
        let result: any = null;
        const timeout = setTimeout(() => { eventSource.close(); reject(new Error('Stream timeout')); }, 300000);

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (onEvent) onEvent(data);
            if (data.event === 'complete') {
              clearTimeout(timeout);
              eventSource.close();
              resolve(result || data);
            }
            if (data.event === 'content') {
              result = { content: (result?.content || '') + (data.data?.text || data.data?.content || '') };
            }
            if (data.event === 'error') {
              clearTimeout(timeout);
              eventSource.close();
              reject(new Error(data.data?.message || 'Stream error'));
            }
          } catch (e) { /* ignore parse errors */ }
        };

        eventSource.onerror = () => {
          eventSource.close();
          // Fallback to polling
          clearTimeout(timeout);
          this._pollForResult(requestId, onEvent).then(resolve).catch(reject);
        };
      });
    } catch {
      // Fallback to polling if SSE fails
      return this._pollForResult(requestId, onEvent);
    }
  }

  private async _pollForResult(requestId: string, onEvent?: (event: any) => void) {
    const maxAttempts = 60;
    let eventIndex = 0;
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 1500));
      const poll = await this.client.get(`/chat/${requestId}?event_index=${eventIndex}`);
      const data = poll.data;

      if (data.streaming_events && onEvent) {
        for (const evt of data.streaming_events) {
          onEvent(evt);
        }
      }
      if (data.event_count !== undefined) {
        eventIndex = data.event_count;
      }

      if (data.status === 'complete' || data.status === 'failed') {
        if (onEvent && data.result?.content) {
          onEvent({ event: 'content', data: { content: data.result.content } });
          onEvent({ event: 'complete', data: {} });
        }
        return data.result || data;
      }
    }
    throw new Error('Request timed out after 5 minutes');
  }

  async getChatHistory(k = 10, conversationId?: string) {
    let url = `/chat/history?k=${k}`;
    if (conversationId) url += `&conversation_id=${encodeURIComponent(conversationId)}`;
    return (await this.client.get(url)).data.messages || [];
  }

  async getUserInfo() { return (await this.client.get('/me')).data; }
  async getMspPrincipal() { return (await this.client.get('/msp-principal')).data; }
  async getConversations() { const data = (await this.client.get('/conversations')).data; return data.conversations || []; }
  async deleteConversation(id: string) { return (await this.client.delete(`/conversations/${encodeURIComponent(id)}`)).data; }
  async getAccounts() { const data = (await this.client.get('/accounts')).data; return data.accounts || data || []; }
  async switchAccount(name: string) { return (await this.client.post(`/accounts/${encodeURIComponent(name)}/switch`)).data; }
  async createAccount(data: any) { return (await this.client.post('/accounts', data)).data; }
  async deleteAccount(name: string) { return (await this.client.delete(`/accounts/${encodeURIComponent(name)}`)).data; }
  async prepareAccount(name: string) { return (await this.client.post(`/accounts/${encodeURIComponent(name)}/prepare`)).data; }
  async refreshAccount(name: string) { return (await this.client.put(`/accounts/${encodeURIComponent(name)}/refresh`)).data; }
  async refreshAllAccounts() { return (await this.client.post('/accounts/refresh-all')).data; }

  async pollForResult(requestId: string) {
    const resp = await this.client.get(`/chat/${requestId}`);
    return resp.data;
  }

  async healthCheck() { return (await this.client.get('/health')).data; }
  async getHealthOutages() { return (await this.client.get('/health/outages')).data; }
  async getHealthScheduled() { return (await this.client.get('/health/scheduled')).data; }
  async getHealthNotifications() { return (await this.client.get('/health/notifications')).data; }
  async getHealthSummary() { return (await this.client.get('/health/summary')).data; }

  async getWorkflowStatus(id: string) { return (await this.client.get(`/workflows/${id}`)).data; }
  async getPendingWorkflows() { return (await this.client.get('/workflows/pending')).data; }
  async approveWorkflowStep(id: string, step: any, onProgress?: any) { return (await this.client.post(`/workflows/${id}/approve`, { step_index: step })).data; }
  async rejectWorkflowStep(id: string, step: any, reason?: string) { return (await this.client.post(`/workflows/${id}/reject`, { step_index: step, reason })).data; }

  async setRefreshToken(token: string, idToken?: string) { return (await this.client.post('/auth/set-refresh', { refresh_token: token, id_token: idToken })).data; }
  async restoreSession() { return (await this.client.post('/auth/restore')).data; }
  async logout() { return (await this.client.post('/auth/logout')).data; }
}

export const apiClient = new ApiClient();
