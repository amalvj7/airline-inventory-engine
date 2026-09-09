/**
 * Every endpoint returns the same error envelope, so one component renders
 * every failure in the app: the machine code, then the human message.
 */
export function Feedback({ error, success }) {
  if (error) {
    return (
      <div className="feedback feedback-error">
        <strong>{error.code ?? `HTTP ${error.status}`}</strong>
        <span>{error.message}</span>
      </div>
    );
  }
  if (success) {
    return (
      <div className="feedback feedback-ok">
        <span>{success}</span>
      </div>
    );
  }
  return null;
}
