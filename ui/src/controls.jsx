import React, { useId } from "react";
export function Button({ children, primary = false, ...props }) {
  return (
    <button className={primary ? "button primary" : "button"} {...props}>
      {children}
    </button>
  );
}
export function Field({ label, children }) {
  const id = useId();
  if (children?.type === "div")
    return (
      <div className="field" role="group" aria-label={label}>
        <span>{label}</span>
        {children}
      </div>
    );
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {React.cloneElement(children, { id })}
    </div>
  );
}
export function Select({ options, ...props }) {
  return (
    <select {...props}>
      {options.map((option) => {
        const [value, label] = Array.isArray(option)
          ? option
          : [option, option];
        return (
          <option key={value} value={value}>
            {label}
          </option>
        );
      })}
    </select>
  );
}
export function Panel({ title, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export const titleCase = (text) =>
  text.replaceAll("-", " ").replace(/\b\w/g, (c) => c.toUpperCase());
