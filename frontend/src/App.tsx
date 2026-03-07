import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Play, Settings, Trash2 } from 'lucide-react';
import { formatElapsedSeconds } from './utils/formatElapsed';
import Button from './components/Button';
import EditorPanel from './components/EditorPanel';
import LogList from './components/LogList';
import SettingsPage from './components/SettingsPage';
import StatusView from './components/StatusView';
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
  stepStartedAt?: string | null;
};

type WorkflowSessionSnapshot =
{
  sessionId: string;
  status: string;
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

const EDITOR_WIDTH_COOKIE_NAME = 'agent_lab_editor_width';
const LOG_HEIGHT_COOKIE_NAME = 'agent_lab_log_height';
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;
const CURRENT_SESSION_ID_STORAGE_KEY = 'agent_lab_current_session_id';

function clampPercentage(value: number, minimum: number, maximum: number): number
{
  return Math.min(maximum, Math.max(minimum, value));
}

function readPercentageCookie(
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

function writePercentageCookie(name: string, value: number): void
{
  document.cookie = `${name}=${value}; path=/; max-age=${COOKIE_MAX_AGE_SECONDS}; samesite=lax`;
}

function readStoredSessionId(): string | null
{
  if (typeof window === 'undefined')
  {
    return null;
  }

  return window.localStorage.getItem(CURRENT_SESSION_ID_STORAGE_KEY);
}

function writeStoredSessionId(sessionId: string | null): void
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

function getCurrentPathname(): string
{
  if (typeof window === 'undefined')
  {
    return '/';
  }

  return window.location.pathname;
}

function debugLog(hypothesisId: string, message: string, data: Record<string, unknown>): void
{
  // #region agent log
  fetch('http://127.0.0.1:7841/ingest/7bddab68-8e02-4480-82d9-70b8500c49f1',
  {
    method: 'POST',
    headers:
    {
      'Content-Type': 'application/json',
      'X-Debug-Session-Id': 'ecf5ab',
    },
    body: JSON.stringify(
    {
      sessionId: 'ecf5ab',
      runId: 'pre-fix',
      hypothesisId,
      location: 'frontend/src/App.tsx',
      message,
      data,
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
}

function App()
{
  const contentAreaRef = useRef<HTMLDivElement | null>(null);
  const mainSplitRef = useRef<HTMLDivElement | null>(null);
  const [pathname, setPathname] = useState(getCurrentPathname);
  const [code, setCode] = useState(`researcher = Agent(
    name="Researcher",
    role="Market researcher specializing in SaaS and B2B trends.",
    goal="Find and refine a promising SaaS idea based on analyst feedback",
    input=analyst.output
)

analyst = Agent(
  name="Analyst",
  role="Critical analyst who identifies flaws and improvement opportunities.",
  goal="Review the researcher's latest SaaS idea and only mark done when the idea is strong enough",
  input=researcher.output
)

workflow = Workflow(
  agents=
  [
    "researcher",
    "analyst"
  ],
  start_agent="researcher",
  max_rounds=8
)

workflow.run()`);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [agentOrder, setAgentOrder] = useState<string[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<Record<string, string>>({});
  const [workflowResult, setWorkflowResult] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(readStoredSessionId);
  const [editorActiveTab, setEditorActiveTab] = useState('code');
  const [isRunning, setIsRunning] = useState(false);
  const [, setTick] = useState(0);
  const [editorWidthPercent, setEditorWidthPercent] = useState(() => readPercentageCookie(EDITOR_WIDTH_COOKIE_NAME, 62, 30, 70));
  const [logHeightPercent, setLogHeightPercent] = useState(() => readPercentageCookie(LOG_HEIGHT_COOKIE_NAME, 28, 18, 55));
  const [timeoutSeconds, setTimeoutSeconds] = useState(240);
  const abortControllerRef = useRef<AbortController | null>(null);
  const workflowStartTimeRef = useRef<number | null>(null);
  const closedSocketIdsRef = useRef<Set<string>>(new Set());
  const currentSessionIdRef = useRef<string | null>(currentSessionId);
  const sessionRefreshTimeoutRef = useRef<number | null>(null);
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
    setWorkflowResult(null);
    workflowStartTimeRef.current = null;
  };

  const loadResultContent = async (sessionId: string, filename: string): Promise<string> =>
  {
    const response = await axios.get<SessionResultResponse>(
      `http://localhost:8000/sessions/${sessionId}/results/${encodeURIComponent(filename)}`,
    );
    return response.data.content;
  };

  const loadSession = async (sessionId: string) =>
  {
    try
    {
      const response = await axios.get<WorkflowSessionSnapshot>(
        `http://localhost:8000/sessions/${sessionId}/workflow`,
      );
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

      const nextAgentOutputs = Object.fromEntries(
        await Promise.all(
          agentNames.map(async (agentName) =>
          {
            const agentSnapshot = snapshotAgents[agentName];
            let output = '';

            if (typeof agentSnapshot?.lastResultFile === 'string' && agentSnapshot.lastResultFile !== '')
            {
              try
              {
                output = await loadResultContent(snapshot.sessionId, agentSnapshot.lastResultFile);
              }
              catch
              {
                output = '';
              }
            }

            return [agentName, output] as const;
          }),
        ),
      );

      let nextWorkflowResult = snapshot.workflowResult ?? null;
      if (typeof snapshot.workflowResultFile === 'string' && snapshot.workflowResultFile !== '')
      {
        try
        {
          nextWorkflowResult = await loadResultContent(snapshot.sessionId, snapshot.workflowResultFile);
        }
        catch
        {
          nextWorkflowResult = snapshot.workflowResult ?? null;
        }
      }

      setAgentOrder(agentNames);
      setAgentStatuses(nextAgentStatuses);
      setAgentOutputs(nextAgentOutputs);
      setWorkflowResult(nextWorkflowResult);

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
          const codeResponse = await axios.get<{ content: string }>(
            `http://localhost:8000/sessions/${snapshot.sessionId}/code`,
          );
          const sessionCode = codeResponse.data.content ?? '';
          setCode(sessionCode);
          lastSyncedCodeRef.current = sessionCode;
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
    if (sessionRefreshTimeoutRef.current !== null)
    {
      window.clearTimeout(sessionRefreshTimeoutRef.current);
    }

    sessionRefreshTimeoutRef.current = window.setTimeout(() =>
    {
      sessionRefreshTimeoutRef.current = null;
      void loadSession(sessionId);
    }, 50);
  };

  useEffect(() =>
  {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() =>
  {
    codeRef.current = code;
  }, [code]);

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

      void axios.put(`http://localhost:8000/sessions/${sessionId}/code`,
      {
        content: currentCode,
      })
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
    void axios.get<{ timeout: number }>('http://localhost:8000/settings')
      .then((res) => setTimeoutSeconds(res.data.timeout))
      .catch(() => {});

    if (currentSessionIdRef.current !== null)
    {
      void loadSession(currentSessionIdRef.current);
    }

    return () =>
    {
      if (sessionRefreshTimeoutRef.current !== null)
      {
        window.clearTimeout(sessionRefreshTimeoutRef.current);
      }
    };
  }, []);

  const handleRunAgent = async () =>
  {
    setLogs([]);
    clearSessionSnapshot();
    persistCurrentSessionId(null);
    setIsRunning(true);
    workflowStartTimeRef.current = Date.now();
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    // #region agent log
    debugLog('F1', 'run_agent_submit_start',
    {
      frontendOrigin: window.location.origin,
      backendUrl: 'http://localhost:8000/run',
      codeLength: code.length,
      online: navigator.onLine,
    });
    // #endregion

    try
    {
      const response = await axios.post('http://localhost:8000/run',
      {
        code,
      },
      {
        signal,
      });

      // #region agent log
      debugLog('F1', 'run_agent_submit_success',
      {
        status: response.status,
        data: response.data,
      });
      // #endregion

      if (typeof response.data.sessionId === 'string' && response.data.sessionId !== '')
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
        if (axios.isAxiosError(error))
        {
          // #region agent log
          debugLog('F2', 'run_agent_submit_axios_error',
          {
            message: error.message,
            code: error.code,
            status: error.response?.status,
            responseData: error.response?.data,
            hasRequest: error.request !== undefined,
            backendUrl: 'http://localhost:8000/run',
          });
          // #endregion
        }
        else
        {
          // #region agent log
          debugLog('F2', 'run_agent_submit_unknown_error',
          {
            error: String(error),
            backendUrl: 'http://localhost:8000/run',
          });
          // #endregion
        }

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
    try
    {
      await axios.post('http://localhost:8000/stop');
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
      socket = new WebSocket('ws://localhost:8000/ws/logs');

      socket.onopen = () =>
    {
      // #region agent log
      debugLog('F3', 'logs_socket_open',
      {
        socketUrl: 'ws://localhost:8000/ws/logs',
      });
      // #endregion
    };

    socket.onmessage = (event) =>
    {
      try
      {
        const logEntry = JSON.parse(event.data) as LogEntry;
        setLogs((currentLogs) => [...currentLogs, logEntry]);

        if (typeof logEntry.sessionId === 'string' && logEntry.sessionId !== '')
        {
          if (logEntry.eventType === 'workflow_started')
          {
            persistCurrentSessionId(logEntry.sessionId);
          }

          if (
            currentSessionIdRef.current === null ||
            currentSessionIdRef.current === logEntry.sessionId
          )
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
      // #region agent log
      debugLog('F3', 'logs_socket_error',
      {
        socketUrl: 'ws://localhost:8000/ws/logs',
      });
      // #endregion
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
    writePercentageCookie(EDITOR_WIDTH_COOKIE_NAME, editorWidthPercent);
  }, [editorWidthPercent]);

  useEffect(() =>
  {
    writePercentageCookie(LOG_HEIGHT_COOKIE_NAME, logHeightPercent);
  }, [logHeightPercent]);

  const hasActiveStep = Object.values(agentStatuses).some(
    (s) => s.state === 'thinking' || s.state === 'working',
  );
  const isWorkflowActive = isRunning || hasActiveStep;

  useEffect(() =>
  {
    if (!isWorkflowActive)
    {
      return;
    }

    const id = setInterval(() => setTick((t) => t + 1), 1000);

    return () => clearInterval(id);
  }, [isWorkflowActive]);

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

  const handleVerticalResizeStart = (event: React.PointerEvent<HTMLDivElement>) =>
  {
    const mainSplit = mainSplitRef.current;
    if (mainSplit === null)
    {
      return;
    }

    event.preventDefault();
    const rect = mainSplit.getBoundingClientRect();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const handlePointerMove = (moveEvent: PointerEvent) =>
    {
      const nextWidthPercent = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      setEditorWidthPercent(clampPercentage(nextWidthPercent, 30, 70));
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
        <h1 className={styles.appTitle}>Agent Lab</h1>
        <div className={styles.topBarActions}>
          {pathname === '/settings' ? (
            <Button variant="secondary" onClick={() => navigateTo('/')} icon={<ArrowLeft size={18} />}>
              Back To Lab
            </Button>
          ) : (
            <>
              <Button
                variant="run"
                onClick={isWorkflowActive ? handleStopWorkflow : handleRunAgent}
                icon={!isWorkflowActive ? <Play size={16} /> : undefined}
                showSpinner={isWorkflowActive}
                elapsedTime={isWorkflowActive ? formatElapsedSeconds(workflowElapsedSeconds) : undefined}
              >
                {isWorkflowActive ? 'Stop Workflow' : 'Run Workflow'}
              </Button>
              <Button
                variant="clearLogs"
                onClick={() => setLogs([])}
                icon={<Trash2 size={18} />}
                title="Clear Logs"
              >
                {''}
              </Button>
              <Button
                variant="secondary"
                onClick={() => navigateTo('/settings')}
                icon={<Settings size={18} />}
                title="Settings"
              >
                {''}
              </Button>
            </>
          )}
        </div>
      </header>

      {pathname === '/settings' ? (
        <div className={styles.contentArea}>
          <SettingsPage />
        </div>
      ) : (
        <div className={styles.contentArea} ref={contentAreaRef}>
          <div className={styles.mainArea} style={{ height: `calc(${100 - logHeightPercent}% - 4px)` }}>
            <div className={styles.mainSplit} ref={mainSplitRef}>
              <section className={styles.panel} style={{ width: `calc(${editorWidthPercent}% - 4px)` }}>
                <EditorPanel
                  code={code}
                  onCodeChange={setCode}
                  agentOutputs={agentOutputs}
                  agentNames={agentOrder.length > 0 ? agentOrder : Object.keys(agentStatuses)}
                  workflowResult={workflowResult}
                  activeTab={editorActiveTab}
                  onTabChange={setEditorActiveTab}
                />
              </section>

              <div
                className={styles.verticalResizeHandle}
                onPointerDown={handleVerticalResizeStart}
                role="separator"
                aria-label="Resize editor and status panels"
                aria-orientation="vertical"
              />

              <section className={styles.panel} style={{ width: `calc(${100 - editorWidthPercent}% - 4px)` }}>
                <StatusView
                  agentStatuses={
                    agentOrder.length > 0
                      ? [
                          ...agentOrder
                            .filter((name) => agentStatuses[name] !== undefined)
                            .map((name) => agentStatuses[name]),
                          ...Object.values(agentStatuses).filter(
                            (s) => !agentOrder.includes(s.name),
                          ),
                        ]
                      : Object.values(agentStatuses)
                  }
                  workflowResult={workflowResult}
                  timeoutSeconds={timeoutSeconds}
                  onShowAgentResults={(agentName) => setEditorActiveTab(`agent:${agentName}`)}
                  onShowWorkflowResult={() => setEditorActiveTab('workflow-result')}
                />
              </section>
            </div>
          </div>

          <div
            className={styles.horizontalResizeHandle}
            onPointerDown={handleHorizontalResizeStart}
            role="separator"
            aria-label="Resize logs panel"
            aria-orientation="horizontal"
          />

          <section className={`${styles.panel} ${styles.bottomPanel}`} style={{ height: `calc(${logHeightPercent}% - 4px)` }}>
            <LogList logs={logs} />
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
