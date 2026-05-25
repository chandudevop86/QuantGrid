type LoaderProps = {
  label?: string;
};

export default function Loader({ label = "Loading..." }: LoaderProps) {
  return (
    <div className="loader" role="status" aria-live="polite">
      <span className="loader-dot" />
      <span>{label}</span>
    </div>
  );
}
