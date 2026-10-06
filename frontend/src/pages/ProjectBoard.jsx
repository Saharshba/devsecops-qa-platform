import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ISSUE_TYPES, PRIORITIES, STATUSES, api, formatDateTime, humanise } from '../api/client';
import { useAuth } from '../auth';
import { usePolling } from '../hooks';
import { Card, Empty, ErrorBanner, PriorityBadge } from '../components/common';

export default function ProjectBoard() {
  const { projectKey } = useParams();
  const { atLeast } = useAuth();
  const canCreate = atLeast('DEVELOPER');

  const project = usePolling(() => api.project(projectKey), { deps: [projectKey] });
  const issues = usePolling(() => api.issues(projectKey, { limit: 200 }), {
    intervalMs: 20000, deps: [projectKey],
  });
  const activity = usePolling(() => api.projectActivity(projectKey), { deps: [projectKey] });

  const [form, setForm] = useState({
    title: '', description: '', priority: 'MEDIUM', issue_type: 'TASK', assignee: '',
  });
  const [formError, setFormError] = useState(null);

  async function create(event) {
    event.preventDefault();
    setFormError(null);
    try {
      await api.createIssue(projectKey, {
        ...form,
        assignee: form.assignee || null,
      });
      setForm({ title: '', description: '', priority: 'MEDIUM', issue_type: 'TASK', assignee: '' });
      await issues.reload();
      await activity.reload();
    } catch (err) {
      setFormError(err);
    }
  }

  const items = issues.data?.items ?? [];
  const members = project.data?.members ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{project.data?.name ?? projectKey}</h1>
          <p className="subtle">
            {project.data?.description || 'No description'} · {items.length} issues ·{' '}
            {members.length} members
          </p>
        </div>
        <Link to="/projects">All projects</Link>
      </div>

      <ErrorBanner error={project.error || issues.error || formError} />

      <div className="board" style={{ marginBottom: 14 }}>
        {STATUSES.map((status) => {
          const column = items.filter((issue) => issue.status === status);
          return (
            <div className="board-column" key={status} data-testid={`column-${status}`}>
              <h3>{humanise(status)} · {column.length}</h3>
              {column.map((issue) => (
                <div className="board-card" key={issue.id}>
                  <Link to={`/issues/${issue.key}`} data-testid={`issue-${issue.key}`}>
                    {issue.key} {issue.title}
                  </Link>
                  <div className="meta">
                    <PriorityBadge priority={issue.priority} />
                    <span className="pill">{issue.issue_type}</span>
                    <span>{issue.assignee ? `@${issue.assignee}` : 'unassigned'}</span>
                  </div>
                </div>
              ))}
              {!column.length && <p className="subtle">—</p>}
            </div>
          );
        })}
      </div>

      <div className="grid charts">
        {canCreate && (
          <Card title="New issue">
            <form onSubmit={create}>
              <label htmlFor="title">Title</label>
              <input id="title" name="title" value={form.title} required style={{ width: '100%' }}
                     onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <label htmlFor="description">Description</label>
              <textarea id="description" rows={3} value={form.description} style={{ width: '100%' }}
                        onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <label htmlFor="priority">Priority</label>
              <select id="priority" value={form.priority} style={{ width: '100%' }}
                      onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
              </select>
              <label htmlFor="issue_type">Type</label>
              <select id="issue_type" value={form.issue_type} style={{ width: '100%' }}
                      onChange={(e) => setForm({ ...form, issue_type: e.target.value })}>
                {ISSUE_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <label htmlFor="assignee">Assignee</label>
              <select id="assignee" value={form.assignee} style={{ width: '100%' }}
                      onChange={(e) => setForm({ ...form, assignee: e.target.value })}>
                <option value="">Unassigned</option>
                {members.map((member) => (
                  <option key={member.id} value={member.username}>{member.username}</option>
                ))}
              </select>
              <button className="primary" type="submit" data-testid="create-issue">Create issue</button>
            </form>
          </Card>
        )}

        <Card title="Project activity">
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
              <tbody>
                {activity.data?.map((entry) => (
                  <tr key={entry.id}>
                    <td className="mono">{formatDateTime(entry.created_at)}</td>
                    <td>{entry.actor_username}</td>
                    <td>{entry.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!activity.loading && !activity.data?.length && <Empty />}
        </Card>
      </div>
    </>
  );
}
