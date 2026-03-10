/**
 * Optimistic cache for session data. Components read from cache; on miss, fetch from API.
 * Cache can be invalidated when backend changes (e.g. via Supabase Realtime).
 */

import axios from 'axios';
import {
  sessionFileUrl,
  sessionFilesUrl,
  sessionWorkflowUrl,
} from './api';

export type WorkflowSessionSnapshot = {
  sessionId: string;
  status: string;
  settings?: { timeout?: number };
  agentOrder: string[];
  currentAgent?: string | null;
  currentRound?: number;
  startedAt?: string | null;
  updatedAt?: string | null;
  workflowResult?: string | null;
  workflowResultFile?: string | null;
  agents: Record<string, unknown>;
};

type SessionCacheEntry = {
  workflow: WorkflowSessionSnapshot | null;
  files: string[] | null;
  fileContents: Map<string, string>;
};

const cache = new Map<string, SessionCacheEntry>();

type InvalidateCallback = (sessionId: string) => void;

let onInvalidate: InvalidateCallback | null = null;

export function setInvalidateCallback(cb: InvalidateCallback | null): void
{
  onInvalidate = cb;
}

function getOrCreateEntry(sessionId: string): SessionCacheEntry
{
  let entry = cache.get(sessionId);
  if (!entry)
  {
    entry = {
      workflow: null,
      files: null,
      fileContents: new Map(),
    };
    cache.set(sessionId, entry);
  }
  return entry;
}

export async function getWorkflow(sessionId: string): Promise<WorkflowSessionSnapshot | null>
{
  const entry = getOrCreateEntry(sessionId);
  if (entry.workflow !== null)
  {
    return entry.workflow;
  }
  try
  {
    const res = await axios.get<WorkflowSessionSnapshot>(sessionWorkflowUrl(sessionId));
    entry.workflow = res.data;
    return entry.workflow;
  }
  catch (err)
  {
    if (axios.isAxiosError(err) && err.response?.status === 404)
    {
      throw err;
    }
    return null;
  }
}

export async function getFiles(sessionId: string): Promise<string[]>
{
  const entry = getOrCreateEntry(sessionId);
  if (entry.files !== null)
  {
    return entry.files;
  }
  try
  {
    const res = await axios.get<{ files: string[] }>(sessionFilesUrl(sessionId));
    entry.files = res.data.files ?? [];
    return entry.files;
  }
  catch
  {
    return [];
  }
}

export async function getFileContent(sessionId: string, filename: string): Promise<string>
{
  const entry = getOrCreateEntry(sessionId);
  const cached = entry.fileContents.get(filename);
  if (cached !== undefined)
  {
    return cached;
  }
  try
  {
    const res = await axios.get<{ content: string }>(sessionFileUrl(sessionId, filename));
    const content = res.data.content ?? '';
    entry.fileContents.set(filename, content);
    return content;
  }
  catch
  {
    throw new Error(`Failed to load ${filename}`);
  }
}

export function setWorkflow(sessionId: string, snapshot: WorkflowSessionSnapshot | null): void
{
  const entry = getOrCreateEntry(sessionId);
  entry.workflow = snapshot;
}

export function setFiles(sessionId: string, files: string[]): void
{
  const entry = getOrCreateEntry(sessionId);
  entry.files = files;
}

export function setFileContent(sessionId: string, filename: string, content: string): void
{
  const entry = getOrCreateEntry(sessionId);
  entry.fileContents.set(filename, content);
}

export function invalidateSession(sessionId: string): void
{
  cache.delete(sessionId);
  onInvalidate?.(sessionId);
}

export function invalidateWorkflow(sessionId: string): void
{
  const entry = cache.get(sessionId);
  if (entry)
  {
    entry.workflow = null;
    onInvalidate?.(sessionId);
  }
}

export function invalidateFile(sessionId: string, filename: string): void
{
  const entry = cache.get(sessionId);
  if (entry)
  {
    entry.fileContents.delete(filename);
    onInvalidate?.(sessionId);
  }
}

export function invalidateFiles(sessionId: string): void
{
  const entry = cache.get(sessionId);
  if (entry)
  {
    entry.files = null;
    entry.fileContents.clear();
    onInvalidate?.(sessionId);
  }
}
