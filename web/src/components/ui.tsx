import type { ReactNode } from 'react'
import { ArrowUpRight, CircleAlert, LoaderCircle } from 'lucide-react'
import { ballNumber } from '../lib/format'

export function Balls({ values, small = false, matched = [] }: {values: number[]; small?: boolean; matched?: number[]}) {
  return <div className={`balls ${small ? 'balls-small' : ''}`} aria-label={`Dãy số ${values.map(ballNumber).join(', ')}`}>{values.map(n => <span className={`ball ${matched.includes(n) ? 'ball-match' : ''}`} key={n}>{ballNumber(n)}</span>)}</div>
}
export function Card({ children, className = '' }: {children: ReactNode; className?: string}) { return <section className={`card ${className}`}>{children}</section> }
export function SectionTitle({ eyebrow, title, action }: {eyebrow?: string; title: string; action?: ReactNode}) { return <div className="section-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</div> }
export function SourceLink({ url, children = 'Xem nguồn' }: {url: string; children?: ReactNode}) { return <a className="text-link" href={url} target="_blank" rel="noreferrer" aria-label={typeof children === 'string' ? undefined : 'Xem nguồn kết quả'}>{children}{typeof children === 'string' && <ArrowUpRight size={14} />}</a> }
export function Empty({ title, description, children, loading }: {title: string; description?: string; children?: ReactNode; loading?: boolean}) { return <div className="empty-state">{loading ? <LoaderCircle className="spin" size={30} /> : <CircleAlert size={30} />}<h3>{title}</h3>{description && <p>{description}</p>}{children}</div> }
