import { useMemo } from "react";
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import { Radar } from "react-chartjs-2";

ChartJS.register(
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

interface RadarChartProps {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    backgroundColor?: string;
    borderColor?: string;
  }[];
}

const COLORS = [
  { bg: "rgba(59, 130, 246, 0.2)", border: "rgb(59, 130, 246)" },
  { bg: "rgba(239, 68, 68, 0.2)", border: "rgb(239, 68, 68)" },
  { bg: "rgba(34, 197, 94, 0.2)", border: "rgb(34, 197, 94)" },
  { bg: "rgba(234, 179, 8, 0.2)", border: "rgb(234, 179, 8)" },
  { bg: "rgba(168, 85, 247, 0.2)", border: "rgb(168, 85, 247)" },
];

/** Read a CSS custom property from :root and return a comma-format hsl() string
 *  that Chart.js / canvas can actually render. Falls back to a readable gray. */
function cssHsl(variable: string, fallback = "hsl(0, 0%, 50%)"): string {
  if (typeof document === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  if (!raw) return fallback;
  // raw is e.g. "222.2 84% 4.9%" → split on whitespace
  const parts = raw.split(/\s+/);
  if (parts.length >= 3) {
    return `hsl(${parts[0]}, ${parts[1]}, ${parts[2]})`;
  }
  return fallback;
}

export default function RadarChart({ labels, datasets }: RadarChartProps) {
  // Resolve theme colours once so they work inside the <canvas>
  const theme = useMemo(() => {
    const fg = cssHsl("--foreground");
    const popover = cssHsl("--popover");
    const popoverFg = cssHsl("--popover-foreground");
    const border = cssHsl("--border");
    const bg = cssHsl("--background");
    return { fg, popover, popoverFg, border, bg };
  }, []);

  const data = {
    labels,
    datasets: datasets.map((ds, i) => ({
      ...ds,
      backgroundColor: ds.backgroundColor || COLORS[i % COLORS.length].bg,
      borderColor: ds.borderColor || COLORS[i % COLORS.length].border,
      borderWidth: 2,
      pointRadius: 3,
      pointHoverRadius: 5,
    })),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    scales: {
      r: {
        beginAtZero: true,
        max: 100,
        ticks: {
          stepSize: 20,
          color: theme.fg,
          backdropColor: theme.bg,
          font: { size: 11, weight: "600" as const },
          z: 100,
        },
        grid: { color: theme.border },
        angleLines: { color: theme.border },
        pointLabels: {
          color: theme.fg,
          font: { size: 13, weight: "600" as const },
        },
      },
    },
    plugins: {
      legend: {
        position: "bottom" as const,
        labels: {
          color: theme.fg,
          font: { size: 12, weight: "500" as const },
          usePointStyle: true,
          padding: 16,
        },
      },
      tooltip: {
        enabled: true,
        backgroundColor: theme.popover,
        titleColor: theme.popoverFg,
        bodyColor: theme.popoverFg,
        borderColor: theme.border,
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
        boxPadding: 6,
        usePointStyle: true,
        callbacks: {
          labelColor: function (tooltipItem: any) {
            const dataset = tooltipItem.dataset;
            const color = dataset.borderColor || "rgba(0,0,0,0)";
            return {
              backgroundColor: color,
              borderColor: color,
            };
          },
        },
      },
    },
  };

  return <Radar data={data} options={options} />;
}
