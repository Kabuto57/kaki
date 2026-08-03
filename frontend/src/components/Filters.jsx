/*
  Filters.

  The quick chips exist because almost every visit is one of about four
  questions — tonight, tomorrow, the weekend, or a specific area. Making those
  one tap, and putting the fiddly controls underneath, means the common case
  costs nothing and the rare case is still possible. The calendar below the
  chips handles anything more specific — a particular date, or several.
*/
import Calendar from './Calendar'

// Saturday and Sunday, in the Monday-is-0 numbering the API uses.
const WEEKEND = [5, 6]

const TIME_OF_DAY = [
  { key: 'morning', label: 'Morning', after: '06:00', before: '11:59' },
  { key: 'afternoon', label: 'Afternoon', after: '12:00', before: '17:59' },
  { key: 'evening', label: 'Evening', after: '18:00', before: '23:59' },
]

export const EMPTY_FILTERS = {
  preset: null,
  weekdays: [],
  dates: [],
  regions: [],
  after: '',
  before: '',
  maxPrice: '',
  skill: '',
  q: '',
  includeFilled: false,
  fromTime: null,
  toTime: null,
}

function sgDateString(date) {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Singapore',
  }).format(date)
}

function endOfTodaySg() {
  return new Date(`${sgDateString(new Date())}T23:59:59+08:00`).toISOString()
}

function startOfTomorrowSg() {
  const tomorrow = new Date(new Date(endOfTodaySg()).getTime() + 1000)
  return new Date(`${sgDateString(tomorrow)}T00:00:00+08:00`).toISOString()
}

function endOfTomorrowSg() {
  const tomorrow = new Date(new Date(endOfTodaySg()).getTime() + 1000)
  return new Date(`${sgDateString(tomorrow)}T23:59:59+08:00`).toISOString()
}

export default function Filters({ filters, onChange, regions }) {
  const set = (patch) => onChange({ ...filters, ...patch })

  const applyPreset = (preset) => {
    if (filters.preset === preset) {
      set({ preset: null, weekdays: [], dates: [], fromTime: null, toTime: null })
      return
    }
    if (preset === 'tonight') {
      set({ preset, weekdays: [], dates: [], fromTime: null, toTime: endOfTodaySg() })
    } else if (preset === 'tomorrow') {
      set({ preset, weekdays: [], dates: [], fromTime: startOfTomorrowSg(), toTime: endOfTomorrowSg() })
    } else if (preset === 'weekend') {
      set({ preset, weekdays: WEEKEND, dates: [], fromTime: null, toTime: null })
    }
  }

  const applyTimeOfDay = (period) => {
    if (filters.after === period.after && filters.before === period.before) {
      set({ after: '', before: '' })
      return
    }
    set({ after: period.after, before: period.before })
  }

  const hasAny =
    filters.preset ||
    filters.weekdays.length ||
    filters.dates.length ||
    filters.regions.length ||
    filters.after ||
    filters.before ||
    filters.maxPrice ||
    filters.skill ||
    filters.q ||
    filters.includeFilled

  return (
    <div className="filters">
      <div className="chip-row">
        <button
          type="button"
          className="chip"
          aria-pressed={filters.preset === 'tonight'}
          onClick={() => applyPreset('tonight')}
        >
          Tonight
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={filters.preset === 'tomorrow'}
          onClick={() => applyPreset('tomorrow')}
        >
          Tomorrow
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={filters.preset === 'weekend'}
          onClick={() => applyPreset('weekend')}
        >
          Weekend
        </button>
      </div>

      <div className="chip-row">
        {TIME_OF_DAY.map((period) => (
          <button
            key={period.key}
            type="button"
            className="chip"
            aria-pressed={filters.after === period.after && filters.before === period.before}
            onClick={() => applyTimeOfDay(period)}
          >
            {period.label}
          </button>
        ))}
      </div>

      <Calendar filters={filters} onChange={onChange} />

      <div className="filter-detail">
        <div className="field">
          <label htmlFor="f-region">Area</label>
          <select
            id="f-region"
            value={filters.regions[0] || ''}
            onChange={(event) =>
              set({ regions: event.target.value ? [event.target.value] : [] })
            }
          >
            <option value="">Anywhere</option>
            {regions.map((region) => (
              <option key={region} value={region}>
                {region}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-after">Starts after</label>
          <input
            id="f-after"
            type="time"
            value={filters.after}
            onChange={(event) => set({ after: event.target.value })}
          />
        </div>

        <div className="field">
          <label htmlFor="f-price">Max price</label>
          <input
            id="f-price"
            type="number"
            min="0"
            step="1"
            placeholder="any"
            value={filters.maxPrice}
            onChange={(event) => set({ maxPrice: event.target.value })}
          />
        </div>

        <div className="field">
          <label htmlFor="f-q">Search text</label>
          <input
            id="f-q"
            type="search"
            placeholder="e.g. doubles"
            value={filters.q}
            onChange={(event) => set({ q: event.target.value })}
          />
        </div>
      </div>

      {hasAny && (
        <button type="button" className="reset" onClick={() => onChange(EMPTY_FILTERS)}>
          Clear filters
        </button>
      )}
    </div>
  )
}
