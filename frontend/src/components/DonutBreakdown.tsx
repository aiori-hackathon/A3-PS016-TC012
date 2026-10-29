
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export type DonutItem = {
  name: string;
  value: number;
  color: string;
};

type Props = {
  title: string;
  subtitle: string;
  items: DonutItem[];
};

export default function DonutBreakdown({
  title,
  subtitle,
  items,
}: Props) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  const visible = items.filter((item) => item.value > 0);

  return (
    <div className="donut-card">
      <div className="donut-heading">
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>

      <div className="donut-layout">
        <div className="donut-visual">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={visible}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={91}
                paddingAngle={visible.length > 1 ? 3 : 0}
                stroke="none"
                isAnimationActive={true}
              >
                {visible.map((item) => (
                  <Cell key={item.name} fill={item.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#1e252e",
                  border: "1px solid #455365",
                  borderRadius: 6,
                  color: "#f4f7fb",
                }}
              />
            </PieChart>
          </ResponsiveContainer>

          <div className="donut-center">
            <strong>{total}</strong>
            <span>Total</span>
          </div>
        </div>

        <div className="donut-legend">
          {items.map((item) => (
            <div className="donut-legend-row" key={item.name}>
              <span
                className="donut-legend-dot"
                style={{ background: item.color }}
              />
              <span className="donut-legend-name">{item.name}</span>
              <strong>{item.value}</strong>
              <small>
                {total > 0
                  ? `${((item.value / total) * 100).toFixed(1)}%`
                  : "N/A"}
              </small>
            </div>
          ))}
        </div>
      </div>

      {total === 0 && (
        <p className="donut-empty">No recorded events in this selection.</p>
      )}
    </div>
  );
}
