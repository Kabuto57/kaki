/*
  One place that knows how to talk to the API.

  Errors from the backend always arrive as {error: {code, message}}, so this
  unwraps them into a real Error carrying a message written for a human. That
  contract is why nothing else in the app needs a try/catch that inspects
  response shapes.
*/

const BASE = import.meta.env.VITE_API_URL || '/api'

class ApiError extends Error {
  constructor(message, code, status) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    })
  } catch {
    // fetch only rejects on network failure, which is a different problem from
    // the server saying no, and deserves a different message.
    throw new ApiError("Can't reach the server. Check your connection.", 'network', 0)
  }

  if (response.status === 204) return null

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(
      body?.error?.message || 'Something went wrong.',
      body?.error?.code || 'unknown',
      response.status,
    )
  }
  return body
}

/* Turns the filter state into a query string, dropping anything unset so the
   URL stays short enough to share. */
export function buildQuery(filters) {
  const params = new URLSearchParams()
  const add = (key, value) => {
    if (value !== null && value !== undefined && value !== '') params.append(key, value)
  }

  filters.weekdays?.forEach((day) => params.append('weekday', day))
  filters.dates?.forEach((date) => params.append('date', date))
  filters.regions?.forEach((region) => params.append('region', region))
  filters.venues?.forEach((venue) => params.append('venue', venue))

  add('after', filters.after)
  add('before', filters.before)
  add('q', filters.q)
  add('skill', filters.skill)
  if (filters.maxPrice) add('max_price_cents', Math.round(filters.maxPrice * 100))
  if (filters.includeFilled) add('include_filled', 'true')
  if (filters.fromTime) add('from_time', filters.fromTime)
  if (filters.toTime) add('to_time', filters.toTime)

  return params.toString()
}

/* Same shared filters as buildQuery, minus anything date-related — the
   calendar's own from_date/to_date window replaces those. */
function buildCalendarQuery(filters, fromDate, toDate) {
  const params = new URLSearchParams()
  const add = (key, value) => {
    if (value !== null && value !== undefined && value !== '') params.append(key, value)
  }

  filters.regions?.forEach((region) => params.append('region', region))
  filters.venues?.forEach((venue) => params.append('venue', venue))

  add('after', filters.after)
  add('before', filters.before)
  add('q', filters.q)
  add('skill', filters.skill)
  if (filters.maxPrice) add('max_price_cents', Math.round(filters.maxPrice * 100))
  if (filters.includeFilled) add('include_filled', 'true')
  add('from_date', fromDate)
  add('to_date', toDate)

  return params.toString()
}

export const api = {
  games: (filters) => {
    const query = buildQuery(filters)
    return request(`/games${query ? `?${query}` : ''}`)
  },
  calendarCounts: (filters, fromDate, toDate) =>
    request(`/games/calendar?${buildCalendarQuery(filters, fromDate, toDate)}`),
  stats: () => request('/games/stats'),
  venues: () => request('/venues'),
  regions: () => request('/venues/regions'),
}

export { ApiError }
