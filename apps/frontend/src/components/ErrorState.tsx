type ErrorStateProps = { message: string; onRetry?: () => void };

export default function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="qg-state-panel qg-error-state" role="alert">
      <strong>Market decision unavailable</strong><p>{message}</p>
      {onRetry && <button type="button" onClick={onRetry}>Try again</button>}
    </div>
  );
}
