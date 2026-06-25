const AUTH_STORAGE_KEY = "clinic_voice_agent_admin_session";

const FIXED_USERNAME = "admin";
const FIXED_PASSWORD = "Tatodobajocontrol";

function getStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

export function isAuthenticated(): boolean {
  return getStorage()?.getItem(AUTH_STORAGE_KEY) === "authenticated";
}

export function loginWithPassword(username: string, password: string): boolean {
  const isValid =
    username.trim() === FIXED_USERNAME && password === FIXED_PASSWORD;
  if (!isValid) {
    return false;
  }

  getStorage()?.setItem(AUTH_STORAGE_KEY, "authenticated");
  return true;
}

export function logout(): void {
  getStorage()?.removeItem(AUTH_STORAGE_KEY);
}
