/*
  Month-grid date picker.

  Click a day to toggle it in the selection; click-drag across days selects the
  whole span in between. Per-day game counts come from a dedicated endpoint so
  someone can see which days are worth clicking before they click — an empty
  day is visibly skippable rather than a dead end after the fact.

  Selecting any date here is mutually exclusive with the quick-preset chips
  (Tonight/Tomorrow/Weekend/Evenings), same as the old weekday toggles were —
  picking a specific day is a different question than "soonest game".
*/
import { useEffect, useRef, useState } from 'react'

import { api } from '../lib/api'

const MONTH_LABEL = new Intl.DateTimeFormat('en-SG', {
  month: 'long',
  year: 'numeric',
  timeZone: 'Asia/Singapore',
})
const WEEKDAY_HEADS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

function sgToday() {
  const [y, m, d] = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Singapore',
  })
    .format(new Date())
    .split('-')
    .map(Number)
  return { year: y, month: m - 1, day: d }
}

function pad(n) {
  return String(n).padStart(2, '0')
}

function dateStr(year, month, day) {
  return `${year}-${pad(month + 1)}-${pad(day)}`
}

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate()
}

/* Monday-first, fixed 6x7 grid. Days outside the visible month are inert
   placeholders — they exist only to keep the week columns aligned. */
function buildGrid(year, month) {
  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7
  const total = daysInMonth(year, month)
  const cells = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let day = 1; day <= total; day++) cells.push({ dateStr: dateStr(year, month, day), day })
  while (cells.length < 42) cells.push(null)
  return cells
}

function rangeBetween(aStr, bStr) {
  const a = new Date(`${aStr}T00:00:00`)
  const b = new Date(`${bStr}T00:00:00`)
  const [start, end] = a <= b ? [a, b] : [b, a]
  const out = []
  for (const d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    out.push(dateStr(d.getFullYear(), d.getMonth(), d.getDate()))
  }
  return out
}

export default function Calendar({ filters, onChange }) {
  const today = sgToday()
  const [view, setView] = useState({ year: today.year, month: today.month })
  const [counts, setCounts] = useState({})
  const [preview, setPreview] = useState([])
  const [expanded, setExpanded] = useState(filters.dates.length === 0)

  const dragAnchor = useRef(null)
  const dragMoved = useRef(false)

  const grid = buildGrid(view.year, view.month)
  const todayStr = dateStr(today.year, today.month, today.day)
  const selected = new Set(filters.dates)

  // Refetch counts when the visible month changes, or when a non-date filter
  // that affects which games match changes — a region/price/skill change
  // should redraw the counts, not just the game list below.
  const countKey = JSON.stringify({
    region: filters.regions,
    after: filters.after,
    before: filters.before,
    maxPrice: filters.maxPrice,
    skill: filters.skill,
    q: filters.q,
    includeFilled: filters.includeFilled,
  })

  useEffect(() => {
    const from = dateStr(view.year, view.month, 1)
    const to = dateStr(view.year, view.month, daysInMonth(view.year, view.month))
    let cancelled = false
    api
      .calendarCounts(filters, from, to)
      .then((data) => {
        if (!cancelled) setCounts(data)
      })
      .catch(() => {
        if (!cancelled) setCounts({})
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.year, view.month, countKey])

  useEffect(() => {
    const finishDrag = () => {
      if (dragAnchor.current === null) return
      const span = dragMoved.current ? preview : [dragAnchor.current]
      const next = new Set(selected)
      if (span.length === 1 && selected.has(span[0]) && !dragMoved.current) {
        next.delete(span[0])
      } else {
        span.forEach((d) => next.add(d))
      }
      onChange({ ...filters, preset: null, dates: [...next] })
      dragAnchor.current = null
      dragMoved.current = false
      setPreview([])
      setExpanded(false)
    }
    window.addEventListener('mouseup', finishDrag)
    return () => window.removeEventListener('mouseup', finishDrag)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview, filters])

  const changeMonth = (delta) => {
    setView(({ year, month }) => {
      const next = month + delta
      if (next < 0) return { year: year - 1, month: 11 }
      if (next > 11) return { year: year + 1, month: 0 }
      return { year, month: next }
    })
  }

  const startDrag = (cellDate) => {
    dragAnchor.current = cellDate
    dragMoved.current = false
    setPreview([cellDate])
  }

  const enterDrag = (cellDate) => {
    if (dragAnchor.current === null) return
    if (cellDate !== dragAnchor.current) dragMoved.current = true
    setPreview(rangeBetween(dragAnchor.current, cellDate))
  }

  const summary =
    filters.dates.length === 0
      ? 'Any date'
      : filters.dates.length === 1
        ? '1 day selected'
        : `${filters.dates.length} days selected`

  return (
    <div className="calendar">
      <button
        type="button"
        className="calendar-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span>{summary}</span>
        <span className="calendar-chevron" data-open={expanded || undefined}>
          ▾
        </span>
      </button>

      {expanded && (
        <>
          <div className="calendar-header">
            <button
              type="button"
              className="calendar-nav"
              onClick={() => changeMonth(-1)}
              aria-label="Previous month"
            >
              ‹
            </button>
            <span className="calendar-month">{MONTH_LABEL.format(new Date(view.year, view.month, 1))}</span>
            <button type="button" className="calendar-nav" onClick={() => changeMonth(1)} aria-label="Next month">
              ›
            </button>
          </div>

          <div className="calendar-grid">
            {WEEKDAY_HEADS.map((label, i) => (
              <span key={i} className="calendar-weekday">
                {label}
              </span>
            ))}

            {grid.map((cell, i) => {
              if (!cell) return <span key={i} className="calendar-day out" />
              const count = counts[cell.dateStr] || 0
              const isSelected = selected.has(cell.dateStr)
              const isPreview = preview.includes(cell.dateStr)
              const isPast = cell.dateStr < todayStr

              return (
                <button
                  key={i}
                  type="button"
                  className="calendar-day"
                  disabled={isPast}
                  aria-pressed={isSelected}
                  data-preview={isPreview || undefined}
                  data-today={cell.dateStr === todayStr || undefined}
                  onMouseDown={() => !isPast && startDrag(cell.dateStr)}
                  onMouseEnter={() => !isPast && enterDrag(cell.dateStr)}
                >
                  <span className="calendar-day-num">{cell.day}</span>
                  {count > 0 && <span className="calendar-day-count">{count}</span>}
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
