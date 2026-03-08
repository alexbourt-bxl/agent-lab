import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Play } from 'lucide-react';
import { formatElapsedSeconds } from './utils/formatElapsed';
import AppMenu from './components/AppMenu';
import Button from './components/Button';
import EditorPanel, {
  extractAgentClassCode,
  extractWorkflowCode,
} from './components/EditorPanel';
import LogList from './components/LogList';
import SettingsPage from './components/SettingsPage';
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

const LOG_HEIGHT_COOKIE_NAME = 'agent_lab_log_height';
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;
const CURRENT_SESSION_ID_STORAGE_KEY = 'agent_lab_current_session_id';

function parseAgentConfigsFromCode(code: string): Array<{ name: string; className: string; variable: string }>
{
  const configs: Array<{ name: string; className: string; variable: string }> = [];
  const classMatches = [...code.matchAll(/class (\w+)\(Agent\):\s*/g)];
  const classesByName = new Map<string, { name: string }>();

  for (let i = 0; i < classMatches.length; i++)
  {
    const className = classMatches[i][1];
    const bodyStart = classMatches[i].index! + classMatches[i][0].length;
    const bodyEnd = i + 1 < classMatches.length
      ? classMatches[i + 1].index!
      : code.length;
    const nextClass = code.slice(bodyStart).match(/\nclass \w+\(Agent\)/);
    const end = nextClass
      ? bodyStart + nextClass.index!
      : bodyEnd;
    const body = code.slice(bodyStart, end);
    const nameMatch = body.match(/name\s*=\s*["']([^"']*)["']/);
    classesByName.set(className, {
      name: nameMatch ? nameMatch[1].trim() : className,
    });
  }

  for (const [className, attrs] of classesByName)
  {
    let variable = '';
    const pattern = new RegExp(
      `(\\w+)\\s*=\\s*${className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\(`,
      'g',
    );
    let m;
    while ((m = pattern.exec(code)) !== null)
    {
      const argsStart = m.index + m[0].length;
      const argsEnd = findMatchingParen(code, argsStart - 1);
      const argumentsStr = code.slice(argsStart, argsEnd);
      const goalMatch = argumentsStr.match(/goal\s*=\s*["']([^"']*)["']/);
      if (goalMatch)
      {
        variable = m[1];
        break;
      }
    }
    configs.push({
      name: attrs.name || className,
      className,
      variable: variable || className.charAt(0).toLowerCase() + className.slice(1),
    });
  }

  configs.sort((a, b) =>
  {
    const instA = code.indexOf(`${a.variable} = ${a.className}`);
    const instB = code.indexOf(`${b.variable} = ${b.className}`);
    const idxA = instA >= 0 ? instA : code.indexOf(`class ${a.className}(Agent)`);
    const idxB = instB >= 0 ? instB : code.indexOf(`class ${b.className}(Agent)`);
    return idxA - idxB;
  });
  return configs;
}

function getAgentDisplayNameFromFileContent(content: string): string
{
  const nameMatch = content.match(/name\s*=\s*["']([^"']*)["']/);
  if (nameMatch && nameMatch[1].trim())
  {
    return nameMatch[1].trim();
  }
  const classMatch = content.match(/class (\w+)\(Agent\)/);
  return classMatch ? classMatch[1] : '';
}

function agentNameToKebab(name: string): string
{
  const result: string[] = [];
  for (let i = 0; i < name.length; i++)
  {
    const c = name[i];
    if (/\s/.test(c))
    {
      if (result.length > 0 && result[result.length - 1] !== '-')
      {
        result.push('-');
      }
    }
    else if (/[A-Z]/.test(c) && i > 0 && result.length > 0 && result[result.length - 1] !== '-')
    {
      result.push('-');
      result.push(c.toLowerCase());
    }
    else if (/[a-zA-Z0-9]/.test(c))
    {
      result.push(c.toLowerCase());
    }
  }
  return result.join('').replace(/--/g, '-').replace(/^-+|-+$/g, '') || 'agent';
}

function findMatchingParen(str: string, openIndex: number): number
{
  let depth = 1;
  for (let i = openIndex + 1; i < str.length; i++)
  {
    if (str[i] === '(')
    {
      depth++;
    }
    else if (str[i] === ')')
    {
      depth--;
      if (depth === 0)
      {
        return i;
      }
    }
  }
  return str.length;
}

function removeAgentFromCode(code: string, agentName: string): string | null
{
  const configs = parseAgentConfigsFromCode(code);
  const config = configs.find((c) => c.name === agentName);
  if (!config)
  {
    return null;
  }

  const escapedClass = config.className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escapedVar = config.variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  let result = code;

  const classRegex = new RegExp(
    `class ${escapedClass}\\(Agent\\):\\s*\\n(?:    .+\\n)*`,
    'g',
  );
  result = result.replace(classRegex, '');

  const instanceRegex = new RegExp(
    `${escapedVar}\\s*=\\s*${escapedClass}\\s*\\([^)]*\\)\\s*\\n?`,
    'g',
  );
  result = result.replace(instanceRegex, '');

  return result.replace(/\n{3,}/g, '\n\n').trim();
}

type AgentCodeConfig =
{
  className: string;
  displayName: string;
  role: string;
  tools: string;
  variableName: string;
  goal: string;
  input: string;
};

function createAgentCode(config: AgentCodeConfig): { classDef: string; instantiation: string }
{
  const classDef = `
class ${config.className}(Agent):
    name = "${config.displayName}"
    role = "${config.role}"
    tools = ${config.tools}
`;
  const instantiation = `${config.variableName} = ${config.className}(\n    goal="${config.goal}",\n    input=${config.input}\n)`;
  return { classDef, instantiation };
}

function addAgentSkeletonToCode(code: string): { code: string; newAgentName: string }
{
  const configs = parseAgentConfigsFromCode(code);
  const newAgentNums = configs
    .map((c) =>
    {
      if (c.name === 'New Agent')
      {
        return 1;
      }
      const m = c.name.match(/^New Agent (\d+)$/);
      return m ? Number(m[1]) : 0;
    })
    .filter((n) => n > 0);
  const nextNum = newAgentNums.length > 0 ? Math.max(...newAgentNums) + 1 : 1;
  const displayName = nextNum === 1 ? 'New Agent' : `New Agent ${nextNum}`;
  const className = `NewAgent${nextNum}`;
  const variableName = nextNum === 1 ? 'newAgent' : `newAgent${nextNum}`;
  const { classDef, instantiation } = createAgentCode(
  {
    className,
    displayName,
    role: '',
    tools: '[ReadFile, WriteFile]',
    variableName,
    goal: '...',
    input: '...',
  });

  if (configs.length === 0)
  {
    return {
      code: code.trimEnd() + classDef + '\n\n' + instantiation + '\n',
      newAgentName: displayName,
    };
  }

  const firstIdx = code.indexOf(`${configs[0].variable} = ${configs[0].className}`);
  if (firstIdx < 0)
  {
    return {
      code: code.trimEnd() + classDef + '\n\n' + instantiation + '\n',
      newAgentName: displayName,
    };
  }

  const beforeInstantiations = code.slice(0, firstIdx).trimEnd();
  const instantiations = code.slice(firstIdx).trimStart();

  const withNewClass = beforeInstantiations + classDef + '\n\n' + instantiations;
  return {
    code: withNewClass.trimEnd() + '\n\n' + instantiation + '\n',
    newAgentName: displayName,
  };
}

function buildDefaultCode(): string
{
  const researcher = createAgentCode(
  {
    className: 'Researcher',
    displayName: 'Researcher',
    role: 'Market researcher specializing in SaaS and B2B trends.',
    tools: '[ReadFile, WriteFile]',
    variableName: 'researcher',
    goal: "Find and refine a promising SaaS idea based on analyst feedback",
    input: 'analyst.output',
  });
  const analyst = createAgentCode(
  {
    className: 'Analyst',
    displayName: 'Analyst',
    role: "Critical analyst who identifies flaws and improvement opportunities.",
    tools: '[ReadFile, WriteFile]',
    variableName: 'analyst',
    goal: "Review the researcher's latest SaaS idea and only mark done when the idea is strong enough",
    input: 'researcher.output',
  });
  return (
    researcher.classDef.trim() +
    '\n\n' +
    analyst.classDef.trim() +
    '\n\n' +
    researcher.instantiation +
    '\n\n' +
    analyst.instantiation +
    '\n'
  );
}

const DEFAULT_CODE = buildDefaultCode();

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
  const [pathname, setPathname] = useState(getCurrentPathname);
  const [code, setCode] = useState(DEFAULT_CODE);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [agentOrder, setAgentOrder] = useState<string[]>([]);
  const [agentOutputs, setAgentOutputs] = useState<Record<string, string>>({});
  const [workflowResult, setWorkflowResult] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(readStoredSessionId);
  const [editorActiveTab, setEditorActiveTab] = useState('workflow');
  const [isRunning, setIsRunning] = useState(false);
  const [, setTick] = useState(0);
  const [maxRounds, setMaxRounds] = useState(8);
  const [logHeightPercent, setLogHeightPercent] = useState(() => readPercentageCookie(LOG_HEIGHT_COOKIE_NAME, 28, 18, 55));
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
      `http://localhost:8000/sessions/${sessionId}/${encodeURIComponent(filename)}`,
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
          const filesRes = await axios.get<{ files: string[] }>(
            `http://localhost:8000/sessions/${snapshot.sessionId}/files`,
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
          `http://localhost:8000/sessions/${sessionId}/${encodeURIComponent('workflow.py')}`,
          { content: workflowCode },
        ),
        ...configs.map((cfg) =>
          axios.put(
            `http://localhost:8000/sessions/${sessionId}/${encodeURIComponent(`${agentNameToKebab(cfg.className)}.py`)}`,
            { content: extractAgentClassCode(currentCode, cfg.className) },
          ),
        ),
        ...toDelete.map((className) =>
          axios.delete(
            `http://localhost:8000/sessions/${sessionId}/${encodeURIComponent(`${agentNameToKebab(className)}.py`)}`,
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
    const ensureSession = async () =>
    {
      const storedId = readStoredSessionId();
      if (storedId !== null)
      {
        await loadSession(storedId);
        if (currentSessionIdRef.current === storedId)
        {
          return;
        }
      }

      try
      {
        const createRes = await axios.post<{ sessionId: string }>('http://localhost:8000/sessions/create');
        const newId = createRes.data.sessionId;
        if (typeof newId === 'string' && newId !== '')
        {
          persistCurrentSessionId(newId);
          await loadSession(newId);
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

  const handleNewSession = async () =>
  {
    try
    {
      const createRes = await axios.post<{ sessionId: string }>('http://localhost:8000/sessions/create');
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
        sessionId: currentSessionId,
        maxRounds,
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
            onNew={handleNewSession}
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
              variant="run"
              onClick={isWorkflowActive ? handleStopWorkflow : handleRunAgent}
              icon={!isWorkflowActive ? <Play size={16} /> : undefined}
              showSpinner={isWorkflowActive}
              elapsedTime={isWorkflowActive ? formatElapsedSeconds(workflowElapsedSeconds) : undefined}
            >
              {isWorkflowActive ? 'Stop Workflow' : 'Run Workflow'}
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
          <div className={styles.mainArea} style={{ height: `calc(${100 - logHeightPercent}% - 4px)` }}>
            <section className={styles.panel} style={{ flex: 1 }}>
              <EditorPanel
                code={code}
                onCodeChange={setCode}
                agentOutputs={agentOutputs}
                agentStatuses={agentStatuses}
                agentOrder={agentOrder}
                workflowId={currentSessionId}
                maxRounds={maxRounds}
                onMaxRoundsChange={setMaxRounds}
                workflowResult={workflowResult}
                activeTab={editorActiveTab}
                onTabChange={setEditorActiveTab}
                onCloseAgentTab={(agentName: string) =>
                {
                  const configs = parseAgentConfigsFromCode(code);
                  const config = configs.find((c) => c.name === agentName);
                  if (config && currentSessionId !== null)
                  {
                    void axios.delete(
                      `http://localhost:8000/sessions/${currentSessionId}/${encodeURIComponent(`${agentNameToKebab(config.className)}.py`)}`,
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

          <section className={`${styles.panel} ${styles.bottomPanel}`} style={{ height: `calc(${logHeightPercent}% - 4px)` }}>
            <LogList logs={logs} />
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
