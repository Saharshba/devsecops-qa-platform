/** Shared helpers: API-level setup, UI-level assertions.
 *
 * Fixtures are created through the API rather than by clicking, so an E2E test
 * fails on the journey it is actually testing, not on unrelated setup.
 */
export const API_URL = process.env.E2E_API_URL || 'http://localhost:8000';

export const ADMIN = {
  username: process.env.E2E_ADMIN_USER || 'admin',
  password: process.env.E2E_ADMIN_PASSWORD || 'ChangeMe!123',
};

export async function apiLogin(request, user = ADMIN) {
  const response = await request.post(`${API_URL}/api/auth/login`, { data: user });
  if (!response.ok()) throw new Error(`login failed: ${response.status()} ${await response.text()}`);
  return (await response.json()).access_token;
}

export function auth(token) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

/** Create a user if it does not already exist, and return its credentials. */
export async function ensureUser(request, token, { username, role }) {
  const password = `${username.replace(/[^A-Za-z]/g, '') || 'user'}Passw0rd!42`;
  const response = await request.post(`${API_URL}/api/auth/users`, {
    headers: auth(token),
    data: { username, email: `${username}@example.com`, password, role },
  });
  if (!response.ok() && response.status() !== 409) {
    throw new Error(`could not create ${username}: ${await response.text()}`);
  }
  return { username, password };
}

export async function uiLogin(page, { username, password }) {
  await page.goto('/login');
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.getByTestId('sign-in').click();
  await page.waitForURL('**/');
}

/** A project key unique to this run, so repeated runs do not collide. */
export function uniqueKey(prefix = 'E2E') {
  const suffix = Date.now().toString(36).slice(-4).toUpperCase();
  return `${prefix}${suffix}`.slice(0, 10);
}
