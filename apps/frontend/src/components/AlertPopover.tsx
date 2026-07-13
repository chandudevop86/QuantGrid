type AlertPopoverProps = { alerts: string[]; open: boolean; onToggle: () => void };

export default function AlertPopover({ alerts, open, onToggle }: AlertPopoverProps) {
  return (
    <div className="qg-alert-menu">
      <button type="button" className="qg-header-button" aria-haspopup="true" aria-expanded={open} onClick={onToggle}>
        <span aria-hidden="true">⌁</span><span>Alerts</span>{alerts.length > 0 && <small>{alerts.length}</small>}
      </button>
      {open && <div className="qg-alert-popover" role="status"><strong>Alerts</strong>{alerts.length ? alerts.map((alert) => <p key={alert}>{alert}</p>) : <p>No active alerts.</p>}</div>}
    </div>
  );
}
