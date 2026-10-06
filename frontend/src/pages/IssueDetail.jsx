import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PRIORITIES, api, formatDateTime, humanise } from '../api/client';
import { usePolling } from '../hooks';
import { Card, Empty, ErrorBanner, PriorityBadge, StatusLabel } from '../components/common';

export default function IssueDetail() {
  const { issueKey } = useParams();
  const issue = usePolling(() => api.issue(issueKey), { deps: [issueKey] });
  const comments = usePolling(() => api.comments(issueKey), { deps: [issueKey] });
  const activity = usePolling(() => api.issueActivity(issueKey), { deps: [issueKey] });
  const members = usePolling(
    () => (issue.data ? api.users() : Promise.resolve([])),
    { deps: [issue.data?.id] },
  );

  const [comment, setComment] = useState('');
  const [actionError, setActionError] = useState(null);

  async function refresh() {
    await Promise.all([issue.reload(), comments.reload(), activity.reload()]);
  }

  async function apply(payload) {
    setActionError(null);
    try {
      await api.updateIssue(issueKey, payload);
      await refresh();
    } catch (err) {
      setActionError(err);
    }
  }

  async function submitComment(event) {
    event.preventDefault();
    setActionError(null);
    try {
      await api.addComment(issueKey, comment);
      setComment('');
      await refresh();
    } catch (err) {
      setActionError(err);
    }
  }

  if (issue.loading && !issue.data) return <p className="empty">Loading…</p>;
  if (issue.error) return <ErrorBanner error={issue.error} />;
  if (!issue.data) return null;

  const data = issue.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 data-testid="issue-title">{data.key} · {data.title}</h1>
          <p className="subtle">
            <Link to={`/projects/${data.key.split('-')[0]}`}>← Back to the board</Link> ·
            reported by {data.reporter} · {formatDateTime(data.created_at)}
          </p>
        </div>
        <PriorityBadge priority={data.priority} />
      </div>

      <ErrorBanner error={actionError} />

      <div className="grid charts" style={{ marginBottom: 14 }}>
        <Card title="Details">
          <dl className="kv">
            <dt>Status</dt><dd><StatusLabel status={data.status} /></dd>
            <dt>Type</dt><dd>{data.issue_type}</dd>
            <dt>Assignee</dt><dd>{data.assignee || 'Unassigned'}</dd>
            <dt>Labels</dt>
            <dd>{data.labels.length
              ? data.labels.map((l) => <span className="pill" key={l}>{l}</span>)
              : <span className="subtle">none</span>}</dd>
            <dt>Updated</dt><dd>{formatDateTime(data.updated_at)}</dd>
            {data.closed_at && <><dt>Closed</dt><dd>{formatDateTime(data.closed_at)}</dd></>}
          </dl>
          <p style={{ whiteSpace: 'pre-wrap' }}>{data.description || <span className="subtle">No description.</span>}</p>
        </Card>

        <Card title="Actions" note="The API enforces the workflow; buttons only show what it allows.">
          <div className="filters" style={{ marginBottom: 14 }}>
            {data.allowed_transitions.map((status) => (
              <button key={status} data-testid={`transition-${status}`}
                      className={status === 'IN_PROGRESS' ? 'primary' : ''}
                      onClick={() => apply({ status })}>
                Move to {humanise(status)}
              </button>
            ))}
            {!data.allowed_transitions.length && <span className="subtle">No transitions available.</span>}
          </div>

          <label htmlFor="assignee">Assignee</label>
          <select id="assignee" value={data.assignee || ''} style={{ width: '100%' }}
                  data-testid="assignee-select"
                  onChange={(e) => apply({ assignee: e.target.value || null })}>
            <option value="">Unassigned</option>
            {members.data?.map((user) => (
              <option key={user.id} value={user.username}>{user.username}</option>
            ))}
          </select>

          <label htmlFor="priority" style={{ marginTop: 10 }}>Priority</label>
          <select id="priority" value={data.priority} style={{ width: '100%' }}
                  onChange={(e) => apply({ priority: e.target.value })}>
            {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
          </select>
        </Card>
      </div>

      <div className="grid charts">
        <Card title="Comments">
          {comments.data?.map((item) => (
            <div key={item.id} style={{ borderBottom: '1px solid var(--grid)', padding: '10px 0' }}>
              <strong>{item.author}</strong>{' '}
              <span className="subtle">{formatDateTime(item.created_at)}</span>
              {item.edited_at && <span className="pill">edited</span>}
              <p style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>{item.body}</p>
            </div>
          ))}
          {!comments.data?.length && <Empty>No comments yet.</Empty>}

          <form onSubmit={submitComment} style={{ marginTop: 12 }}>
            <textarea rows={3} value={comment} required style={{ width: '100%' }}
                      data-testid="comment-body" placeholder="Add a comment"
                      onChange={(e) => setComment(e.target.value)} />
            <button className="primary" type="submit" data-testid="add-comment">Comment</button>
          </form>
        </Card>

        <Card title="History" note="Every change to this issue, in order.">
          <div className="table-wrap">
            <table data-testid="activity-table">
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
        </Card>
      </div>
    </>
  );
}
