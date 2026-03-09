/**
 * Frontend API config: base URL and WebSocket URL for the backend.
 * Set VITE_API_URL in .env (e.g. http://localhost:8000) to override the default.
 */

const DEFAULT_API_BASE = 'http://localhost:8000';

function getEnvApiBase(): string
{
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL)
  {
    const url = String(import.meta.env.VITE_API_URL).trim();
    if (url !== '')
    {
      return url.replace(/\/$/, '');
    }
  }
  return DEFAULT_API_BASE;
}

let cachedBase: string | null = null;

export function getApiBaseUrl(): string
{
  if (cachedBase === null)
  {
    cachedBase = getEnvApiBase();
  }
  return cachedBase;
}

export function getWsLogsUrl(): string
{
  const base = getApiBaseUrl();
  const wsProtocol = base.startsWith('https') ? 'wss' : 'ws';
  const host = base.replace(/^https?:\/\//, '');
  return `${wsProtocol}://${host}/ws/logs`;
}

export function sessionWorkflowUrl(sessionId: string): string
{
  return `${getApiBaseUrl()}/sessions/${sessionId}/workflow`;
}

export function sessionFilesUrl(sessionId: string): string
{
  return `${getApiBaseUrl()}/sessions/${sessionId}/files`;
}

export function sessionFileUrl(sessionId: string, filename: string): string
{
  return `${getApiBaseUrl()}/sessions/${sessionId}/${encodeURIComponent(filename)}`;
}

export function sessionSettingsUrl(sessionId: string): string
{
  return `${getApiBaseUrl()}/sessions/${sessionId}/settings`;
}

export function createSessionUrl(): string
{
  return `${getApiBaseUrl()}/sessions/create`;
}

export function runWorkflowUrl(): string
{
  return `${getApiBaseUrl()}/run`;
}

export function stopWorkflowUrl(): string
{
  return `${getApiBaseUrl()}/stop`;
}
