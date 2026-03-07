import AgentStatusCard from './AgentStatusCard';
import styles from './StatusView.module.css';

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  stepStartTime?: number;
};

type StatusViewProps =
{
  agentStatuses: AgentStatus[];
  workflowResult: string | null;
  timeoutSeconds: number;
  onShowAgentResults?: (agentName: string) => void;
};

function formatStateLabel(state: string): string
{
  return state.replaceAll('_', ' ');
}

function StatusView(
{
  agentStatuses,
  workflowResult,
  timeoutSeconds,
  onShowAgentResults
}: StatusViewProps)
{
  return (
    <div className={styles.panelBody}>
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
              stepStartTime={agentStatus.stepStartTime}
              stateLabel={formatStateLabel(agentStatus.state)}
              timeoutSeconds={timeoutSeconds}
              onShowResults={onShowAgentResults}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default StatusView;
