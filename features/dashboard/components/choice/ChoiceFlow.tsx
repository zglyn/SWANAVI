"use client";

import Link from "next/link";
import { useEffect, type InputHTMLAttributes, type ReactNode } from "react";
import { SwanLogo } from "@/components/swan/Logo";
import styles from "./choice-flow.module.css";

export function ChoiceFlow({
  title,
  step,
  steps,
  action,
  onAction,
  actionDisabled,
  onBack,
  children,
}: {
  title: string;
  step?: number;
  steps?: number;
  action?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  onBack?: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const previous = {
      html: html.style.background,
      body: body.style.background,
      color: body.style.color,
    };
    html.style.background = "#000000";
    body.style.background = "#000000";
    body.style.color = "#ffffff";
    return () => {
      html.style.background = previous.html;
      body.style.background = previous.body;
      body.style.color = previous.color;
    };
  }, []);

  return (
    <div className="swan-stage">
    <main className={styles.frame}>
      <div className={styles.column}>
        <header className={styles.brand}>
          <Link href="/" aria-label="Swanavi home">
            <SwanLogo />
          </Link>
          <Link href="/profile" className={styles.profile}>Profile</Link>
        </header>
        {onBack ? (
          <button type="button" className={styles.back} onClick={onBack}>
            Back
          </button>
        ) : null}
        {step && steps ? (
          <div>
            <div
              className={styles.track}
              role="progressbar"
              aria-valuemin={1}
              aria-valuemax={steps}
              aria-valuenow={step}
              aria-label={`${step} of ${steps}`}
            >
              <div className={styles.bar} style={{ width: `${(step / steps) * 100}%` }} />
            </div>
            <p className={styles.count}>{step} of {steps}</p>
          </div>
        ) : null}
        <div key={`${step ?? 0}-${title}`} className={styles.body}>
          <h1 className={styles.title}>{title}</h1>
          {children}
        </div>
      </div>
      {action && onAction ? (
        <div className={styles.dock}>
          <div className={styles.dockInner}>
            <button type="button" className={styles.continue} onClick={onAction} disabled={actionDisabled}>
              {action}
            </button>
          </div>
        </div>
      ) : null}
    </main>
    </div>
  );
}

export function ChoiceSection({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      {title ? <p className={styles.kicker}>{title}</p> : null}
      {children}
    </section>
  );
}

export function ChoiceStack({ as = "div", children }: { as?: "div" | "ul"; children: ReactNode }) {
  const Tag = as;
  return <Tag className={styles.stack}>{children}</Tag>;
}

export function ChoiceRow({
  pressed,
  onClick,
  children,
}: {
  pressed?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className={styles.row} aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

export function ChoiceSub({ children }: { children: ReactNode }) {
  return <span className={styles.sub}>{children}</span>;
}

export function ChoicePills({ children }: { children: ReactNode }) {
  return <div className={styles.pills}>{children}</div>;
}

export function ChoicePill({
  pressed,
  onClick,
  children,
}: {
  pressed?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className={styles.pill} aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

export function ChoiceField({ label, ...props }: { label?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={styles.label}>
      {label ? <span>{label}</span> : null}
      <input {...props} className={styles.field} />
    </label>
  );
}

export function ChoiceNote({ children, live }: { children: ReactNode; live?: boolean }) {
  return (
    <p className={styles.note} aria-live={live ? "polite" : undefined}>
      {children}
    </p>
  );
}

export function ChoiceSummary({ children }: { children: ReactNode }) {
  return <p className={styles.summary}>{children}</p>;
}

export function ChoiceCard({ children }: { children: ReactNode }) {
  return <div className={styles.card}>{children}</div>;
}

export function ChoiceSlider({
  label,
  valueLabel,
  ...props
}: { label: string; valueLabel: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className={styles.card}>
      <span className={styles.sliderHead}>
        <span className={styles.capitalize}>{label}</span>
        <span className={styles.muted}>{valueLabel}</span>
      </span>
      <input type="range" {...props} className={styles.slider} />
    </label>
  );
}

export function choiceName(skipped: boolean) {
  return skipped ? `${styles.name} ${styles.skip}` : styles.name;
}
