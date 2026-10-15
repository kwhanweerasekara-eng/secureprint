import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// The API stores UTC times without a zone ("2026-10-14T18:11:02"), which
// browsers would read as local time. Treat a time with no zone as UTC.
export function parseApiDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
}

export function formatDateTime(iso: string): string {
  return parseApiDate(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// Compact form for tables: "15 Oct, 00:04".
export function formatShortDateTime(iso: string): string {
  const d = parseApiDate(iso);
  const date = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}

// "MASK_AND_PRINT" -> "Mask and print"
export function humanize(value: string): string {
  const s = value.toLowerCase().replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return "-";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export const CATEGORY_LABELS: Record<string, string> = {
  nic: "NIC Numbers",
  card: "Payment Card Numbers",
  bank_account: "Bank Account Numbers",
  iban: "IBAN Numbers",
  passport: "Passport Numbers",
  email: "Email Addresses",
  telephone: "Telephone Numbers",
  credential: "Credentials",
  api_key: "API Keys & Secrets",
  salary: "Salary Information",
  employee_id: "Employee IDs",
  classification_marker: "Classification Markers",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || category;
}

export function eventLabel(type: string): string {
  return type
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
