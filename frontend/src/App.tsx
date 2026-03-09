import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Play, SquareStop } from 'lucide-react';
import { formatElapsedSeconds } from './utils/formatElapsed';
import {
  createSessionUrl,
  getWsLogsUrl,
  runWorkflowUrl,
  sessionFileUrl,
  sessionFilesUrl,
  sessionWorkflowUrl,
  stopWorkflowUrl,
} from './api';
import AppMenu from './components/AppMenu';
import Button from './components/Button';
import EditorPanel from './components/EditorPanel';
import LogList from './components/LogList';
import SettingsPage from './components/SettingsPage';
import {
  clampPercentage,
  LOG_HEIGHT_COOKIE_NAME,
  readPercentageCookie,
  readStoredSessionId,
  readStoredTheme,
  writePercentageCookie,
  writeStoredSessionId,
  writeStoredTheme,
} from './persistence';
import type { Theme } from './persistence';
import {
  addAgentSkeletonToCode,
  agentNameToKebab,
  buildDefaultCode,
  DEFAULT_CODE,
  deserializeWorkflowFromJson,
  extractAgentClassCode,
  extractWorkflowCode,
  getAgentDisplayNameFromFileContent,
  getEffectiveMaxRounds,
  parseAgentConfigsFromCode,
  removeAgentFromCode,
  serializeWorkflowToJson,
} from './workflowCode';
import type { WorkflowJson } from './workflowCode';
import styles from './App.module.css';

type LogEntry =
{
  timestamp: string;
  level: string;
  message: string;
  eventType?: string;
  agentName?: string;
  state?: string;
  round?: number;
  sessionId?: string;
  runId?: string;
  agentOrder?: string[];
};

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  stepStartTime?: number;
};

type SessionAgentSnapshot =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  lastResultFile?: string | null;
  resultFiles?: string[];
  rounds?: number[];
  stepStartedAt?: string | null;
};

type WorkflowSessionSnapshot =
{
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
  agents: Record<string, SessionAgentSnapshot>;
};

type SessionResultResponse =
{
  filename: string;
  content: string;
};

function getCurrentPathname(): string
{
  if (typeof window === 'undefined')
  {
    return '/';
  }

  return window.location.pathname;
}

function App()
{
  const contentAreaRef = useRef<HTMLDivElement | null>(null);
  const [pathname, setPathname] = useState(getCurrentPathname);
  const [theme, setTheme] = useState<Theme>(readStoredTheme);
  const [code, setCode] = useState(DEFAULT_CODE);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [agentOrder, setAgentOrder] = useState<string[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<Record<string, string>>({});
  const [agentOutputsByRound, setAgentOutputsByRound] = useState<Record<string, Record<number, string>>>({});
  const [agentRounds, setAgentRounds] = useState<Record<string, number[]>>({});
  const [workflowResult, setWorkflowResult] = useState<string | null>(null);
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [currentRound, setCurrentRound] = useState<number>(0);
  const [workflowStatus, setWorkflowStatus] = useState<string>('idle');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(readStoredSessionId);
  const [editorActiveTab, setEditorActiveTab] = useState('workflow');
  const [isRunning, setIsRunning] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [, setTick] = useState(0);
  const maxRounds = getEffectiveMaxRounds(code);
  const [logHeightPercent, setLogHeightPercent] = useState(() => readPercentageCookie(LOG_HEIGHT_COOKIE_NAME, 28, 18, 55));
  const abortControllerRef = useRef<AbortController | null>(null);
  const workflowStartTimeRef = useRef<number | null>(null);
  const closedSocketIdsRef = useRef<Set<string>>(new Set());
  const currentSessionIdRef = useRef<string | null>(currentSessionId);
  const sessionRefreshTimeoutRef = useRef<number | null>(null);
  const sessionRefreshInFlightRef = useRef<boolean>(false);
  const sessionRefreshPendingRef = useRef<{ sessionId: string } | null>(null);
  const sessionLoadGenerationRef = useRef<number>(0);
  const codeRef = useRef<string>(code);
  const lastSyncedCodeRef = useRef<string | null>(null);

  const persistCurrentSessionId = (sessionId: string | null) =>
  {
    currentSessionIdRef.current = sessionId;
    setCurrentSessionId(sessionId);
    writeStoredSessionId(sessionId);
  };

  const clearSessionSnapshot = () =>
  {
    setAgentStatuses({});
    setAgentOrder([]);
    setAgentOutputs({});
    setAgentOutputsByRound({});
    setAgentRounds({});
    setWorkflowResult(null);
    setCurrentAgent(null);
    setCurrentRound(0);
    setWorkflowStatus('idle');
    setIsStopping(false);
    workflowStartTimeRef.current = null;
  };

  const loadResultContent = async (sessionId: string, filename: string): Promise<string> =>
  {
    const response = await axios.get<SessionResultResponse>(
      sessionFileUrl(sessionId, filename),
    );
    return response.data.content;
  };

  const loadSession = async (
    sessionId: string,
    options?: { restoreWorkflowResult?: boolean },
  ) =>
  {
    const restoreWorkflowResult = options?.restoreWorkflowResult ?? true;
    const loadId = ++sessionLoadGenerationRef.current;
    try
    {
      const response = await axios.get<WorkflowSessionSnapshot>(
        sessionWorkflowUrl(sessionId),
      );
      if (sessionLoadGenerationRef.current !== loadId)
      {
        return;
      }
      if (currentSessionIdRef.current !== sessionId)
      {
        return;
      }
      const snapshot = response.data;
      const snapshotAgents = snapshot.agents ?? {};
      const orderedAgentNames = snapshot.agentOrder ?? [];
      const agentNames = [
        ...orderedAgentNames,
        ...Object.keys(snapshotAgents).filter((agentName) => !orderedAgentNames.includes(agentName)),
      ];

      const nextAgentStatuses = Object.fromEntries(
        agentNames.map((agentName) =>
        {
          const agentSnapshot = snapshotAgents[agentName];
          const parsedStepStartTime =
            typeof agentSnapshot?.stepStartedAt === 'string'
              ? Date.parse(agentSnapshot.stepStartedAt)
              : Number.NaN;

          return [
            agentName,
            {
              name: agentName,
              state: agentSnapshot?.state ?? 'waiting_for_turn',
              message: agentSnapshot?.message ?? '',
              round: agentSnapshot?.round,
              stepStartTime: Number.isNaN(parsedStepStartTime) ? undefined : parsedStepStartTime,
            },
          ];
        }),
      );

      const roundsByAgent: Record<string, number[]> = {};
      for (const agentName of agentNames)
      {
        const agentSnapshot = snapshotAgents[agentName];
        const rounds = agentSnapshot?.rounds ?? [];
        const resultFiles = agentSnapshot?.resultFiles ?? [];
        if (rounds.length > 0)
        {
          roundsByAgent[agentName] = [...rounds].sort((a, b) => a - b);
        }
        else if (resultFiles.length > 0)
        {
          const parsed = resultFiles
            .map((f) =>
            {
              const m = f.match(/^[^.]+_(\d+)\.md$/);
              return m ? parseInt(m[1], 10) : null;
            })
            .filter((r): r is number => r !== null);
          roundsByAgent[agentName] = [...new Set(parsed)].sort((a, b) => a - b);
        }
      }

      const outputsByRound: Record<string, Record<number, string>> = {};
      const lastOutputs: Record<string, string> = {};
      for (const agentName of agentNames)
      {
        const rounds = roundsByAgent[agentName] ?? [];
        outputsByRound[agentName] = {};
        let lastOutput = '';
        for (const r of rounds)
        {
          const filename = `${agentNameToKebab(agentName)}_${r}.md`;
          try
          {
            const content = await loadResultContent(snapshot.sessionId, filename);
            outputsByRound[agentName][r] = content;
            lastOutput = content;
          }
          catch
          {
            outputsByRound[agentName][r] = '';
          }
        }
        lastOutputs[agentName] = lastOutput;
      }

      const nextAgentOutputs = lastOutputs;

      let nextWorkflowResult: string | null = null;
      if (restoreWorkflowResult)
      {
        nextWorkflowResult = snapshot.workflowResult ?? null;
        if (typeof snapshot.workflowResultFile === 'string' && snapshot.workflowResultFile !== '')
        {
          try
          {
            nextWorkflowResult = await loadResultContent(
              snapshot.sessionId,
              snapshot.workflowResultFile,
            );
          }
          catch
          {
            nextWorkflowResult = snapshot.workflowResult ?? null;
          }
        }
      }

      if (sessionLoadGenerationRef.current !== loadId || currentSessionIdRef.current !== sessionId)
      {
        return;
      }

      setAgentOrder(agentNames);
      setAgentStatuses(nextAgentStatuses);
      setAgentOutputs(nextAgentOutputs);
      setAgentOutputsByRound(outputsByRound);
      setAgentRounds(roundsByAgent);
      setWorkflowResult(nextWorkflowResult);
      setCurrentAgent(snapshot.currentAgent ?? null);
      setCurrentRound(snapshot.currentRound ?? 0);
      setWorkflowStatus(snapshot.status ?? 'idle');

      const parsedStartedAt =
        typeof snapshot.startedAt === 'string'
          ? Date.parse(snapshot.startedAt)
          : Number.NaN;
      workflowStartTimeRef.current =
        snapshot.status === 'running' && !Number.isNaN(parsedStartedAt)
          ? parsedStartedAt
          : null;

      const isNewSession = currentSessionIdRef.current !== snapshot.sessionId;
      persistCurrentSessionId(snapshot.sessionId);

      if (isNewSession)
      {
        try
        {
          const filesRes = await axios.get<{ files: string[] }>(
            sessionFilesUrl(snapshot.sessionId),
          );
          const pyFiles = (filesRes.data.files ?? []).filter(
            (f) => f.endsWith('.py') && f !== 'workflow.py',
          );
          const [workflowCode, ...agentContents] = await Promise.all([
            loadResultContent(snapshot.sessionId, 'workflow.py').catch(() => ''),
            ...pyFiles.map((f) =>
              loadResultContent(snapshot.sessionId, f).catch(() => ''),
            ),
          ]);
          const withNames = agentContents
            .filter((c) => c !== '')
            .map((c) => [getAgentDisplayNameFromFileContent(c), c] as const);
          const nameToContent = new Map(withNames);
          const ordered = agentNames
            .map((name) => nameToContent.get(name))
            .filter((c): c is string => c !== undefined);
          const remaining = withNames
            .filter(([name]) => !agentNames.includes(name))
            .map(([, c]) => c);
          const orderedRemaining = ordered.concat(remaining);
          const agentPart = orderedRemaining.join('\n\n');
          const sessionCode =
            agentPart && workflowCode
              ? `${agentPart}\n\n${workflowCode}`
              : agentPart || workflowCode || '';
          const codeToUse = sessionCode || buildDefaultCode();
          setCode(codeToUse);
          lastSyncedCodeRef.current = sessionCode ? sessionCode : null;
        }
        catch
        {
          lastSyncedCodeRef.current = null;
        }
      }
    }
    catch (error)
    {
      const isMissingSession =
        axios.isAxiosError(error) && error.response?.status === 404;

      if (isMissingSession && currentSessionIdRef.current === sessionId)
      {
        persistCurrentSessionId(null);
        clearSessionSnapshot();
      }
    }
  };

  const scheduleSessionRefresh = (sessionId: string) =>
  {
    sessionRefreshPendingRef.current = { sessionId };

    if (sessionRefreshInFlightRef.current)
    {
      return;
    }

    if (sessionRefreshTimeoutRef.current !== null)
    {
      return;
    }

    sessionRefreshTimeoutRef.current = window.setTimeout(async () =>
    {
      sessionRefreshTimeoutRef.current = null;
      const sid = sessionRefreshPendingRef.current?.sessionId ?? sessionId;
      sessionRefreshInFlightRef.current = true;
      try
      {
        await loadSession(sid);
      }
      finally
      {
        sessionRefreshInFlightRef.current = false;
        const pending = sessionRefreshPendingRef.current;
        sessionRefreshPendingRef.current = null;
        if (pending !== null)
        {
          scheduleSessionRefresh(pending.sessionId);
        }
      }
    }, 100);
  };

  useEffect(() =>
  {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() =>
  {
    document.documentElement.setAttribute('data-theme', theme);
    writeStoredTheme(theme);
  }, [theme]);

  useEffect(() =>
  {
    codeRef.current = code;
  }, [code]);

  useEffect(() =>
  {
    if (editorActiveTab.startsWith('agent:'))
    {
      const agentName = editorActiveTab.replace('agent:', '');
      const configs = parseAgentConfigsFromCode(code);
      const hasConfig = configs.some((c) => c.name === agentName);
      if (!hasConfig)
      {
        setEditorActiveTab('workflow');
      }
    }
  }, [code, editorActiveTab]);

  useEffect(() =>
  {
    if (currentSessionId === null)
    {
      return;
    }

    const intervalId = window.setInterval(() =>
    {
      const sessionId = currentSessionIdRef.current;
      if (sessionId === null)
      {
        return;
      }

      const currentCode = codeRef.current;
      const lastSynced = lastSyncedCodeRef.current;
      if (currentCode === lastSynced)
      {
        return;
      }

      const workflowCode = extractWorkflowCode(currentCode);
      const configs = parseAgentConfigsFromCode(currentCode);
      const currentClassNames = new Set(configs.map((c) => c.className));
      const lastClassNames = lastSyncedCodeRef.current
        ? new Set(parseAgentConfigsFromCode(lastSyncedCodeRef.current).map((c) => c.className))
        : new Set<string>();
      const toDelete = [...lastClassNames].filter((cn) => !currentClassNames.has(cn));

      void Promise.all([
        axios.put(
          sessionFileUrl(sessionId, 'workflow.py'),
          { content: workflowCode },
        ),
        ...configs.map((cfg) =>
          axios.put(
            sessionFileUrl(sessionId, `${agentNameToKebab(cfg.className)}.py`),
            { content: extractAgentClassCode(currentCode, cfg.className) },
          ),
        ),
        ...toDelete.map((className) =>
          axios.delete(
            sessionFileUrl(sessionId, `${agentNameToKebab(className)}.py`),
          ),
        ),
      ])
        .then(() =>
        {
          lastSyncedCodeRef.current = currentCode;
        })
        .catch(() => {});
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [currentSessionId]);

  useEffect(() =>
  {
    const storedId = readStoredSessionId();
    if (storedId === null)
    {
      fetch('/default_workflow.json')
        .then((r) => (r.ok ? r.json() : null))
        .then((json: WorkflowJson | null) =>
        {
          if (json?.agents?.length)
          {
            setCode(deserializeWorkflowFromJson(json));
          }
        })
        .catch(() => {});
    }

    const ensureSession = async () =>
    {
      const storedId = readStoredSessionId();
      if (storedId !== null)
      {
        await loadSession(storedId, { restoreWorkflowResult: false });
        if (currentSessionIdRef.current === storedId)
        {
          return;
        }
      }

      try
      {
        const createRes = await axios.post<{ sessionId: string }>(createSessionUrl());
        const newId = createRes.data.sessionId;
        if (typeof newId === 'string' && newId !== '')
        {
          persistCurrentSessionId(newId);
          await loadSession(newId, { restoreWorkflowResult: false });
        }
      }
      catch
      {
        setLogs((prev) => [
          ...prev,
          {
            timestamp: new Date().toISOString(),
            level: 'error',
            message: 'Error: Failed to create session.',
          },
        ]);
      }
    };

    void ensureSession();

    return () =>
    {
      if (sessionRefreshTimeoutRef.current !== null)
      {
        window.clearTimeout(sessionRefreshTimeoutRef.current);
      }
    };
  }, []);

  const handleLoad = (json: WorkflowJson) =>
  {
    if (isRunning)
    {
      void handleStopWorkflow();
    }
    setCode(deserializeWorkflowFromJson(json));
  };

  const handleSave = () =>
  {
    const json = serializeWorkflowToJson(code);
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'workflow.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleNewSession = async () =>
  {
    try
    {
      const createRes = await axios.post<{ sessionId: string }>(createSessionUrl());
      const newId = createRes.data.sessionId;
      if (typeof newId !== 'string' || newId === '')
      {
        throw new Error('Invalid session ID');
      }
      persistCurrentSessionId(newId);
      clearSessionSnapshot();
      setLogs([]);
      await loadSession(newId);
      setEditorActiveTab('workflow');
    }
    catch
    {
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'Error: Failed to create session.',
        },
      ]);
    }
  };

  const handleRunAgent = async () =>
  {
    if (currentSessionId === null)
    {
      setLogs((prev) => [
        ...prev,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'Error: No session. Create a session first.',
        },
      ]);
      return;
    }

    setLogs([]);
    clearSessionSnapshot();
    setIsRunning(true);
    workflowStartTimeRef.current = Date.now();
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try
    {
      const response = await axios.post(runWorkflowUrl(),
      {
        code,
        sessionId: currentSessionId,
      },
      {
        signal,
      });

      if (response.data?.status === 'error')
      {
        setWorkflowStatus('error');
      }
      else if (typeof response.data.sessionId === 'string' && response.data.sessionId !== '')
      {
        lastSyncedCodeRef.current = code;
        await loadSession(response.data.sessionId);
      }
    }
    catch (error)
    {
      const isAborted = axios.isAxiosError(error) && error.code === 'ERR_CANCELED';

      if (!isAborted)
      {
        setWorkflowStatus('error');
        setLogs((currentLogs) => [
          ...currentLogs,
          {
            timestamp: new Date().toISOString(),
            level: 'error',
            message: 'Error: Failed to submit the agent script to the backend.',
          },
        ]);
      }
    }
    finally
    {
      setIsRunning(false);
      workflowStartTimeRef.current = null;
      abortControllerRef.current = null;
    }
  };

  const handleStopWorkflow = async () =>
  {
    setIsStopping(true);
    try
    {
      await axios.post(stopWorkflowUrl(), { sessionId: currentSessionId });
    }
    catch
    {
      // Ignore stop errors; abort will still cancel the request
    }
    abortControllerRef.current?.abort();
  };

  useEffect(() =>
  {
    const effectId = Math.random().toString(36).slice(2, 10);
    let socket: WebSocket | null = null;

    const timeoutId = setTimeout(() =>
    {
      socket = new WebSocket(getWsLogsUrl());

    socket.onmessage = (event) =>
    {
      try
      {
        const logEntry = JSON.parse(event.data) as LogEntry;
        setLogs((currentLogs) => [...currentLogs, logEntry]);

        if (typeof logEntry.sessionId === 'string' && logEntry.sessionId !== '')
        {
          const sessionMatches =
            currentSessionIdRef.current === null ||
            currentSessionIdRef.current === logEntry.sessionId;

          if (logEntry.eventType === 'workflow_started')
          {
            persistCurrentSessionId(logEntry.sessionId);
            const parsedTimestamp =
              typeof logEntry.timestamp === 'string'
                ? Date.parse(logEntry.timestamp)
                : Number.NaN;
            workflowStartTimeRef.current =
              !Number.isNaN(parsedTimestamp) ? parsedTimestamp : Date.now();
            setWorkflowStatus('running');
            if (Array.isArray(logEntry.agentOrder) && logEntry.agentOrder.length > 0)
            {
              setAgentOrder(logEntry.agentOrder);
            }
            void loadSession(logEntry.sessionId);
          }
          else if (logEntry.eventType === 'state' && logEntry.agentName != null)
          {
            const parsedTimestamp =
              typeof logEntry.timestamp === 'string'
                ? Date.parse(logEntry.timestamp)
                : Number.NaN;
            const ts = !Number.isNaN(parsedTimestamp) ? parsedTimestamp : Date.now();
            setAgentStatuses((prev) =>
            {
              const existing = prev[logEntry.agentName!];
              const stepStartTime =
                logEntry.state === 'working' || logEntry.state === 'executing'
                  ? ts
                  : logEntry.state === 'thinking'
                    ? (existing?.stepStartTime ?? ts)
                    : undefined;
              const next = { ...prev };
              next[logEntry.agentName!] = {
                name: logEntry.agentName!,
                state: logEntry.state ?? 'waiting_for_turn',
                message: logEntry.message ?? '',
                round: logEntry.round,
                stepStartTime,
              };
              return next;
            });
            if (logEntry.agentName != null)
            {
              setCurrentAgent(logEntry.agentName);
            }
            if (typeof logEntry.round === 'number')
            {
              setCurrentRound(logEntry.round);
            }
          }
          else if (logEntry.eventType === 'handoff' && logEntry.agentName != null)
          {
            setCurrentAgent(logEntry.agentName);
            if (typeof logEntry.round === 'number')
            {
              setCurrentRound(logEntry.round);
            }
          }
          else if (logEntry.eventType === 'workflow_result')
          {
            setWorkflowResult(logEntry.message ?? null);
            if (logEntry.state === 'done')
            {
              setWorkflowStatus('done');
            }
          }
          else if (
            logEntry.eventType === 'system' &&
            logEntry.state != null &&
            ['done', 'stopped', 'error'].includes(logEntry.state)
          )
          {
            setWorkflowStatus(logEntry.state);
            if (logEntry.state === 'stopped')
            {
              setAgentStatuses((prev) =>
              {
                const next = { ...prev };
                for (const name of Object.keys(next))
                {
                  const s = next[name];
                  if (
                    s.state === 'working' ||
                    s.state === 'thinking' ||
                    s.state === 'executing'
                  )
                  {
                    next[name] = {
                      ...s,
                      state: 'waiting_for_turn',
                      message: 'Workflow stopped.',
                      stepStartTime: undefined,
                    };
                  }
                }
                return next;
              });
            }
          }
          else if (
            logEntry.eventType === 'thought' &&
            logEntry.agentName != null &&
            typeof logEntry.round === 'number'
          )
          {
            const agentName = logEntry.agentName;
            const round = logEntry.round;
            const message = logEntry.message ?? '';
            setAgentOutputsByRound((prev) =>
            {
              const next = { ...prev };
              const byRound = { ...(next[agentName] ?? {}) };
              byRound[round] = message;
              next[agentName] = byRound;
              return next;
            });
            setAgentRounds((prev) =>
            {
              const current = prev[agentName] ?? [];
              if (current.includes(round))
              {
                return prev;
              }
              const next = [...current, round].sort((a, b) => a - b);
              return { ...prev, [agentName]: next };
            });
            setAgentOutputs((prev) => ({ ...prev, [agentName]: message }));
          }

          if (sessionMatches)
          {
            scheduleSessionRefresh(logEntry.sessionId);
          }
        }
      }
      catch
      {
        setLogs((currentLogs) => [
          ...currentLogs,
          {
            timestamp: new Date().toISOString(),
            level: 'error',
            message: 'Received an invalid log payload.',
          },
        ]);
      }
    };

    socket.onerror = () =>
    {
      if (closedSocketIdsRef.current.has(effectId))
      {
        return;
      }
      setLogs((currentLogs) => [
        ...currentLogs,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'WebSocket connection error.',
        },
      ]);
    };
    }, 0);

    return () =>
    {
      clearTimeout(timeoutId);
      closedSocketIdsRef.current.add(effectId);
      if (socket !== null)
      {
        socket.close();
      }
    };
  }, []);

  useEffect(() =>
  {
    writePercentageCookie(LOG_HEIGHT_COOKIE_NAME, logHeightPercent);
  }, [logHeightPercent]);

  const hasActiveStep = Object.values(agentStatuses).some(
    (s) =>
      s.state === 'working' ||
      s.state === 'executing' ||
      s.state === 'thinking',
  );

  useEffect(() =>
  {
    const shouldTick = hasActiveStep || workflowStatus === 'running' || isRunning;
    if (!shouldTick)
    {
      return;
    }

    const id = setInterval(() => setTick((t) => t + 1), 1000);

    return () => clearInterval(id);
  }, [hasActiveStep, workflowStatus, isRunning]);

  const workflowElapsedSeconds =
    workflowStartTimeRef.current !== null
      ? Math.floor((Date.now() - workflowStartTimeRef.current) / 1000)
      : 0;

  useEffect(() =>
  {
    const handlePopState = () =>
    {
      setPathname(window.location.pathname);
    };

    window.addEventListener('popstate', handlePopState);

    return () =>
    {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  const navigateTo = (nextPathname: string) =>
  {
    if (window.location.pathname === nextPathname)
    {
      return;
    }

    window.history.pushState({}, '', nextPathname);
    setPathname(nextPathname);
  };

  const handleHorizontalResizeStart = (event: React.PointerEvent<HTMLDivElement>) =>
  {
    const contentArea = contentAreaRef.current;
    if (contentArea === null)
    {
      return;
    }

    event.preventDefault();
    const rect = contentArea.getBoundingClientRect();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'row-resize';

    const handlePointerMove = (moveEvent: PointerEvent) =>
    {
      const bottomHeightPercent = ((rect.bottom - moveEvent.clientY) / rect.height) * 100;
      setLogHeightPercent(clampPercentage(bottomHeightPercent, 18, 55));
    };

    const handlePointerUp = () =>
    {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  };

  return (
    <div className={styles.appShell}>
      <header className={styles.topBar}>
        <div className={styles.topBarLeft}>
          <AppMenu
            theme={theme}
            onThemeToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            onNew={handleNewSession}
            onLoad={handleLoad}
            onSave={handleSave}
            onSettings={() => navigateTo('/settings')}
            onClearLogs={() => setLogs([])}
          />
          <h1 className={styles.appTitle}>Agent Lab</h1>
        </div>
        <div className={styles.topBarActions}>
          {pathname === '/settings' ? (
            <Button variant="secondary" onClick={() => navigateTo('/')} icon={<ArrowLeft size={18} />}>
              Back To Lab
            </Button>
          ) : (
            <Button
              variant={isRunning || hasActiveStep || isStopping ? 'runActive' : 'run'}
              onClick={isStopping ? undefined : (isRunning || hasActiveStep ? handleStopWorkflow : handleRunAgent)}
              icon={isStopping ? undefined : (isRunning || hasActiveStep ? <SquareStop size={14} /> : <Play size={16} />)}
              showSpinner={isStopping}
              disabled={isStopping}
            >
              {isStopping ? 'Stopping Workflow...' : (isRunning || hasActiveStep ? 'Stop Workflow' : 'Run Workflow')}
            </Button>
          )}
        </div>
      </header>

      {pathname === '/settings' ? (
        <div className={styles.contentArea}>
          <SettingsPage sessionId={currentSessionId} />
        </div>
      ) : (
        <div className={styles.contentArea} ref={contentAreaRef}>
          <div className={styles.mainArea} style={{ height: `calc(${100 - logHeightPercent}% - var(--space-resize-gap))` }}>
            <section className={styles.panel} style={{ flex: 1 }}>
              <EditorPanel
                theme={theme}
                code={code}
                onCodeChange={setCode}
                agentOutputs={agentOutputs}
                agentOutputsByRound={agentOutputsByRound}
                agentRounds={agentRounds}
                agentStatuses={agentStatuses}
                agentOrder={agentOrder}
                workflowId={currentSessionId}
                maxRounds={maxRounds}
                currentAgent={currentAgent}
                currentRound={currentRound}
                workflowStatus={workflowStatus}
                workflowResult={workflowResult}
                workflowRunning={isRunning || hasActiveStep}
                workflowElapsedTime={
                  (isRunning || hasActiveStep)
                    ? formatElapsedSeconds(workflowElapsedSeconds)
                    : undefined
                }
                activeTab={editorActiveTab}
                onTabChange={setEditorActiveTab}
                onCloseAgentTab={(agentName: string) =>
                {
                  const configs = parseAgentConfigsFromCode(code);
                  const config = configs.find((c) => c.name === agentName);
                  if (config && currentSessionId !== null)
                  {
                    void axios.delete(
                      sessionFileUrl(currentSessionId, `${agentNameToKebab(config.className)}.py`),
                    ).catch(() => {});
                  }
                  const newCode = removeAgentFromCode(code, agentName);
                  if (newCode !== null)
                  {
                    setCode(newCode);
                    if (editorActiveTab === `agent:${agentName}`)
                    {
                      setEditorActiveTab('workflow');
                    }
                  }
                }}
                onAddAgent={() =>
                {
                  const { code: newCode, newAgentName } = addAgentSkeletonToCode(code);
                  setCode(newCode);
                  setEditorActiveTab(`agent:${newAgentName}`);
                }}
              />
            </section>
          </div>

          <div
            className={styles.horizontalResizeHandle}
            onPointerDown={handleHorizontalResizeStart}
            role="separator"
            aria-label="Resize logs panel"
            aria-orientation="horizontal"
          />

          <section className={`${styles.panel} ${styles.bottomPanel}`} style={{ height: `calc(${logHeightPercent}% - var(--space-resize-gap))` }}>
            <LogList logs={logs} />
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
