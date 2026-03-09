import { useEffect, useRef, useState } from 'react';
import { Menu, Sun, Moon } from 'lucide-react';
import type { WorkflowJson } from '../workflowCode';
import styles from './AppMenu.module.css';

type AppMenuProps =
{
  theme: 'dark' | 'light';
  onThemeToggle: () => void;
  onNew: () => void;
  onLoad: (json: WorkflowJson) => void;
  onSave: () => void;
  onSettings: () => void;
  onClearLogs: () => void;
};

function AppMenu(
{
  theme,
  onThemeToggle,
  onNew,
  onLoad,
  onSave,
  onSettings,
  onClearLogs,
}: AppMenuProps)
{
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() =>
  {
    if (!open)
    {
      return;
    }

    const handleClickOutside = (event: MouseEvent) =>
    {
      if (containerRef.current !== null && !containerRef.current.contains(event.target as Node))
      {
        setOpen(false);
      }
    };

    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  }, [open]);

  const handleNew = () =>
  {
    onNew();
    setOpen(false);
  };

  const handleSettings = () =>
  {
    onSettings();
    setOpen(false);
  };

  const handleClearLogs = () =>
  {
    onClearLogs();
    setOpen(false);
  };

  const handleThemeToggle = () =>
  {
    onThemeToggle();
    setOpen(false);
  };

  const handleLoadClick = () =>
  {
    fileInputRef.current?.click();
    setOpen(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) =>
  {
    const file = e.target.files?.[0];
    if (!file)
    {
      return;
    }
    const reader = new FileReader();
    reader.onload = () =>
    {
      try
      {
        const json = JSON.parse(reader.result as string) as WorkflowJson;
        onLoad(json);
      }
      catch
      {
        // Ignore parse errors
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleSave = () =>
  {
    onSave();
    setOpen(false);
  };

  return (
    <div className={styles.container} ref={containerRef}>
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((prev) => !prev)}
        title="Menu"
        aria-expanded={open}
        aria-haspopup="true"
      >
        <Menu size={20} />
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={handleFileChange}
        aria-hidden
      />
      {open && (
        <div className={styles.dropdown}>
          <button type="button" className={styles.item} onClick={handleNew}>
            New
          </button>
          <button type="button" className={styles.item} onClick={handleLoadClick}>
            Load
          </button>
          <button type="button" className={styles.item} onClick={handleSave}>
            Save
          </button>
          <div className={styles.separator} role="separator" />
          <button type="button" className={styles.item} onClick={handleSettings}>
            Settings
          </button>
          <div className={styles.separator} role="separator" />
          <button type="button" className={`${styles.item} ${styles.itemWithIcon}`} onClick={handleThemeToggle}>
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
          <div className={styles.separator} role="separator" />
          <button type="button" className={styles.item} onClick={handleClearLogs}>
            Clear logs
          </button>
        </div>
      )}
    </div>
  );
}

export default AppMenu;
