import { getBaseUrl } from "./api";

function isWbBasketImageUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    return (
      ["http:", "https:"].includes(parsed.protocol) &&
      (host === "wbbasket.ru" || host.endsWith(".wbbasket.ru")) &&
      parsed.pathname.includes("/images/")
    );
  } catch {
    return false;
  }
}

export function proxyWbImageUrl(src: string | null | undefined): string | null {
  const value = String(src ?? "").trim();
  if (!value) return null;
  if (!isWbBasketImageUrl(value)) return value;
  return `${getBaseUrl()}/photo/image-proxy?url=${encodeURIComponent(value)}`;
}
