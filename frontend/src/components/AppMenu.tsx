import { useEffect, useRef, useState } from 'react';
import { Menu, Sun, Moon } from 'lucide-react';
import styles from './AppMenu.module.css';

type AppMenuProps =
{
  theme: 'dark' | 'light';
  onThemeToggle: () => void;
  onNew: () => void;
  onSettings: () => void;
  onClearLogs: () => void;
};

function AppMenu(
{
  theme,
  onThemeToggle,
  onNew,
  onSettings,
  onClearLogs,
}: AppMenuProps)
{
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

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
      {open && (
        <div className={styles.dropdown}>
          <button type="button" className={styles.item} onClick={handleNew}>
            New workflow
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
