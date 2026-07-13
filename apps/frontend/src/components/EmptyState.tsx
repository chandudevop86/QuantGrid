type EmptyStateProps = { title: string; message: string };

export default function EmptyState({ title, message }: EmptyStateProps) {
  return <div className="qg-state-panel"><strong>{title}</strong><p>{message}</p></div>;
}
