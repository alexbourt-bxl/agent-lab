import AgentStatusCard from './AgentStatusCard';
import styles from './StatusView.module.css';

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
};

type StatusViewProps =
{
  agentStatuses: AgentStatus[];
  workflowResult: string | null;
};

function formatStateLabel(state: string): string
{
  return state.replaceAll('_', ' ');
}

function StatusView(
{
  agentStatuses,
  workflowResult,
}: StatusViewProps)
{
  return (
    <div className={styles.panelBody}>
      {workflowResult !== null && workflowResult !== '' && (
        <div className={styles.workflowResultCard}>
          <div className={styles.workflowResultLabel}>Workflow Result</div>
          <div className={styles.workflowResultValue}>{workflowResult}</div>
        </div>
      )}
      {agentStatuses.length === 0 && workflowResult === null ? (
        <div className={styles.panelPlaceholder}>
          Agent status will appear here during execution.
        </div>
      ) : (
        <div className={styles.agentStatusList}>
          {agentStatuses.map((agentStatus) => (
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
  );
}

export default StatusView;
