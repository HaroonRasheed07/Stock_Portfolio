// API base URL resolution order:
// 1. NEXT_PUBLIC_API_URL env var (explicit override)
// 2. Same hostname as the browser is viewing (enables LAN/mobile testing:
//    phone opens http://<dev-machine>:3000 -> API at http://<dev-machine>:8000)
// 3. localhost fallback (SSR / first render)
function resolveApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    // Only derive from hostname for network hosts; never for file:// etc.
    if (hostname && hostname !== "localhost" && hostname !== "127.0.0.1") {
      return `${protocol}//${hostname}:8000`;
    }
  }
  return "http://localhost:8000";
}

export const API_BASE_URL = resolveApiBase();

export async function fetchAPI<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: "Request failed" }));
    throw new Error(err.error || err.detail || `HTTP Error ${response.status}`);
  }

  const result = await response.json();
  return result.data !== undefined ? result.data : result;
}

/**
 * Fetch with provider-status awareness.
 * Returns { data, status } where status distinguishes:
 *   success | stale | partial | provider_unavailable
 * so UIs can show freshness banners instead of silently trusting old data.
 */
export async function fetchAPIWithStatus<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<{ data: T | null; status: "success" | "stale" | "partial" | "unavailable"; error?: string }> {
  try {
    const data = await fetchAPI<T>(endpoint, options);
    const anyData = data as any;
    let status: "success" | "stale" | "partial" | "unavailable" = "success";
    if (anyData?.from_stale_cache || anyData?.price?.from_stale_cache) status = "stale";
    else if (anyData?.status === "stale" || anyData?.price?.status === "stale") status = "stale";
    else if (anyData?.status === "partial") status = "partial";
    else if (
      anyData?.status === "provider_unavailable" ||
      anyData?.price?.status === "provider_unavailable"
    ) {
      return { data: null, status: "unavailable", error: anyData?.error || anyData?.price?.error };
    }
    return { data, status };
  } catch (err: any) {
    const msg = err?.message || "";
    if (msg.includes("503")) {
      return { data: null, status: "unavailable", error: msg };
    }
    throw err;
  }
}

export async function uploadFileAPI<T>(endpoint: string, formData: FormData): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: "Upload failed" }));
    throw new Error(err.error || err.detail || `HTTP Error ${response.status}`);
  }

  const result = await response.json();
  return result.data !== undefined ? result.data : result;
}
