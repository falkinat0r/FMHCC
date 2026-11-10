import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MetricPoint } from "../../api/fixtures";
import { formatTime } from "../../lib/format";

interface MetricChartProps {
  label: string;
  points: MetricPoint[];
  /** Einheit (z. B. "%", "GB") */
  unit: string;
  color?: string;
}

/**
 * Metrikdiagramm (Recharts). Wird NUR mit echten/Fixture-Daten
 * gerendert — bei fehlenden Daten zeigt die Aufrufer-Komponente
 * einen klaren "nicht verfuegbar"-Zustand (keine Mock-Charts in
 * der Produktivansicht).
 */
export function MetricChart({
  label,
  points,
  unit,
  color = "#35b5a2",
}: MetricChartProps) {
  if (points.length === 0) return null;
  return (
    <div aria-label={`Chart: ${label}`} className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id={`grad-${label.replace(/\s+/g, "-")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#263241" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="ts"
            tick={{ fill: "#93a1b0", fontSize: 10 }}
            tickFormatter={(value: string) => formatTime(value)}
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: "#93a1b0", fontSize: 10 }}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#151c24",
              border: "1px solid #263241",
              borderRadius: 6,
              fontSize: 11,
            }}
            labelStyle={{ color: "#93a1b0" }}
            formatter={(value, name) => [`${String(value)} ${unit}`, String(name)]}
            labelFormatter={(label) => formatTime(String(label))}
          />
          <Area
            type="monotone"
            dataKey="value"
            name={label}
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#grad-${label.replace(/\s+/g, "-")})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
