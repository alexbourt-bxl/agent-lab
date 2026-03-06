import Editor from '@monaco-editor/react';
import styles from './EditorPanel.module.css';

type EditorPanelProps =
{
  code: string;
  onCodeChange: (value: string) => void;
  agentOutputs: Record<string, string>;
  agentNames: string[];
  workflowResult: string | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
};

function EditorPanel(
{
  code,
  onCodeChange,
  agentOutputs,
  agentNames,
  workflowResult,
  activeTab,
  onTabChange,
}: EditorPanelProps)
{
  const hasWorkflowResult = workflowResult !== null && workflowResult !== '';

  return (
    <div className={styles.panelBody}>
      <div className={styles.tabList}>
        <button
          type="button"
          className={activeTab === 'code' ? styles.tabActive : styles.tab}
          onClick={() => onTabChange('code')}
        >
          Code
        </button>
        {agentNames.map((name) => (
          <button
            key={name}
            type="button"
            className={activeTab === `agent:${name}` ? styles.tabActive : styles.tab}
            onClick={() => onTabChange(`agent:${name}`)}
          >
            {name}
          </button>
        ))}
        {hasWorkflowResult && (
          <button
            type="button"
            className={activeTab === 'workflow-result' ? styles.tabActive : styles.tab}
            onClick={() => onTabChange('workflow-result')}
          >
            Workflow Result
          </button>
        )}
      </div>
      <div className={styles.tabContent}>
        {activeTab === 'code' && (
          <div className={styles.editorShell}>
            <Editor
              defaultLanguage="python"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(value) => onCodeChange(value ?? '')}
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
        )}
        {activeTab.startsWith('agent:') && (
          <div className={styles.outputContent}>
            <pre className={styles.outputPre}>
              {agentOutputs[activeTab.replace('agent:', '')] ?? 'No output yet.'}
            </pre>
          </div>
        )}
        {activeTab === 'workflow-result' && (
          <div className={styles.outputContent}>
            <pre className={styles.outputPre}>{workflowResult ?? ''}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default EditorPanel;
