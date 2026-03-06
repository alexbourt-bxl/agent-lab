import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import AgentStatusCard from './components/AgentStatusCard';
import LogEntry from './components/LogEntry';
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
};

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
};

type LogVariant = 'thought' | 'tool-call' | 'result' | 'state' | 'default';

function getLogVariant(logEntry: LogEntry): LogVariant
{
  if (logEntry.eventType === 'tool_call')
  {
    return 'tool-call';
  }

  if (logEntry.eventType === 'tool_result')
  {
    return 'result';
  }

  if (logEntry.eventType === 'thought')
  {
    return 'thought';
  }

  if (logEntry.eventType === 'state' || logEntry.eventType === 'handoff')
  {
    return 'state';
  }

  return 'default';
}

function formatStateLabel(state: string): string
{
  return state.replaceAll('_', ' ');
}

function App()
{
  const [code, setCode] = useState(`researcher = Agent(
  name="Researcher", 
  goal="Find and refine a promising SaaS idea based on analyst feedback"
)

analyst = Agent(
  name="Analyst", 
  goal="Find faults in the researcher's latest SaaS idea and only mark done when the idea is strong enough"
)

workflow = Workflow(
  agents=
  [
    "researcher",
    "analyst",
  ],
  entry_agent="researcher",
  max_rounds=8
)

workflow.run()`);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const logPanelRef = useRef<HTMLDivElement | null>(null);

  const handleRunAgent = async () =>
  {
    setLogs([]);
    setAgentStatuses({});

    try
    {
      await axios.post('http://localhost:8000/run',
      {
        code,
      });
    }
    catch
    {
      setLogs((currentLogs) => [
        ...currentLogs,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'Failed to submit the agent script to the backend.',
        },
      ]);
    }
  };

  useEffect(() =>
  {
    const socket = new WebSocket('ws://localhost:8000/ws/logs');

    socket.onmessage = (event) =>
    {
      try
      {
        const logEntry = JSON.parse(event.data) as LogEntry;
        setLogs((currentLogs) => [...currentLogs, logEntry]);

        if (logEntry.agentName !== undefined && logEntry.state !== undefined)
        {
          setAgentStatuses((currentStatuses) => (
            {
              ...currentStatuses,
              [logEntry.agentName as string]:
              {
                name: logEntry.agentName as string,
                state: logEntry.state as string,
                message: logEntry.message,
                round: logEntry.round,
              },
            }
          ));
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
      setLogs((currentLogs) => [
        ...currentLogs,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'WebSocket connection error.',
        },
      ]);
    };

    return () =>
    {
      socket.close();
    };
  }, []);

  useEffect(() =>
  {
    if (logPanelRef.current === null)
    {
      return;
    }

    logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
  }, [logs]);

  return (
    <div className={styles.appShell}>
      <header className={styles.topBar}>
        <h1 className={styles.appTitle}>Agent Lab</h1>
        <button className={styles.runButton} type="button" onClick={handleRunAgent}>
          Run Workflow
        </button>
      </header>

      <main className={styles.mainContent}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>Editor</div>
          <div className={`${styles.panelBody} ${styles.editorPanelBody}`}>
            <div className={styles.editorShell}>
              <Editor
                defaultLanguage="python"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(value) => setCode(value ?? '')}
                options={
                {
                  minimap:
                  {
                    enabled: false,
                  },
                  fontSize: 14,
                  padding:
                  {
                    top: 16,
                  },
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>Visualization/Status</div>
          <div className={styles.panelBody}>
            {Object.keys(agentStatuses).length === 0 ? (
              <div className={styles.panelPlaceholder}>
                Agent status will appear here during execution.
              </div>
            ) : (
              <div className={styles.agentStatusList}>
                {Object.values(agentStatuses).map((agentStatus) => (
                  <AgentStatusCard
                    key={agentStatus.name}
                    name={agentStatus.name}
                    state={agentStatus.state}
                    message={agentStatus.message}
                    round={agentStatus.round}
                    stateLabel={formatStateLabel(agentStatus.state)}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      </main>

      <section className={`${styles.panel} ${styles.bottomPanel}`}>
        <div className={`${styles.panelHeader} ${styles.panelHeaderRow}`}>
          <span>Execution Logs</span>
          <button className={styles.clearLogsButton} type="button" onClick={() => setLogs([])}>
            Clear Logs
          </button>
        </div>
        <div className={`${styles.panelBody} ${styles.logsPanelBody}`} ref={logPanelRef}>
          {logs.length === 0 ? (
            <div className={styles.panelPlaceholder}>
              Waiting for execution logs...
            </div>
          ) : (
            <div className={styles.logList}>
              {logs.map((logEntry, index) =>
              {
                const logVariant = getLogVariant(logEntry);
                const logLabel = logEntry.agentName ?? logEntry.eventType ?? logEntry.level.toUpperCase();

                return (
                <LogEntry
                  key={`${logEntry.timestamp}-${index}`}
                  timestamp={logEntry.timestamp}
                  logLabel={logLabel}
                  message={logEntry.message}
                  logVariant={logVariant}
                />
                );
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
