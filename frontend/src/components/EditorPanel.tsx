import { useRef, useState } from 'react';
import Editor from '@monaco-editor/react';
import type { Monaco } from '@monaco-editor/react';
import { Plus, X } from 'lucide-react';
import { formatElapsedSeconds } from '../utils/formatElapsed';
import styles from './EditorPanel.module.css';

const AVAILABLE_TOOLS = ['ReadFile', 'WriteFile', 'SearchWeb'];

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

const CODE_PANE_WIDTH_COOKIE = 'agent_lab_code_pane_width';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function readCodePaneWidth(): number
{
  if (typeof document === 'undefined')
  {
    return 50;
  }
  const entry = document.cookie.split('; ').find((e) => e.startsWith(`${CODE_PANE_WIDTH_COOKIE}=`));
  if (!entry)
  {
    return 50;
  }
  const val = Number(entry.split('=').slice(1).join('='));
  return Number.isNaN(val) ? 50 : Math.min(70, Math.max(30, val));
}

function writeCodePaneWidth(value: number): void
{
  document.cookie = `${CODE_PANE_WIDTH_COOKIE}=${value}; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`;
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
  onMaxRoundsChange: (value: number) => void;
  workflowResult: string | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
  onCloseAgentTab: (agentName: string) => void;
  onAddAgent: () => void;
};

function parseAgentConfigsFromCode(code: string): Array<{ name: string; className: string; variable: string }>
{
  const configs: Array<{ name: string; className: string; variable: string }> = [];
  const classMatches = [...code.matchAll(/class (\w+)\(Agent\):\s*/g)];
  const classesByName = new Map<string, { name: string }>();

  for (let i = 0; i < classMatches.length; i++)
  {
    const className = classMatches[i][1];
    const bodyStart = classMatches[i].index! + classMatches[i][0].length;
    const bodyEnd = i + 1 < classMatches.length
      ? classMatches[i + 1].index!
      : code.length;
    const nextClass = code.slice(bodyStart).match(/\nclass \w+\(Agent\)/);
    const end = nextClass
      ? bodyStart + nextClass.index!
      : bodyEnd;
    const body = code.slice(bodyStart, end);
    const nameMatch = body.match(/name\s*=\s*["']([^"']*)["']/);
    classesByName.set(className, {
      name: nameMatch ? nameMatch[1].trim() : className,
    });
  }

  for (const [className, attrs] of classesByName)
  {
    let variable = '';
    const pattern = new RegExp(
      `(\\w+)\\s*=\\s*${className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\(`,
      'g',
    );
    let m;
    while ((m = pattern.exec(code)) !== null)
    {
      const argsStart = m.index + m[0].length;
      let depth = 1;
      let argsEnd = argsStart;
      for (let i = argsStart; i < code.length; i++)
      {
        if (code[i] === '(')
        {
          depth++;
        }
        else if (code[i] === ')')
        {
          depth--;
          if (depth === 0)
          {
            argsEnd = i;
            break;
          }
        }
      }
      const argumentsStr = code.slice(argsStart, argsEnd);
      const goalMatch = argumentsStr.match(/goal\s*=\s*["']([^"']*)["']/);
      if (goalMatch)
      {
        variable = m[1];
        break;
      }
    }
    configs.push({
      name: attrs.name || className || 'Agent?',
      className: className || 'Agent?',
      variable: variable || className.charAt(0).toLowerCase() + className.slice(1),
    });
  }

  configs.sort((a, b) =>
  {
    const instA = code.indexOf(`${a.variable} = ${a.className}`);
    const instB = code.indexOf(`${b.variable} = ${b.className}`);
    const idxA = instA >= 0 ? instA : code.indexOf(`class ${a.className}(Agent)`);
    const idxB = instB >= 0 ? instB : code.indexOf(`class ${b.className}(Agent)`);
    return idxA - idxB;
  });
  return configs;
}

function getTabLabel(config: { name: string; className: string }): string
{
  const trimmed = config.name.trim();
  return trimmed || config.className || 'Agent?';
}

export function extractWorkflowCode(code: string): string
{
  const firstInst = code.match(/\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(/);
  if (firstInst && firstInst.index !== undefined)
  {
    return code.slice(firstInst.index).trimStart();
  }
  return '';
}

export function extractAgentClassCode(code: string, className: string): string
{
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = code.match(
    new RegExp(
      `(class ${escaped}\\(Agent\\):[\\s\\S]*?)(?=\\nclass \\w+\\(Agent\\)|\\n[A-Za-z_]\\w*\\s*=|$)`,
    ),
  );
  return match ? match[1].trimEnd() : '';
}

function mergeWorkflowCodeIntoFullCode(fullCode: string, workflowCode: string): string
{
  const firstInst = fullCode.match(/\n([A-Za-z_]\w*)\s*=\s*\w+\s*\(/);
  if (!firstInst || firstInst.index === undefined)
  {
    return fullCode.trimEnd() + (fullCode.endsWith('\n') ? '' : '\n') + workflowCode + '\n';
  }
  const workflowStart = firstInst.index;
  const before = fullCode.slice(0, workflowStart);
  const trailing = fullCode.slice(workflowStart).match(/^\s*/)?.[0] ?? '';
  return before + trailing + workflowCode;
}

function mergeAgentClassCodeIntoFullCode(
  fullCode: string,
  className: string,
  agentCode: string,
): string
{
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(
    `(class ${escaped}\\(Agent\\):[\\s\\S]*?)(?=\\nclass \\w+\\(Agent\\)|\\n[A-Za-z_]\\w*\\s*=|$)`,
  );
  const match = fullCode.match(pattern);
  if (!match)
  {
    return fullCode;
  }
  return fullCode.replace(pattern, agentCode);
}

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
  onMaxRoundsChange,
  workflowResult,
  activeTab,
  onTabChange,
  onCloseAgentTab,
  onAddAgent,
}: EditorPanelProps)
{
  const splitRef = useRef<HTMLDivElement | null>(null);
  const [codePaneWidthPercent, setCodePaneWidthPercent] = useState(readCodePaneWidth);
  const [selectedRoundByAgent, setSelectedRoundByAgent] = useState<Record<string, number>>({});

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
          className={activeTab === 'workflow' ? styles.tabActive : styles.tab}
          onMouseDown={(e) => e.preventDefault()}
          onClick={(e) =>
          {
            onTabChange('workflow');
            (e.currentTarget as HTMLElement).blur();
          }}
        >
          Workflow
        </button>
        {agentConfigs.map((config) =>
        {
          const label = getTabLabel(config);
          const status = agentStatuses[config.name];
          const isWorking = status?.state === 'thinking' || status?.state === 'working';
          return (
            <div
              key={config.name}
              role="tab"
              tabIndex={0}
              className={activeTab === `agent:${config.name}` ? styles.tabActive : styles.tab}
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
            <div className={styles.workflowHeader}>
              <span className={styles.workflowId}>
                ID: {workflowId ?? '—'}
              </span>
              <label className={styles.maxRoundsLabel}>
                Max rounds:
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxRounds}
                  onChange={(e) => onMaxRoundsChange(Number(e.target.value) || 8)}
                  className={styles.maxRoundsInput}
                />
              </label>
            </div>
            <div className={styles.twoPaneSplit} ref={splitRef}>
              <div className={styles.codePane} style={{ width: `calc(${codePaneWidthPercent}% - 4px)` }}>
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
              <div className={styles.resultPane} style={{ width: `calc(${100 - codePaneWidthPercent}% - 4px)` }}>
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
              const isWorking = status?.state === 'thinking' || status?.state === 'working';
              const stepElapsedSeconds =
                isWorking && status?.stepStartTime !== undefined
                  ? Math.floor((Date.now() - status.stepStartTime) / 1000)
                  : undefined;
              return (
                <>
                  <div className={styles.agentHeader}>
                    {stepElapsedSeconds !== undefined && (
                      <span className={styles.agentElapsed}>
                        {formatElapsedSeconds(stepElapsedSeconds)}
                      </span>
                    )}
                    <span className={styles.agentStatus}>
                      {status?.state?.replaceAll('_', ' ') ?? '—'} {status?.message ? `· ${status.message}` : ''}
                    </span>
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
            <div className={styles.twoPaneSplit} ref={splitRef}>
              <div className={styles.codePane} style={{ width: `calc(${codePaneWidthPercent}% - 4px)` }}>
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
              <div className={styles.resultPane} style={{ width: `calc(${100 - codePaneWidthPercent}% - 4px)` }}>
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
