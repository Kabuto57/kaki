/*
  Display helpers.

  The API serves UTC; everything a person reads is Singapore time. Doing that
  conversion in one place — here — is what stops an 8pm game showing up as noon
  somewhere in the UI.
*/

const TZ = 'Asia/Singapore'

const dayFormat = new Intl.DateTimeFormat('en-SG', { weekday: 'short', timeZone: TZ })
const dateFormat = new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', timeZone: TZ })
const timeFormat = new Intl.DateTimeFormat('en-SG', {
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZone: TZ,
})

export function sgDate(iso) {
  return new Date(iso)
}

export function dayLabel(iso) {
  const date = sgDate(iso)
  const today = todayInSg()
  const days = daysBetween(today, startOfSgDay(date))

  if (days === 0) return 'Today'
  if (days === 1) return 'Tmr'
  return dayFormat.format(date).toUpperCase()
}

/* A stable key for color-coding the day label — 'today', 'tmr', or the
   weekday ('mon'..'sun') — independent of the display text above. */
export function dayKey(iso) {
  const date = sgDate(iso)
  const today = todayInSg()
  const days = daysBetween(today, startOfSgDay(date))

  if (days === 0) return 'today'
  if (days === 1) return 'tmr'
  return dayFormat.format(date).toLowerCase()
}

export function dateLabel(iso) {
  return dateFormat.format(sgDate(iso))
}

/* "8pm" reads better than "8:00 pm" on a card, so drop a zero minute. */
export function timeLabel(iso) {
  return timeFormat.format(sgDate(iso)).replace(':00', '').replace(/\s/g, '').toLowerCase()
}

export function rangeLabel(startIso, endIso) {
  if (!startIso) return ''
  if (!endIso) return timeLabel(startIso)
  return `${timeLabel(startIso)}–${timeLabel(endIso)}`
}

/* How far off it is, phrased the way someone deciding tonight's plans thinks. */
export function untilLabel(iso) {
  const hours = (sgDate(iso) - new Date()) / 36e5
  if (hours < 0) return 'started'
  if (hours < 1) return `${Math.round(hours * 60)}m`
  if (hours < 24) return `${Math.round(hours)}h`
  return `${Math.round(hours / 24)}d`
}

export function isTonight(iso) {
  const hours = (sgDate(iso) - new Date()) / 36e5
  return hours >= 0 && hours <= 12
}

export function priceLabel(cents) {
  if (cents === null || cents === undefined) return null
  if (cents === 0) return 'free'
  return `$${(cents / 100).toFixed(2).replace(/\.00$/, '')}`
}

function startOfSgDay(date) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: TZ,
  }).format(date)
  return new Date(`${parts}T00:00:00+08:00`)
}

function todayInSg() {
  return startOfSgDay(new Date())
}

function daysBetween(a, b) {
  return Math.round((b - a) / 864e5)
}
