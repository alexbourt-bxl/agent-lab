import { useEffect, useState } from 'react';
import axios from 'axios';
import CodeEditor from './components/CodeEditor';
import LogList from './components/LogList';
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
};

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
};

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
  start_agent="researcher",
  max_rounds=8
)

workflow.run()`);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});

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
          <CodeEditor code={code} onCodeChange={setCode} />
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>Visualization/Status</div>
          <StatusView agentStatuses={Object.values(agentStatuses)} />
        </section>
      </main>

      <section className={`${styles.panel} ${styles.bottomPanel}`}>
        <LogList logs={logs} onClearLogs={() => setLogs([])} />
      </section>
    </div>
  );
}

export default App;
