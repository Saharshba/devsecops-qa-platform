import { api, formatDateTime } from '../api/client';
import { usePolling } from '../hooks';
import { Card, Empty, ErrorBanner } from '../components/common';

export default function Notifications() {
  const { data, error, loading, reload } = usePolling(() => api.notifications({ limit: 100 }), {
    intervalMs: 30000, deps: [],
  });

  async function markAll() {
    await api.markAllRead();
    await reload();
  }

  async function mark(id) {
    await api.markRead(id);
    await reload();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Notifications</h1>
          <p className="subtle">You are never notified about your own actions.</p>
        </div>
        <button onClick={markAll}>Mark all read</button>
      </div>

      <ErrorBanner error={error} />

      <Card>
        <div className="table-wrap">
          <table>
            <thead><tr><th>When</th><th>Type</th><th>Message</th><th></th></tr></thead>
            <tbody>
              {data?.map((item) => (
                <tr key={item.id} style={{ opacity: item.is_read ? 0.6 : 1 }}>
                  <td className="mono">{formatDateTime(item.created_at)}</td>
                  <td><span className="pill">{item.kind}</span></td>
                  <td>{item.message}</td>
                  <td>
                    {!item.is_read && (
                      <button onClick={() => mark(item.id)} style={{ padding: '2px 8px' }}>
                        Mark read
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !data?.length && <Empty>Nothing to catch up on.</Empty>}
      </Card>
    </>
  );
}
