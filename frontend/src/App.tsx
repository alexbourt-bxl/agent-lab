import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import Editor from '@monaco-editor/react'
import './App.css'

type LogEntry =
{
  timestamp: string
  level: string
  message: string
  eventType?: string
  agentName?: string
  state?: string
  round?: number
}

type AgentStatus =
{
  name: string
  state: string
  message: string
  round?: number
}

type SavedScript =
{
  id: string
  name: string
  code: string
}

type SavedAgent =
{
  id: string
  variable: string
  name: string
  goal: string
  sourceScriptId?: string | null
}

type LogVariant = 'thought' | 'tool-call' | 'result' | 'state' | 'default'

function getLogVariant(logEntry: LogEntry): LogVariant
{
  if (logEntry.eventType === 'tool_call')
  {
    return 'tool-call'
  }

  if (logEntry.eventType === 'tool_result')
  {
    return 'result'
  }

  if (logEntry.eventType === 'thought')
  {
    return 'thought'
  }

  if (logEntry.eventType === 'state' || logEntry.eventType === 'handoff')
  {
    return 'state'
  }

  return 'default'
}

function formatStateLabel(state: string): string
{
  return state.replaceAll('_', ' ')
}

function buildAgentSnippet(savedAgent: SavedAgent): string
{
  return `${savedAgent.variable} = Agent(name="${savedAgent.name}", goal="${savedAgent.goal}")`
}

function upsertAgentSnippet(currentCode: string, savedAgent: SavedAgent): string
{
  const snippet = buildAgentSnippet(savedAgent)
  const escapedVariable = savedAgent.variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const existingAgentPattern = new RegExp(`${escapedVariable}\\s*=\\s*Agent\\([^\\n]*\\)`)

  if (existingAgentPattern.test(currentCode))
  {
    return currentCode.replace(existingAgentPattern, snippet)
  }

  const firstLoopMatch = currentCode.match(/^\w+\.loop\(\)$/m)
  if (firstLoopMatch?.index !== undefined)
  {
    return `${currentCode.slice(0, firstLoopMatch.index)}${snippet}\n${currentCode.slice(firstLoopMatch.index)}`
  }

  return `${currentCode.trimEnd()}\n${snippet}\n`
}

function App()
{
  const [code, setCode] = useState(`researcher = Agent(name="Researcher", goal="Find one promising SaaS idea")
analyst = Agent(name="Analyst", goal="Review the latest SaaS idea and improve it")
researcher.loop()`)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({})
  const [savedScripts, setSavedScripts] = useState<SavedScript[]>([])
  const [savedAgents, setSavedAgents] = useState<SavedAgent[]>([])
  const [selectedScriptId, setSelectedScriptId] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [scriptName, setScriptName] = useState('SaaS Idea Workflow')
  const logPanelRef = useRef<HTMLDivElement | null>(null)

  const appendLocalLog = (message: string, level: string = 'info') =>
  {
    setLogs((currentLogs) => [
      ...currentLogs,
      {
        timestamp: new Date().toISOString(),
        level,
        message,
        eventType: 'system',
      },
    ])
  }

  const fetchSavedResources = async () =>
  {
    const [scriptsResponse, agentsResponse] = await Promise.all(
    [
      axios.get<SavedScript[]>('http://localhost:8000/scripts'),
      axios.get<SavedAgent[]>('http://localhost:8000/agents'),
    ])

    setSavedScripts(scriptsResponse.data)
    setSavedAgents(agentsResponse.data)
  }

  const handleRunAgent = async () =>
  {
    setLogs([])
    setAgentStatuses({})

    try
    {
      await axios.post('http://localhost:8000/run',
      {
        code,
      })
    }
    catch
    {
      setLogs((currentLogs) => [
        ...currentLogs,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'Failed to submit the agent script to the backend.',
        },
      ])
    }
  }

  const handleSaveScript = async () =>
  {
    try
    {
      const response = await axios.post<SavedScript>('http://localhost:8000/scripts',
      {
        id: selectedScriptId || undefined,
        name: scriptName.trim() || 'Untitled workflow',
        code,
      })

      setSelectedScriptId(response.data.id)
      setScriptName(response.data.name)
      await fetchSavedResources()
      appendLocalLog(`Saved script "${response.data.name}".`)
    }
    catch
    {
      appendLocalLog('Failed to save the current script.', 'error')
    }
  }

  const handleLoadScript = async () =>
  {
    if (selectedScriptId === '')
    {
      return
    }

    try
    {
      const response = await axios.get<SavedScript>(`http://localhost:8000/scripts/${selectedScriptId}`)
      setCode(response.data.code)
      setScriptName(response.data.name)
      appendLocalLog(`Loaded script "${response.data.name}".`)
    }
    catch
    {
      appendLocalLog('Failed to load the selected script.', 'error')
    }
  }

  const handleLoadAgent = () =>
  {
    if (selectedAgentId === '')
    {
      return
    }

    const savedAgent = savedAgents.find((agent) => agent.id === selectedAgentId)
    if (savedAgent === undefined)
    {
      appendLocalLog('Failed to find the selected agent definition.', 'error')
      return
    }

    setCode((currentCode) => upsertAgentSnippet(currentCode, savedAgent))
    appendLocalLog(`Loaded agent "${savedAgent.name}".`)
  }

  useEffect(() =>
  {
    const socket = new WebSocket('ws://localhost:8000/ws/logs')

    socket.onmessage = (event) =>
    {
      try
      {
        const logEntry = JSON.parse(event.data) as LogEntry
        setLogs((currentLogs) => [...currentLogs, logEntry])

        if (logEntry.agentName !== undefined && logEntry.state !== undefined)
        {
          setAgentStatuses((currentStatuses) => (
            {
              ...currentStatuses,
              [logEntry.agentName as string]:
              {
                name: logEntry.agentName as string,
                state: logEntry.state as string,
                message: logEntry.message,
                round: logEntry.round,
              },
            }
          ))
        }
      }
      catch
      {
        setLogs((currentLogs) => [
          ...currentLogs,
          {
            timestamp: new Date().toISOString(),
            level: 'error',
            message: 'Received an invalid log payload.',
          },
        ])
      }
    }

    socket.onerror = () =>
    {
      setLogs((currentLogs) => [
        ...currentLogs,
        {
          timestamp: new Date().toISOString(),
          level: 'error',
          message: 'WebSocket connection error.',
        },
      ])
    }

    return () =>
    {
      socket.close()
    }
  }, [])

  useEffect(() =>
  {
    void fetchSavedResources()
  }, [])

  useEffect(() =>
  {
    if (logPanelRef.current === null)
    {
      return
    }

    logPanelRef.current.scrollTop = logPanelRef.current.scrollHeight
  }, [logs])

  return (
    <div className="app-shell">
      <header className="top-bar">
        <h1 className="app-title">Agent Lab</h1>
        <button className="run-button" type="button" onClick={handleRunAgent}>
          Run Agent
        </button>
      </header>

      <main className="main-content">
        <section className="panel">
          <div className="panel-header">Editor</div>
          <div className="panel-body editor-panel-body">
            <div className="editor-toolbar">
              <div className="editor-toolbar-group">
                <input
                  className="editor-input"
                  type="text"
                  value={scriptName}
                  onChange={(event) => setScriptName(event.target.value)}
                  placeholder="Script name"
                />
                <button className="editor-toolbar-button" type="button" onClick={handleSaveScript}>
                  Save Script
                </button>
              </div>

              <div className="editor-toolbar-group">
                <select
                  className="editor-select"
                  value={selectedScriptId}
                  onChange={(event) => setSelectedScriptId(event.target.value)}
                >
                  <option value="">Select saved script</option>
                  {savedScripts.map((savedScript) => (
                    <option key={savedScript.id} value={savedScript.id}>
                      {savedScript.name}
                    </option>
                  ))}
                </select>
                <button className="editor-toolbar-button" type="button" onClick={handleLoadScript}>
                  Load Script
                </button>
              </div>

              <div className="editor-toolbar-group">
                <select
                  className="editor-select"
                  value={selectedAgentId}
                  onChange={(event) => setSelectedAgentId(event.target.value)}
                >
                  <option value="">Select saved agent</option>
                  {savedAgents.map((savedAgent) => (
                    <option key={savedAgent.id} value={savedAgent.id}>
                      {savedAgent.name}
                    </option>
                  ))}
                </select>
                <button className="editor-toolbar-button" type="button" onClick={handleLoadAgent}>
                  Load Agent
                </button>
              </div>
            </div>
            <div className="editor-shell">
              <Editor
                defaultLanguage="python"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(value) => setCode(value ?? '')}
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
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">Visualization/Status</div>
          <div className="panel-body">
            {Object.keys(agentStatuses).length === 0 ? (
              <div className="panel-placeholder">
                Agent status will appear here during execution.
              </div>
            ) : (
              <div className="agent-status-list">
                {Object.values(agentStatuses).map((agentStatus) => (
                  <div className="agent-status-card" key={agentStatus.name}>
                    <div className="agent-status-row">
                      <span className="agent-status-name">{agentStatus.name}</span>
                      <span className={`agent-status-badge agent-status-${agentStatus.state}`}>
                        {formatStateLabel(agentStatus.state)}
                      </span>
                    </div>
                    <div className="agent-status-message">{agentStatus.message}</div>
                    {agentStatus.round !== undefined && (
                      <div className="agent-status-round">Round {agentStatus.round}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </main>

      <section className="panel bottom-panel">
        <div className="panel-header panel-header-row">
          <span>Execution Logs</span>
          <button className="clear-logs-button" type="button" onClick={() => setLogs([])}>
            Clear Logs
          </button>
        </div>
        <div className="panel-body logs-panel-body" ref={logPanelRef}>
          {logs.length === 0 ? (
            <div className="panel-placeholder">
              Waiting for execution logs...
            </div>
          ) : (
            <div className="log-list">
              {logs.map((logEntry, index) =>
              {
                const logVariant = getLogVariant(logEntry)
                const logLabel = logEntry.agentName ?? logEntry.eventType ?? logEntry.level.toUpperCase()

                return (
                <div className={`log-entry log-entry-${logVariant}`} key={`${logEntry.timestamp}-${index}`}>
                  <span className="log-timestamp">{logEntry.timestamp}</span>
                  <span className={`log-level log-level-${logVariant}`}>{logLabel}</span>
                  <span className="log-message">{logEntry.message}</span>
                </div>
                )
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default App
