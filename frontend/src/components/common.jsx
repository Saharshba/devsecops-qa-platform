import { PRIORITY_COLORS, humanise } from '../api/client';

export function Card({ title, note, children, action }) {
  return (
    <section className="card">
      {(title || action) && (
        <header className="page-head" style={{ marginBottom: 12 }}>
          <div>
            {title && <h2>{title}</h2>}
            {note && <p className="subtle" style={{ margin: 0 }}>{note}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, note }) {
  return (
    <div className="card">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  );
}

/* Priority is a state: the word is always present, colour only reinforces it. */
export function PriorityBadge({ priority }) {
  return (
    <span className={`badge prio-${priority}`} data-testid={`priority-${priority}`}>
      <span className="dot" style={{ background: PRIORITY_COLORS[priority] }} />
      {priority}
    </span>
  );
}

export function StatusLabel({ status }) {
  return <span data-testid="issue-status">{humanise(status)}</span>;
}

export function ErrorBanner({ error }) {
  if (!error) return null;
  return <div className="error" role="alert">{error.message || String(error)}</div>;
}

export function Empty({ children = 'Nothing here yet.' }) {
  return <p className="empty">{children}</p>;
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span className="legend-item" key={item.label}>
          <span className="legend-swatch" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
