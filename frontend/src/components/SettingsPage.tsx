import { useEffect, useState } from 'react';
import axios from 'axios';
import { sessionSettingsUrl } from '../api';
import Button from './Button';
import styles from './SettingsPage.module.css';

type SettingsResponse =
{
  provider: string;
  model: string;
  timeout: number;
  llm_server: string;
  availableModels: string[];
};

type SettingsPageProps =
{
  sessionId: string | null;
};

function SettingsPage({ sessionId }: SettingsPageProps)
{
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [timeout, setTimeoutValue] = useState('240');
  const [llmServer, setLlmServer] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() =>
  {
    if (sessionId === null)
    {
      setIsLoading(false);
      return;
    }

    const loadSettings = async () =>
    {
      try
      {
        const response = await axios.get<SettingsResponse>(
          sessionSettingsUrl(sessionId),
          { timeout: 15000 },
        );
        setProvider(response.data.provider);
        setModel(response.data.model);
        setTimeoutValue(String(response.data.timeout));
        setLlmServer(response.data.llm_server ?? 'http://192.168.129.11:11434');
        setAvailableModels(response.data.availableModels);
      }
      catch
      {
        setErrorMessage('Failed to load settings.');
      }
      finally
      {
        setIsLoading(false);
      }
    };

    void loadSettings();
  }, [sessionId]);

  const handleSave = async () =>
  {
    if (sessionId === null)
    {
      return;
    }

    setErrorMessage(null);
    setSuccessMessage(null);
    setIsSaving(true);

    try
    {
      const response = await axios.put(
        sessionSettingsUrl(sessionId),
        {
          model,
          timeout: Number(timeout),
          llm_server: llmServer,
        },
      );

      if (response.data.status === 'error')
      {
        setErrorMessage(String(response.data.message));
        return;
      }

      setSuccessMessage('Settings saved.');
    }
    catch
    {
      setErrorMessage('Failed to save settings.');
    }
    finally
    {
      setIsSaving(false);
    }
  };

  if (sessionId === null)
  {
    return (
      <section className={styles.settingsPanel}>
        <div className={styles.settingsHeader}>Settings</div>
        <div className={styles.settingsBody}>No session loaded.</div>
      </section>
    );
  }

  if (isLoading)
  {
    return (
      <section className={styles.settingsPanel}>
        <div className={styles.settingsHeader}>Settings</div>
        <div className={styles.settingsBody}>Loading settings...</div>
      </section>
    );
  }

  return (
    <section className={styles.settingsPanel}>
      <div className={styles.settingsHeaderRow}>
        <div className={styles.settingsHeader}>Settings</div>
      </div>
      <div className={styles.settingsBody}>
        <div className={styles.settingsField}>
          <label className={styles.settingsLabel} htmlFor="provider">
            Provider
          </label>
          <input className={styles.settingsInput} id="provider" type="text" value={provider} disabled />
        </div>

        <div className={styles.settingsField}>
          <label className={styles.settingsLabel} htmlFor="llm_server">
            LLM Server
          </label>
          <input
            className={styles.settingsInput}
            id="llm_server"
            type="text"
            placeholder="http://192.168.129.11:11434"
            value={llmServer}
            onChange={(event) => setLlmServer(event.target.value)}
          />
        </div>

        <div className={styles.settingsField}>
          <label className={styles.settingsLabel} htmlFor="model">
            Ollama Model
          </label>
          <select
            className={styles.settingsInput}
            id="model"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          >
            {availableModels.map((availableModel) => (
              <option key={availableModel} value={availableModel}>
                {availableModel}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.settingsField}>
          <label className={styles.settingsLabel} htmlFor="timeout">
            Timeout Seconds
          </label>
          <input
            className={styles.settingsInput}
            id="timeout"
            type="number"
            min="1"
            step="1"
            value={timeout}
            onChange={(event) => setTimeoutValue(event.target.value)}
          />
        </div>

        {errorMessage !== null && (
          <div className={styles.errorMessage}>{errorMessage}</div>
        )}

        {successMessage !== null && (
          <div className={styles.successMessage}>{successMessage}</div>
        )}

        <div className={styles.settingsActions}>
          <Button variant="primary" onClick={handleSave} disabled={isSaving}>
            {isSaving ? 'Saving...' : 'Save Settings'}
          </Button>
        </div>
      </div>
    </section>
  );
}

export default SettingsPage;
