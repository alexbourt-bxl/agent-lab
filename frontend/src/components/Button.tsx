import type { ReactNode } from 'react';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'run' | 'clearLogs';

type ButtonProps =
{
  variant: ButtonVariant;
  onClick?: () => void;
  disabled?: boolean;
  icon?: ReactNode;
  showSpinner?: boolean;
  elapsedTime?: string;
  title?: string;
  children: ReactNode;
};

function Button(
{
  variant,
  onClick,
  disabled = false,
  icon,
  showSpinner = false,
  elapsedTime,
  title,
  children,
}: ButtonProps)
{
  const variantClassName =
  {
    primary: styles.buttonPrimary,
    secondary: styles.buttonSecondary,
    run: styles.buttonRun,
    clearLogs: styles.buttonClearLogs,
  }[variant];

  return (
    <button
      type="button"
      className={`${styles.button} ${variantClassName}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
    >
      {showSpinner ? (
        <span className={styles.buttonSpinner} aria-hidden="true" />
      ) : (
        icon !== undefined && <span className={styles.buttonIcon}>{icon}</span>
      )}
      {showSpinner && elapsedTime !== undefined && (
        <span className={styles.buttonElapsed}>{elapsedTime}</span>
      )}
      {children}
    </button>
  );
}

export default Button;
