import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric",
  });
}

export function severityColor(severity: string): string {
  const map: Record<string, string> = {
    critical: "text-red-600 bg-red-50 border-red-200",
    high:     "text-orange-600 bg-orange-50 border-orange-200",
    medium:   "text-yellow-600 bg-yellow-50 border-yellow-200",
    low:      "text-blue-600 bg-blue-50 border-blue-200",
    info:     "text-gray-600 bg-gray-50 border-gray-200",
  };
  return map[severity.toLowerCase()] ?? "text-gray-600 bg-gray-50 border-gray-200";
}
