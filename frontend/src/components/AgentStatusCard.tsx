import Badge, { type BadgeTone } from './Badge';
import Button from './Button';
import { formatElapsedSeconds } from '../utils/formatElapsed';
import styles from './AgentStatusCard.module.css';

type AgentStatusCardProps =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  stepStartTime?: number;
  stateLabel: string;
  timeoutSeconds: number;
  onShowResults?: (agentName: string) => void;
};

function AgentStatusCard(
{
  name,
  state,
  message,
  round,
  stepStartTime,
  stateLabel,
  timeoutSeconds,
  onShowResults,
}: AgentStatusCardProps)
{
  const showsSpinner = state === 'thinking' || state === 'working';
  const stepElapsedSeconds =
    showsSpinner && stepStartTime !== undefined
      ? Math.floor((Date.now() - stepStartTime) / 1000)
      : undefined;
  const progress =
    showsSpinner && stepElapsedSeconds !== undefined && timeoutSeconds > 0
      ? Math.min(1, stepElapsedSeconds / timeoutSeconds)
      : undefined;
  const showsError = message.includes('Error:');
  const badgeToneByState: Record<string, BadgeTone> =
  {
    thinking: 'thinking',
    working: 'working',
    waiting_for_turn: 'waiting',
    waiting_for_peer: 'waiting',
    done: 'done',
  };
  const badgeTone = showsError ? 'error' : (badgeToneByState[state] ?? 'default');

  return (
    <div className={showsError ? `${styles.agentStatusCard} ${styles.agentStatusCardError}` : styles.agentStatusCard}>
      <div className={styles.agentStatusRow}>
        <span className={styles.agentStatusName}>{name}</span>
        <Badge
          label={stateLabel}
          tone={badgeTone}
          showSpinner={showsSpinner}
          elapsedTime={stepElapsedSeconds !== undefined ? formatElapsedSeconds(stepElapsedSeconds) : undefined}
          progress={progress}
        />
      </div>
      <div className={showsError ? `${styles.agentStatusMessage} ${styles.agentStatusMessageError}` : styles.agentStatusMessage}>{message}</div>
      <div className={styles.agentStatusFooter}>
        {round !== undefined && (
          <div className={styles.agentStatusRound}>Round {round}</div>
        )}
        {onShowResults !== undefined && (
          <Button variant="clearLogs" onClick={() => onShowResults(name)}>
            Show results
          </Button>
        )}
      </div>
    </div>
  );
}

export default AgentStatusCard;
