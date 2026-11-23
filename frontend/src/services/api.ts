export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'CUSTOMER' | 'ADMIN';
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// In-memory token store (avoids vulnerable localStorage token persistence)
let inMemoryToken: string | null = null;

export function setApiToken(token: string | null) {
  inMemoryToken = token;
}

export function getApiToken(): string | null {
  return inMemoryToken;
}

export async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // Supply in-memory Bearer token if available
  if (inMemoryToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${inMemoryToken}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: options.credentials || 'include', // Transport HttpOnly cookie automatically
  });

  const data = await response.json().catch(() => null);

  if (response.status === 401) {
    inMemoryToken = null;
    window.dispatchEvent(new CustomEvent('fraudguard:session-expired'));
    const errorMsg = data?.detail || data?.message || 'Session expired. Please sign in again.';
    throw new Error(errorMsg);
  }

  if (!response.ok) {
    const errorMsg = data?.detail || data?.message || `Request failed with status ${response.status}`;
    throw new Error(errorMsg);
  }

  return data as T;
}
