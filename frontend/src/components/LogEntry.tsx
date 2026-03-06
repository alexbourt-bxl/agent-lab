import styles from './LogEntry.module.css';

type LogVariant = 'thought' | 'tool-call' | 'result' | 'state' | 'default';

const timestampFormatter = new Intl.DateTimeFormat('en-GB',
{
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

type LogEntryProps =
{
  timestamp: string;
  level: string;
  logLabel: string;
  message: string;
  logVariant: LogVariant;
};

function formatTimestamp(timestamp: string): string
{
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime()))
  {
    return timestamp;
  }

  const parts = timestampFormatter.formatToParts(date);
  const day = parts.find((part) => part.type === 'day')?.value;
  const month = parts.find((part) => part.type === 'month')?.value;
  const hours = parts.find((part) => part.type === 'hour')?.value;
  const minutes = parts.find((part) => part.type === 'minute')?.value;
  const seconds = parts.find((part) => part.type === 'second')?.value;

  if (day === undefined || month === undefined || hours === undefined || minutes === undefined || seconds === undefined)
  {
    return timestamp;
  }

  return `${day}-${month} ${hours}:${minutes}:${seconds}`;
}

function LogEntry(
{
  timestamp,
  level,
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

  const showsErrorStyle = level === 'error' || message.includes('Error:');

  const logMessageClassName =
    showsErrorStyle
      ? `${styles.logMessage} ${styles.logMessageError}`
      : styles.logMessage;

  return (
    <div className={logEntryClassName}>
      <span className={styles.logTimestamp}>{formatTimestamp(timestamp)}</span>
      <span className={logLabelClassName}>{logLabel}</span>
      <span className={logMessageClassName}>{message}</span>
    </div>
  );
}

export default LogEntry;
