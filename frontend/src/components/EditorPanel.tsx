import { useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import type { Monaco } from '@monaco-editor/react';
import { Plus, X } from 'lucide-react';
import { formatElapsedSeconds } from '../utils/formatElapsed';
import {
  readCodePaneWidth,
  writeCodePaneWidth,
} from '../persistence';
import {
  extractAgentClassCode,
  extractWorkflowCode,
  getTabLabel,
  mergeAgentClassCodeIntoFullCode,
  mergeWorkflowCodeIntoFullCode,
  parseAgentConfigsFromCode,
} from '../workflowCode';
import styles from './EditorPanel.module.css';

const AVAILABLE_TOOLS = ['ReadFile', 'WriteFile', 'WebSearch'];

let toolsProviderRegistered = false;

function registerToolsCompletionProvider(monaco: Monaco): void
{
  if (toolsProviderRegistered)
  {
    return;
  }
  toolsProviderRegistered = true;
  monaco.languages.registerCompletionItemProvider('python',
  {
    triggerCharacters: [',', ' ', '[', 'R', 'W', 'S'],
    provideCompletionItems(
      model: { getValueInRange: (r: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }) => string; getWordUntilPosition: (p: { lineNumber: number; column: number }) => { startColumn: number; endColumn: number } },
      position: { lineNumber: number; column: number },
    )
    {
      const textBefore = model.getValueInRange({ startLineNumber: 1, startColumn: 1, endLineNumber: position.lineNumber, endColumn: position.column });
      const lastToolsStart = textBefore.lastIndexOf('tools = [');
      if (lastToolsStart === -1)
      {
        return { suggestions: [] };
      }
      const afterToolsStart = textBefore.slice(lastToolsStart);
      let depth = 0;
      for (let i = 0; i < afterToolsStart.length; i++)
      {
        if (afterToolsStart[i] === '[')
        {
          depth++;
        }
        else if (afterToolsStart[i] === ']')
        {
          depth--;
        }
      }
      const inToolsArray = depth > 0;
      if (!inToolsArray)
      {
        return { suggestions: [] };
      }
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };
      return {
        suggestions: AVAILABLE_TOOLS.map((label) =>
        ({
          label,
          kind: monaco.languages.CompletionItemKind.Class,
          insertText: label,
          range,
        })),
      };
    },
  });
}

function handleEditorMount(_editor: unknown, monaco: Monaco): void
{
  registerToolsCompletionProvider(monaco);
}

type AgentStatus =
{
  name: string;
  state: string;
  message: string;
  round?: number;
  stepStartTime?: number;
};

type EditorPanelProps =
{
  theme?: 'dark' | 'light';
  code: string;
  onCodeChange: (value: string) => void;
  agentOutputs: Record<string, string>;
  agentOutputsByRound: Record<string, Record<number, string>>;
  agentRounds: Record<string, number[]>;
  agentStatuses: Record<string, AgentStatus>;
  agentOrder: string[];
  workflowId: string | null;
  maxRounds: number;
  currentAgent: string | null;
  currentRound: number;
  workflowStatus: string;
  workflowResult: string | null;
  workflowRunning?: boolean;
  workflowElapsedTime?: string;
  activeTab: string;
  onTabChange: (tab: string) => void;
  onCloseAgentTab: (agentName: string) => void;
  onAddAgent: () => void;
};

const monacoTheme = (theme: 'dark' | 'light') => (theme === 'light' ? 'vs' : 'vs-dark');

function EditorPanel(
{
  theme = 'dark',
  code,
  onCodeChange,
  agentOutputs,
  agentOutputsByRound = {},
  agentRounds = {},
  agentStatuses,
  agentOrder = [],
  workflowId,
  maxRounds,
  currentAgent = null,
  currentRound = 0,
  workflowStatus = 'idle',
  workflowResult,
  workflowRunning = false,
  workflowElapsedTime,
  activeTab,
  onTabChange,
  onCloseAgentTab,
  onAddAgent,
}: EditorPanelProps)
{
  const splitRef = useRef<HTMLDivElement | null>(null);
  const [codePaneWidthPercent, setCodePaneWidthPercent] = useState(readCodePaneWidth);
  const [selectedRoundByAgent, setSelectedRoundByAgent] = useState<Record<string, number>>({});

  const hasAnyAgentActive = Object.values(agentStatuses).some(
    (s) =>
      s.state === 'working' ||
      s.state === 'executing' ||
      s.state === 'thinking',
  );

  const parsedConfigs = parseAgentConfigsFromCode(code);
  const agentConfigs =
    agentOrder.length > 0
      ? [
          ...agentOrder
            .map((name) => parsedConfigs.find((c) => c.name === name))
            .filter((c): c is NonNullable<typeof c> => c !== undefined),
          ...parsedConfigs.filter((c) => !agentOrder.includes(c.name)),
        ]
      : parsedConfigs;

  const handleVerticalResizeStart = (e: React.PointerEvent<HTMLDivElement>) =>
  {
    const split = splitRef.current;
    if (!split)
    {
      return;
    }
    e.preventDefault();
    const rect = split.getBoundingClientRect();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const handlePointerMove = (moveEvent: PointerEvent) =>
    {
      const pct = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      const clamped = Math.min(70, Math.max(30, pct));
      setCodePaneWidthPercent(clamped);
      writeCodePaneWidth(clamped);
    };

    const handlePointerUp = () =>
    {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  };

  return (
    <div className={styles.panelBody}>
      <div className={styles.tabList}>
        <button
          type="button"
          className={`${activeTab === 'workflow' ? styles.tabActive : styles.tab} ${workflowStatus === 'done' ? styles.tabWorkflowDone : ''} ${workflowStatus === 'error' ? styles.tabWorkflowError : ''}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={(e) =>
          {
            onTabChange('workflow');
            (e.currentTarget as HTMLElement).blur();
          }}
        >
          <span className={styles.tabContent}>
            {workflowRunning && !hasAnyAgentActive && <span className={styles.tabSpinner} aria-hidden />}
            Workflow
          </span>
        </button>
        {agentConfigs.map((config) =>
        {
          const label = getTabLabel(config);
          const status = agentStatuses[config.name];
          const isWorking = status?.state === 'thinking' || status?.state === 'working' || status?.state === 'executing';
          return (
            <div
              key={config.name}
              role="tab"
              tabIndex={0}
              className={`${styles.tab} ${activeTab === `agent:${config.name}` ? styles.tabActive : ''} ${isWorking ? styles.tabActiveAgent : ''}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={(e) =>
              {
                onTabChange(`agent:${config.name}`);
                (e.currentTarget as HTMLElement).blur();
              }}
              onKeyDown={(e) =>
              {
                if (e.key === 'Enter' || e.key === ' ')
                {
                  e.preventDefault();
                  onTabChange(`agent:${config.name}`);
                }
              }}
            >
              <span className={styles.tabContent}>
                {isWorking && <span className={styles.tabSpinner} aria-hidden />}
                {label}
              </span>
              <button
                type="button"
                className={styles.tabClose}
                onMouseDown={(e) => e.preventDefault()}
                onClick={(e) =>
                {
                  e.stopPropagation();
                  onCloseAgentTab(config.name);
                  (e.currentTarget as HTMLElement).blur();
                }}
                aria-label={`Close ${label}`}
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
        <button
          type="button"
          className={styles.tabAdd}
          onMouseDown={(e) => e.preventDefault()}
          onClick={(e) =>
          {
            onAddAgent();
            (e.currentTarget as HTMLElement).blur();
          }}
          aria-label="Add new agent"
        >
          <Plus size={16} />
        </button>
      </div>
      <div className={styles.tabContentArea}>
        {activeTab === 'workflow' && (
          <>
            <div
              className={`${styles.workflowHeader} ${workflowStatus === 'done' ? styles.workflowHeaderDone : ''} ${workflowStatus === 'error' ? styles.workflowHeaderError : ''}`}
            >
              <span className={styles.workflowId}>
                ID: {workflowId ?? '—'}
              </span>
              {workflowRunning && workflowElapsedTime != null && (
                <span className={styles.workflowElapsed}>{workflowElapsedTime}</span>
              )}
              <div className={styles.workflowProgress}>
                <span className={styles.workflowProgressLabel}>
                  {currentAgent != null
                    ? `${currentAgent} R${currentRound} of ${maxRounds}`
                    : `Round ${currentRound} of ${maxRounds}`}
                </span>
                {currentAgent != null && (
                  <span className={styles.workflowProgressAgent}>
                    Active: {currentAgent}
                  </span>
                )}
                <span className={styles.workflowStatusBadge} data-status={workflowStatus}>
                  {workflowStatus}
                </span>
              </div>
            </div>
            <div className={styles.twoPaneSplit} ref={splitRef}>
              <div className={styles.codePane} style={{ width: `calc(${codePaneWidthPercent}% - var(--space-resize-gap))` }}>
                <div className={styles.editorShell}>
                  <Editor
                    defaultLanguage="python"
                    language="python"
                    theme={monacoTheme(theme)}
                    value={extractWorkflowCode(code)}
                    onChange={(value) => onCodeChange(mergeWorkflowCodeIntoFullCode(code, value ?? ''))}
                    onMount={handleEditorMount}
                    options={
                    {
                      minimap: { enabled: false },
                      fontSize: 14,
                      padding: { top: 16 },
                      scrollBeyondLastLine: false,
                    }}
                  />
                </div>
              </div>
              <div
                className={styles.verticalResizeHandle}
                onPointerDown={handleVerticalResizeStart}
                role="separator"
                aria-label="Resize code and result panes"
                aria-orientation="vertical"
              />
              <div className={styles.resultPane} style={{ width: `calc(${100 - codePaneWidthPercent}% - var(--space-resize-gap))` }}>
                <div className={styles.outputContent}>
                  <pre className={styles.outputPre}>{workflowResult ?? 'No workflow result yet.'}</pre>
                </div>
              </div>
            </div>
          </>
        )}
        {activeTab.startsWith('agent:') && (
          <>
            {(() =>
            {
              const agentName = activeTab.replace('agent:', '');
              const status = agentStatuses[agentName];
              const rounds = agentRounds[agentName] ?? [];
              const outputsForAgent = agentOutputsByRound[agentName] ?? {};
              const latestRound = rounds.length > 0 ? rounds[rounds.length - 1] : null;
              const displayRound = selectedRoundByAgent[agentName] ?? latestRound;
              const displayOutput =
                displayRound != null && outputsForAgent[displayRound] !== undefined
                  ? outputsForAgent[displayRound]
                  : agentOutputs[agentName] ?? 'No output';
              const isWorking = status?.state === 'thinking' || status?.state === 'working' || status?.state === 'executing';
              const stepElapsedSeconds =
                isWorking && status?.stepStartTime !== undefined
                  ? Math.floor((Date.now() - status.stepStartTime) / 1000)
                  : undefined;
              return (
                <>
                  <div className={`${styles.agentHeader} ${isWorking ? styles.agentHeaderWorking : ''}`}>
                    <div className={styles.agentHeaderLeft}>
                      <span className={styles.agentStatus}>
                        {status?.state?.replaceAll('_', ' ') ?? '—'} {status?.message ? `· ${status.message}` : ''}
                      </span>
                    </div>
                    <div className={styles.agentHeaderCenter}>
                      {stepElapsedSeconds !== undefined && (
                        <span className={styles.agentElapsed}>
                          {formatElapsedSeconds(stepElapsedSeconds)}
                        </span>
                      )}
                    </div>
                    <div className={styles.agentHeaderRight}>
                    {rounds.length > 1 && (
                      <div className={styles.roundSelector}>
                        {rounds.map((r) => (
                          <button
                            key={r}
                            type="button"
                            className={displayRound === r ? styles.roundBtnActive : styles.roundBtn}
                            onClick={() => setSelectedRoundByAgent((prev) => ({ ...prev, [agentName]: r }))}
                          >
                            R{r}
                          </button>
                        ))}
                      </div>
                    )}
                    </div>
                  </div>
            <div className={styles.twoPaneSplit} ref={splitRef}>
              <div className={styles.codePane} style={{ width: `calc(${codePaneWidthPercent}% - var(--space-resize-gap))` }}>
                <div className={styles.editorShell}>
                  <Editor
                    defaultLanguage="python"
                    language="python"
                    theme={monacoTheme(theme)}
                    onMount={handleEditorMount}
                    value={
                      (() =>
                      {
                        const agentName = activeTab.replace('agent:', '');
                        const cfg = agentConfigs.find((c) => c.name === agentName);
                        return cfg ? extractAgentClassCode(code, cfg.className) : '';
                      })()
                    }
                    onChange={(value) =>
                    {
                      const agentName = activeTab.replace('agent:', '');
                      const cfg = agentConfigs.find((c) => c.name === agentName);
                      if (cfg)
                      {
                        onCodeChange(mergeAgentClassCodeIntoFullCode(code, cfg.className, value ?? ''));
                      }
                    }}
                    options={
                    {
                      minimap: { enabled: false },
                      fontSize: 14,
                      padding: { top: 16 },
                      scrollBeyondLastLine: false,
                    }}
                  />
                </div>
              </div>
              <div
                className={styles.verticalResizeHandle}
                onPointerDown={handleVerticalResizeStart}
                role="separator"
                aria-label="Resize code and result panes"
                aria-orientation="vertical"
              />
              <div className={styles.resultPane} style={{ width: `calc(${100 - codePaneWidthPercent}% - var(--space-resize-gap))` }}>
                <div className={styles.outputContent}>
                  <pre className={styles.outputPre}>
                    {displayOutput}
                  </pre>
                </div>
              </div>
            </div>
                </>
              );
            })()}
          </>
        )}
      </div>
    </div>
  );
}

export default EditorPanel;
