import { Link } from 'react-router-dom';
import { api, formatDateTime, formatNumber } from '../api/client';
import { usePolling } from '../hooks';
import { PriorityChart, StatusChart } from '../components/charts';
import { Card, Empty, ErrorBanner, StatTile } from '../components/common';

export default function Dashboard() {
  const { data, error, loading } = usePolling(() => api.dashboard(), { intervalMs: 20000, deps: [] });

  if (loading && !data) return <p className="empty">Loading…</p>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="subtle">
            {data ? `Scoped to the projects you belong to · ${formatDateTime(data.generated_at)}` : ''}
          </p>
        </div>
      </div>

      <ErrorBanner error={error} />

      {!data ? <Empty /> : (
        <>
          <div className="grid tiles" style={{ marginBottom: 14 }}>
            <StatTile label="Projects" value={formatNumber(data.projects)} />
            <StatTile label="Issues" value={formatNumber(data.total_issues)}
                      note={`${data.open_issues} open`} />
            <StatTile label="Assigned to me" value={formatNumber(data.assigned_to_me)} />
            <StatTile label="Unread notifications" value={formatNumber(data.unread_notifications)} />
          </div>

          <div className="grid charts" style={{ marginBottom: 14 }}>
            <Card title="Issues by status">
              <StatusChart counts={data.issues_by_status} />
            </Card>
            <Card title="Issues by priority">
              <PriorityChart counts={data.issues_by_priority} />
            </Card>
          </div>

          <Card title="Recent activity" action={<Link to="/projects">All projects</Link>}>
            <div className="table-wrap">
              <table>
                <thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
                <tbody>
                  {data.recent_activity.map((entry) => (
                    <tr key={entry.id}>
                      <td className="mono">{formatDateTime(entry.created_at)}</td>
                      <td>{entry.actor_username}</td>
                      <td>{entry.summary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!data.recent_activity.length && <Empty>No activity recorded yet.</Empty>}
          </Card>
        </>
      )}
    </>
  );
}
