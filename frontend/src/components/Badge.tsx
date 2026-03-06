import styles from './Badge.module.css';

export type BadgeTone = 'thinking' | 'working' | 'waiting' | 'done' | 'default';

type BadgeProps =
{
  label: string;
  tone: BadgeTone;
  showSpinner?: boolean;
};

function Badge(
{
  label,
  tone,
  showSpinner = false,
}: BadgeProps)
{
  const toneClassName =
  {
    thinking: styles.badgeThinking,
    working: styles.badgeWorking,
    waiting: styles.badgeWaiting,
    done: styles.badgeDone,
    default: '',
  }[tone];

  const badgeClassName =
    toneClassName === ''
      ? styles.badge
      : `${styles.badge} ${toneClassName}`;

  return (
    <span className={badgeClassName}>
      {showSpinner && <span className={styles.badgeSpinner} aria-hidden="true" />}
      {label}
    </span>
  );
}

export default Badge;
