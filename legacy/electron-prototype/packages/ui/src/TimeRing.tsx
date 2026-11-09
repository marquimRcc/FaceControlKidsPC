interface TimeRingProps {
  remaining: number;
  total: number;
  size?: "small" | "large";
}

export function formatTime(seconds: number): string {
  const minutes = Math.max(0, Math.ceil(seconds / 60));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${hours}h ${String(rest).padStart(2, "0")}min` : `${rest} min`;
}

export function TimeRing({ remaining, total, size = "small" }: TimeRingProps) {
  const percent = Math.max(0, Math.min(100, (remaining / total) * 100));
  return (
    <div
      className={`time-ring time-ring--${size}`}
      style={{ "--progress": `${percent * 3.6}deg` } as React.CSSProperties}
      aria-label={`${formatTime(remaining)} restantes`}
    >
      <div className="time-ring__inside">
        <strong>{formatTime(remaining)}</strong>
        <span>restantes</span>
      </div>
    </div>
  );
}
