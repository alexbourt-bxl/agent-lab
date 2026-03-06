import { useEffect, useRef } from 'react';
import LogEntry from './LogEntry';
import styles from './LogList.module.css';

type LogEntryRecord =
{
  timestamp: string;
  level: string;
  message: string;
  eventType?: string;
  agentName?: string;
};

type LogVariant = 'thought' | 'tool-call' | 'result' | 'state' | 'default';

type LogListProps =
{
  logs: LogEntryRecord[];
  onClearLogs: () => void;
};

function getLogVariant(logEntry: LogEntryRecord): LogVariant
{
  if (logEntry.eventType === 'tool_call')
  {
    return 'tool-call';
  }

  if (logEntry.eventType === 'tool_result')
  {
    return 'result';
  }

  if (logEntry.eventType === 'workflow_result')
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

function LogList(
{
  logs,
  onClearLogs,
}: LogListProps)
{
  const logPanelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() =>
  {
    if (logPanelRef.current === null)
    {
      return;
    }

    logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight;
  }, [logs]);

  return (
    <>
      <div className={styles.panelHeader}>
        <span>Execution Logs</span>
        <button className={styles.clearLogsButton} type="button" onClick={onClearLogs}>
          Clear Logs
        </button>
      </div>
      <div className={styles.panelBody} ref={logPanelRef}>
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
                  level={logEntry.level}
                  logLabel={logLabel}
                  message={logEntry.message}
                  logVariant={logVariant}
                />
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

export default LogList;
