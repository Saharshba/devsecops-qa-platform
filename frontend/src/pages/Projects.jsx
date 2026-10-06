import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, formatDateTime } from '../api/client';
import { useAuth } from '../auth';
import { usePolling } from '../hooks';
import { Card, Empty, ErrorBanner } from '../components/common';

export default function Projects() {
  const { atLeast } = useAuth();
  const canCreate = atLeast('MANAGER');
  const { data, error, loading, reload } = usePolling(() => api.projects(), { deps: [] });
  const [form, setForm] = useState({ key: '', name: '', description: '' });
  const [formError, setFormError] = useState(null);

  async function create(event) {
    event.preventDefault();
    setFormError(null);
    try {
      await api.createProject({ ...form, key: form.key.toUpperCase() });
      setForm({ key: '', name: '', description: '' });
      await reload();
    } catch (err) {
      setFormError(err);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <p className="subtle">You see the projects you are a member of.</p>
        </div>
      </div>

      <ErrorBanner error={error || formError} />

      <div className="grid charts">
        <Card title="Your projects">
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Key</th><th>Name</th><th className="num">Open</th><th className="num">Total</th>
                    <th className="num">Members</th><th>Created</th></tr>
              </thead>
              <tbody>
                {data?.map((project) => (
                  <tr key={project.id}>
                    <td className="mono">
                      <Link to={`/projects/${project.key}`} data-testid={`project-${project.key}`}>
                        {project.key}
                      </Link>
                    </td>
                    <td>{project.name}{project.is_archived && <span className="pill">archived</span>}</td>
                    <td className="num">{project.open_issues}</td>
                    <td className="num">{project.total_issues}</td>
                    <td className="num">{project.members.length}</td>
                    <td className="mono">{formatDateTime(project.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loading && !data?.length && <Empty>You are not a member of any project yet.</Empty>}
        </Card>

        {canCreate && (
          <Card title="New project" note="The key prefixes every issue, e.g. PAY-14.">
            <form onSubmit={create}>
              <label htmlFor="key">Key</label>
              <input id="key" name="key" value={form.key} required maxLength={10}
                     placeholder="PAY" style={{ width: '100%', textTransform: 'uppercase' }}
                     onChange={(e) => setForm({ ...form, key: e.target.value })} />
              <label htmlFor="name">Name</label>
              <input id="name" name="name" value={form.name} required style={{ width: '100%' }}
                     onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <label htmlFor="description">Description</label>
              <textarea id="description" rows={3} value={form.description} style={{ width: '100%' }}
                        onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <button className="primary" type="submit" data-testid="create-project">Create project</button>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
