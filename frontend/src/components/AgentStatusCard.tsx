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
  const stateClassName =
  {
    thinking: styles.agentStatusThinking,
    working: styles.agentStatusWorking,
    waiting_for_turn: styles.agentStatusWaitingForTurn,
    waiting_for_peer: styles.agentStatusWaitingForPeer,
    done: styles.agentStatusDone,
  }[state] ?? '';

  const badgeClassName =
    stateClassName === ''
      ? styles.agentStatusBadge
      : `${styles.agentStatusBadge} ${stateClassName}`;

  return (
    <div className={styles.agentStatusCard}>
      <div className={styles.agentStatusRow}>
        <span className={styles.agentStatusName}>{name}</span>
        <span className={badgeClassName}>{stateLabel}</span>
      </div>
      <div className={styles.agentStatusMessage}>{message}</div>
      {round !== undefined && (
        <div className={styles.agentStatusRound}>Round {round}</div>
      )}
    </div>
  );
}

export default AgentStatusCard;
