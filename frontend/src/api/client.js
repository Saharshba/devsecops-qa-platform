/* API client. Tokens live in sessionStorage; a 401 triggers one refresh. */
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const store = {
  get access() { return sessionStorage.getItem('tracker.access'); },
  get refresh() { return sessionStorage.getItem('tracker.refresh'); },
  get user() {
    const raw = sessionStorage.getItem('tracker.user');
    return raw ? JSON.parse(raw) : null;
  },
  set(tokens) {
    sessionStorage.setItem('tracker.access', tokens.access_token);
    sessionStorage.setItem('tracker.refresh', tokens.refresh_token);
    sessionStorage.setItem('tracker.user', JSON.stringify(tokens.user));
  },
  clear() {
    ['tracker.access', 'tracker.refresh', 'tracker.user'].forEach((k) => sessionStorage.removeItem(k));
  },
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.status = status;
  }
}

async function describe(response) {
  try {
    const body = await response.json();
    if (Array.isArray(body.errors) && body.errors.length) {
      return body.errors.map((e) => `${e.field}: ${e.message}`).join(', ');
    }
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
  } catch {
    return `Request failed (${response.status})`;
  }
}

async function send(path, { method = 'GET', body, auth = true, retry = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth && store.access) headers.Authorization = `Bearer ${store.access}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && auth && retry && store.refresh) {
    const refreshed = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: store.refresh }),
    });
    if (refreshed.ok) {
      store.set(await refreshed.json());
      return send(path, { method, body, auth, retry: false });
    }
    store.clear();
  }

  if (!response.ok) throw new ApiError(response.status, await describe(response));
  return response.status === 204 ? null : response.json();
}

export const api = {
  tokens: store,
  login: async (username, password) => {
    const tokens = await send('/api/auth/login', {
      method: 'POST', body: { username, password }, auth: false,
    });
    store.set(tokens);
    return tokens.user;
  },
  logout: () => store.clear(),
  me: () => send('/api/auth/me'),
  users: () => send('/api/auth/users'),

  dashboard: () => send('/api/dashboard'),
  projects: () => send('/api/projects'),
  project: (key) => send(`/api/projects/${key}`),
  createProject: (payload) => send('/api/projects', { method: 'POST', body: payload }),
  addMember: (key, payload) => send(`/api/projects/${key}/members`, { method: 'POST', body: payload }),

  issues: (key, params = {}) => send(`/api/projects/${key}/issues?${new URLSearchParams(params)}`),
  createIssue: (key, payload) => send(`/api/projects/${key}/issues`, { method: 'POST', body: payload }),
  issue: (issueKey) => send(`/api/issues/${issueKey}`),
  updateIssue: (issueKey, payload) => send(`/api/issues/${issueKey}`, { method: 'PATCH', body: payload }),
  comments: (issueKey) => send(`/api/issues/${issueKey}/comments`),
  addComment: (issueKey, body) => send(`/api/issues/${issueKey}/comments`, {
    method: 'POST', body: { body },
  }),
  issueActivity: (issueKey) => send(`/api/issues/${issueKey}/activity`),
  projectActivity: (key) => send(`/api/projects/${key}/activity`),

  notifications: (params = {}) => send(`/api/notifications?${new URLSearchParams(params)}`),
  markRead: (id) => send(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () => send('/api/notifications/read-all', { method: 'POST' }),
};

export const STATUSES = ['OPEN', 'IN_PROGRESS', 'IN_REVIEW', 'DONE', 'CLOSED'];
export const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
export const ISSUE_TYPES = ['BUG', 'FEATURE', 'TASK', 'SECURITY'];

export const PRIORITY_COLORS = {
  LOW: 'var(--status-good)',
  MEDIUM: 'var(--status-warning)',
  HIGH: 'var(--status-serious)',
  CRITICAL: 'var(--status-critical)',
};

export function formatDateTime(iso) {
  return new Date(iso).toLocaleString();
}

export function formatNumber(value) {
  return new Intl.NumberFormat().format(value ?? 0);
}

export function humanise(value) {
  return String(value).replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
}
