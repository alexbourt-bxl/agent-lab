import Badge, { type BadgeTone } from './Badge';
import styles from './AgentStatusCard.module.css';

type AgentStatusCardProps =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  stateLabel: string;
};

function AgentStatusCard(
{
  name,
  state,
  message,
  round,
  stateLabel,
}: AgentStatusCardProps)
{
  const showsSpinner = state === 'thinking' || state === 'working';
  const badgeToneByState: Record<string, BadgeTone> =
  {
    thinking: 'thinking',
    working: 'working',
    waiting_for_turn: 'waiting',
    waiting_for_peer: 'waiting',
    done: 'done',
  };
  const badgeTone = badgeToneByState[state] ?? 'default';

  return (
    <div className={styles.agentStatusCard}>
      <div className={styles.agentStatusRow}>
        <span className={styles.agentStatusName}>{name}</span>
        <Badge label={stateLabel} tone={badgeTone} showSpinner={showsSpinner} />
      </div>
      <div className={styles.agentStatusMessage}>{message}</div>
      {round !== undefined && (
        <div className={styles.agentStatusRound}>Round {round}</div>
      )}
    </div>
  );
}

export default AgentStatusCard;
