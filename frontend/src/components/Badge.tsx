import styles from './Badge.module.css';

export type BadgeTone = 'thinking' | 'working' | 'waiting' | 'done' | 'error' | 'default';

type BadgeProps =
{
  label: string;
  tone: BadgeTone;
  showSpinner?: boolean;
  elapsedTime?: string;
  progress?: number;
};

function Badge(
{
  label,
  tone,
  showSpinner = false,
  elapsedTime,
  progress,
}: BadgeProps)
{
  const toneClassName =
  {
    thinking: styles.badgeThinking,
    working: styles.badgeWorking,
    waiting: styles.badgeWaiting,
    done: styles.badgeDone,
    error: styles.badgeError,
    default: '',
  }[tone];

  const badgeClassName =
    toneClassName === ''
      ? styles.badge
      : `${styles.badge} ${toneClassName}`;

  return (
    <span
      className={badgeClassName}
      style={progress !== undefined ? { '--badge-progress': progress } as React.CSSProperties : undefined}
    >
      {progress !== undefined && (
        <span className={styles.badgeProgress} aria-hidden="true" />
      )}
      {showSpinner && <span className={styles.badgeSpinner} aria-hidden="true" />}
      {showSpinner && elapsedTime !== undefined && (
        <span className={styles.badgeElapsed}> {elapsedTime}</span>
      )}
      {label}
    </span>
  );
}

export default Badge;
