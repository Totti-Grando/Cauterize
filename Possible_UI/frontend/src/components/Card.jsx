// Generic card surface + header. Used everywhere for consistent spacing.

export function Card({ className = '', children, as: Comp = 'div', hover = false, ...props }) {
  return (
    <Comp
      className={`card ${hover ? 'transition-shadow hover:shadow-cardhover' : ''} ${className}`}
      {...props}
    >
      {children}
    </Comp>
  )
}

export function CardHeader({ title, subtitle, icon: Icon, actions, eyebrow, className = '' }) {
  return (
    <div className={`flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4 ${className}`}>
      <div className="flex items-start gap-3">
        {Icon && (
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
            <Icon className="h-5 w-5" />
          </span>
        )}
        <div>
          {eyebrow && <div className="eyebrow mb-0.5">{eyebrow}</div>}
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function CardBody({ className = '', children }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>
}
