import { useId, useState } from "react";

export default function Tooltip({ content, children }) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      className="tooltip-wrapper"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={() => setOpen((o) => !o)}
      aria-describedby={id}
    >
      {children}
      <span role="tooltip" id={id} className={`tooltip-bubble${open ? " is-open" : ""}`}>
        {content}
      </span>
    </span>
  );
}
