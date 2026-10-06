/* One chart type, used twice: a horizontal bar count.
 *
 * Status counts are an ordered pipeline, so they use a single categorical hue
 * and rely on bar length; priority counts are a state, so they use the
 * reserved status palette with the labels always visible.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { PRIORITY_COLORS, formatNumber, humanise } from '../api/client';

const AXIS = { stroke: 'var(--axis)', tick: { fill: 'var(--text-muted)', fontSize: 11 } };

const TOOLTIP = {
  contentStyle: {
    background: 'var(--surface-1)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    fontSize: 12,
    color: 'var(--text-primary)',
  },
  labelStyle: { color: 'var(--text-secondary)' },
  cursor: { fill: 'var(--plane)' },
};

function Bars({ data, colors }) {
  if (!data.length) return <p className="empty">No issues yet.</p>;
  return (
    <>
      <ResponsiveContainer width="100%" height={34 * data.length + 34}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" {...AXIS} allowDecimals={false} tickFormatter={formatNumber} />
          <YAxis type="category" dataKey="label" {...AXIS} width={110} />
          <Tooltip {...TOOLTIP} formatter={(value) => [formatNumber(value), 'Issues']} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={16} fill="var(--series-1)">
            {colors && data.map((row) => <Cell key={row.label} fill={colors[row.key]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Bucket</th><th className="num">Issues</th></tr></thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td className="num">{formatNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function StatusChart({ counts }) {
  const data = (counts || []).map((row) => ({
    key: row.status, label: humanise(row.status), count: row.count,
  }));
  return <Bars data={data} />;
}

export function PriorityChart({ counts }) {
  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const data = order
    .map((priority) => ({
      key: priority,
      label: priority,
      count: (counts || []).find((c) => c.priority === priority)?.count ?? 0,
    }))
    .filter((row) => row.count > 0);
  return <Bars data={data} colors={PRIORITY_COLORS} />;
}
