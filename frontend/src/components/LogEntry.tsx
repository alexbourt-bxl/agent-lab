import styles from './LogEntry.module.css';

type LogVariant = 'thought' | 'tool-call' | 'result' | 'state' | 'default';

type LogEntryProps =
{
  timestamp: string;
  logLabel: string;
  message: string;
  logVariant: LogVariant;
};

function LogEntry(
{
  timestamp,
  logLabel,
  message,
  logVariant,
}: LogEntryProps)
{
  const variantClassName =
  {
    thought: styles.logEntryThought,
    'tool-call': styles.logEntryToolCall,
    result: styles.logEntryResult,
    state: styles.logEntryState,
    default: '',
  }[logVariant];

  const logLevelClassName =
  {
    thought: styles.logLevelThought,
    'tool-call': styles.logLevelToolCall,
    result: styles.logLevelResult,
    state: styles.logLevelState,
    default: '',
  }[logVariant];

  const logEntryClassName =
    variantClassName === ''
      ? styles.logEntry
      : `${styles.logEntry} ${variantClassName}`;

  const logLabelClassName =
    logLevelClassName === ''
      ? styles.logLevel
      : `${styles.logLevel} ${logLevelClassName}`;

  return (
    <div className={logEntryClassName}>
      <span className={styles.logTimestamp}>{timestamp}</span>
      <span className={logLabelClassName}>{logLabel}</span>
      <span className={styles.logMessage}>{message}</span>
    </div>
  );
}

export default LogEntry;
