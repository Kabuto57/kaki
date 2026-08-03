import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import Filters, { EMPTY_FILTERS } from './components/Filters'
import GameCard from './components/GameCard'
import { api, buildQuery } from './lib/api'

/*
  The feed is the product, so it is the whole app.

  Filters live in the URL rather than only in React state, which means a search
  is shareable, survives a refresh, and works with the back button. "Wednesdays
  in the west after 7pm" should be something you can send to someone.
*/

function filtersFromUrl() {
  const params = new URLSearchParams(window.location.search)
  return {
    ...EMPTY_FILTERS,
    weekdays: params.getAll('weekday').map(Number),
    dates: params.getAll('date'),
    regions: params.getAll('region'),
    after: params.get('after') || '',
    before: params.get('before') || '',
    maxPrice: params.get('max_price_cents') ? Number(params.get('max_price_cents')) / 100 : '',
    skill: params.get('skill') || '',
    q: params.get('q') || '',
    includeFilled: params.get('include_filled') === 'true',
  }
}

export default function App() {
  const [filters, setFilters] = useState(filtersFromUrl)
  const [games, setGames] = useState([])
  const [regions, setRegions] = useState([])
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [error, setError] = useState(null)

  // Guards against a slow early request landing after a fast later one and
  // painting stale results over fresh ones.
  const requestId = useRef(0)

  const query = useMemo(() => buildQuery(filters), [filters])

  const load = useCallback(async () => {
    const id = ++requestId.current
    setStatus('loading')
    try {
      const data = await api.games(filters)
      if (id !== requestId.current) return
      setGames(data.games)
      setStatus('ready')
    } catch (err) {
      if (id !== requestId.current) return
      setError(err.message)
      setStatus('error')
    }
  }, [filters])

  useEffect(() => {
    api
      .regions()
      .then(setRegions)
      .catch(() => setRegions([]))
  }, [])

  // Debounced so typing in the search box does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(load, 220)
    return () => clearTimeout(timer)
  }, [load])

  useEffect(() => {
    const url = query ? `?${query}` : window.location.pathname
    window.history.replaceState(null, '', url)
  }, [query])

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1 className="wordmark">
            kaki<span>.</span>
          </h1>
          <p className="tagline">Badminton games in Singapore, actually searchable</p>
        </div>
        {status === 'ready' && games.length > 0 && (
          <span className="live-count">
            {games.length} game{games.length === 1 ? '' : 's'}
          </span>
        )}
      </header>

      <Filters filters={filters} onChange={setFilters} regions={regions} />

      {status === 'loading' && (
        <div className="game-list" aria-busy="true" aria-label="Loading games">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      )}

      {status === 'error' && (
        <div className="notice error">
          <h2>Couldn't load games</h2>
          <p>{error}</p>
          <button type="button" className="chip" style={{ marginTop: 14 }} onClick={load}>
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && games.length === 0 && (
        <div className="notice">
          <h2>Nothing matches that</h2>
          <p>
            Try widening the day or area, or clearing a filter. Games only appear here once
            someone posts them in the group.
          </p>
        </div>
      )}

      {status === 'ready' && games.length > 0 && (
        <>
          <div className="game-list">
            {games.map((game) => (
              <GameCard key={game.id} game={game} />
            ))}
          </div>
          <p className="footnote">
            Games come from the sg_badminton Telegram group. Join through the original post —
            Kaki only helps you find it.
          </p>
        </>
      )}
    </div>
  )
}
