/**
 * Browser persistence: theme, session id, and layout cookies.
 */

export const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

export const LOG_HEIGHT_COOKIE_NAME = 'agent_lab_log_height';
export const CODE_PANE_WIDTH_COOKIE = 'agent_lab_code_pane_width';
export const CURRENT_SESSION_ID_STORAGE_KEY = 'agent_lab_current_session_id';
export const THEME_STORAGE_KEY = 'agent_lab_theme';

export type Theme = 'dark' | 'light';

export function readStoredTheme(): Theme
{
  if (typeof window === 'undefined')
  {
    return 'dark';
  }
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === 'light' ? 'light' : 'dark';
}

export function writeStoredTheme(theme: Theme): void
{
  if (typeof window === 'undefined')
  {
    return;
  }
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export function readStoredSessionId(): string | null
{
  if (typeof window === 'undefined')
  {
    return null;
  }

  return window.localStorage.getItem(CURRENT_SESSION_ID_STORAGE_KEY);
}

export function writeStoredSessionId(sessionId: string | null): void
{
  if (typeof window === 'undefined')
  {
    return;
  }

  if (sessionId === null || sessionId === '')
  {
    window.localStorage.removeItem(CURRENT_SESSION_ID_STORAGE_KEY);
    return;
  }

  window.localStorage.setItem(CURRENT_SESSION_ID_STORAGE_KEY, sessionId);
}

export function clampPercentage(value: number, minimum: number, maximum: number): number
{
  return Math.min(maximum, Math.max(minimum, value));
}

export function readPercentageCookie(
  name: string,
  fallbackValue: number,
  minimum: number,
  maximum: number,
): number
{
  if (typeof document === 'undefined')
  {
    return fallbackValue;
  }

  const cookieEntry = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`));

  if (cookieEntry === undefined)
  {
    return fallbackValue;
  }

  const storedValue = Number(cookieEntry.split('=').slice(1).join('='));
  if (Number.isNaN(storedValue))
  {
    return fallbackValue;
  }

  return clampPercentage(storedValue, minimum, maximum);
}

export function writePercentageCookie(name: string, value: number): void
{
  document.cookie = `${name}=${value}; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
}

export function readCodePaneWidth(): number
{
  if (typeof document === 'undefined')
  {
    return 50;
  }
  const entry = document.cookie.split('; ').find((e) => e.startsWith(`${CODE_PANE_WIDTH_COOKIE}=`));
  if (!entry)
  {
    return 50;
  }
  const val = Number(entry.split('=').slice(1).join('='));
  return Number.isNaN(val) ? 50 : Math.min(70, Math.max(30, val));
}

export function writeCodePaneWidth(value: number): void
{
  document.cookie = `${CODE_PANE_WIDTH_COOKIE}=${value}; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
}
