import { expect, test } from '@playwright/test';
import { API_URL, apiLogin, auth, ensureUser, uiLogin, uniqueKey } from './helpers';

/**
 * Authorisation, checked through the browser and the API together: the UI
 * hides what a role cannot do, and the API refuses it even when the UI is
 * bypassed. The second half is what matters — a hidden button is not a control.
 */
test.describe('access control', () => {
  let projectKey;
  let viewer;
  let outsider;

  test.beforeAll(async ({ request }) => {
    const token = await apiLogin(request);
    projectKey = uniqueKey('ACL');
    viewer = await ensureUser(request, token, { username: 'e2eviewer', role: 'VIEWER' });
    outsider = await ensureUser(request, token, { username: 'e2eoutsider', role: 'DEVELOPER' });

    await request.post(`${API_URL}/api/projects`, {
      headers: auth(token),
      data: { key: projectKey, name: 'Access control project' },
    });
    await request.post(`${API_URL}/api/projects/${projectKey}/members`, {
      headers: auth(token),
      data: { username: viewer.username, role: 'VIEWER' },
    });
    await request.post(`${API_URL}/api/projects/${projectKey}/issues`, {
      headers: auth(token),
      data: { title: 'Visible only to members', priority: 'LOW' },
    });
  });

  test('signed-out visitors are sent to the login page', async ({ page }) => {
    await page.goto('/projects');
    await expect(page).toHaveURL(/\/login/);
  });

  test('a viewer sees the board but no create form', async ({ page }) => {
    await uiLogin(page, viewer);
    await page.goto(`/projects/${projectKey}`);
    await expect(page.getByTestId('column-OPEN')).toContainText('Visible only to members');
    await expect(page.getByTestId('create-issue')).toHaveCount(0);
  });

  test('the API refuses a viewer even when the UI is bypassed', async ({ request }) => {
    const token = await apiLogin(request, viewer);
    const response = await request.post(`${API_URL}/api/projects/${projectKey}/issues`, {
      headers: auth(token),
      data: { title: 'Should not be created' },
    });
    expect(response.status()).toBe(403);
  });

  test('a non-member cannot read the project by guessing its key', async ({ request }) => {
    const token = await apiLogin(request, outsider);
    const response = await request.get(`${API_URL}/api/projects/${projectKey}`, {
      headers: auth(token),
    });
    expect(response.status()).toBe(403);
    expect(await response.text()).not.toContain('Visible only to members');
  });

  test('an unauthenticated API call is rejected', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/projects`);
    expect(response.status()).toBe(401);
  });
});
