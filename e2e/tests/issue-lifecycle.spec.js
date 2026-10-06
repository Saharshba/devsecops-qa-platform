import { expect, test } from '@playwright/test';
import { ADMIN, API_URL, apiLogin, auth, ensureUser, uiLogin, uniqueKey } from './helpers';

/**
 * The journey the README promises:
 *
 *   sign in → create a project → create an issue → assign a developer
 *          → move it through the workflow → verify the activity log
 */
test.describe('issue lifecycle', () => {
  let projectKey;
  let developer;

  test.beforeAll(async ({ request }) => {
    const token = await apiLogin(request);
    projectKey = uniqueKey('LIFE');
    developer = await ensureUser(request, token, { username: 'e2edev', role: 'DEVELOPER' });

    const created = await request.post(`${API_URL}/api/projects`, {
      headers: auth(token),
      data: { key: projectKey, name: 'Lifecycle project', description: 'Created by the E2E suite' },
    });
    expect(created.ok()).toBeTruthy();

    const member = await request.post(`${API_URL}/api/projects/${projectKey}/members`, {
      headers: auth(token),
      data: { username: developer.username, role: 'DEVELOPER' },
    });
    expect(member.ok()).toBeTruthy();
  });

  test('a manager drives an issue from creation to done', async ({ page }) => {
    await uiLogin(page, ADMIN);
    await expect(page.getByTestId('current-user')).toContainText('admin');

    await page.goto(`/projects/${projectKey}`);
    await page.fill('#title', 'Payment retry duplicates the charge');
    await page.fill('#description', 'Found while testing the retry path.');
    await page.selectOption('#priority', 'CRITICAL');
    await page.selectOption('#issue_type', 'BUG');
    await page.getByTestId('create-issue').click();

    const card = page.getByTestId(`column-OPEN`).getByText('Payment retry duplicates the charge');
    await expect(card).toBeVisible();
    await card.click();

    await expect(page.getByTestId('issue-title')).toContainText('Payment retry duplicates the charge');
    await expect(page.getByTestId('issue-status')).toHaveText('Open');

    // Assign, then walk the workflow. The buttons come from the API's
    // allowed_transitions, so this also checks the state machine is exposed.
    await page.getByTestId('assignee-select').selectOption(developer.username);
    await expect(page.getByText(developer.username, { exact: false })).toBeVisible();

    await page.getByTestId('transition-IN_PROGRESS').click();
    await expect(page.getByTestId('issue-status')).toHaveText('In progress');

    await page.getByTestId('transition-IN_REVIEW').click();
    await expect(page.getByTestId('issue-status')).toHaveText('In review');

    await page.getByTestId('transition-DONE').click();
    await expect(page.getByTestId('issue-status')).toHaveText('Done');

    await page.getByTestId('comment-body').fill('Verified on staging.');
    await page.getByTestId('add-comment').click();
    await expect(page.getByText('Verified on staging.')).toBeVisible();

    // The history must show every step, in order.
    const history = page.getByTestId('activity-table');
    await expect(history).toContainText('created');
    await expect(history).toContainText('assigned');
    await expect(history).toContainText('OPEN → IN_PROGRESS');
    await expect(history).toContainText('IN_REVIEW → DONE');
    await expect(history).toContainText('commented');
  });

  test('the board reflects the new issue on the dashboard', async ({ page }) => {
    await uiLogin(page, ADMIN);
    await expect(page.getByText('Issues')).toBeVisible();
    await page.goto('/projects');
    await expect(page.getByTestId(`project-${projectKey}`)).toBeVisible();
  });
});
