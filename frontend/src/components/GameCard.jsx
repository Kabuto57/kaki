import { useState } from 'react'

import {
  dateLabel,
  dayKey,
  dayLabel,
  isTonight,
  priceLabel,
  rangeLabel,
  timeLabel,
  untilLabel,
} from '../lib/format'

/*
  One game.

  The card changes shape with how well the post was understood. A confidently
  parsed game gets a clean layout. A partially parsed one also shows a clipped
  strip of the original text, because the honest thing to do when we are
  unsure is to show our working rather than present a guess as fact. Clicking
  the card expands the full original message for any game, parsed well or
  not — the post is still the source of truth.
*/
export default function GameCard({ game }) {
  const venueName = game.venue?.name || game.raw_venue
  const price = priceLabel(game.price_cents)
  const tonight = game.starts_at && isTonight(game.starts_at)
  const [expanded, setExpanded] = useState(false)

  return (
    <article
      className="game"
      onClick={() => setExpanded((v) => !v)}
      aria-expanded={expanded}
    >
      <div className="when">
        <div className="day" data-day={game.starts_at ? dayKey(game.starts_at) : undefined}>
          {game.starts_at ? dayLabel(game.starts_at) : '—'}
        </div>
        <div className="time">{game.starts_at ? timeLabel(game.starts_at) : '?'}</div>
        <div className="until">
          {game.starts_at ? untilLabel(game.starts_at) : 'no date'}
        </div>
      </div>

      <div className="game-body">
        <h3 className={`venue${venueName ? '' : ' unknown'}`}>
          {venueName || 'Venue not stated'}
        </h3>

        <div className="facts">
          {game.starts_at && <span>{dateLabel(game.starts_at)}</span>}
          {game.ends_at && (
            <>
              <span className="sep">·</span>
              <span>{rangeLabel(game.starts_at, game.ends_at)}</span>
            </>
          )}
          {game.venue?.region && (
            <>
              <span className="sep">·</span>
              <span>{game.venue.region}</span>
            </>
          )}
          {game.distance_km !== null && game.distance_km !== undefined && (
            <>
              <span className="sep">·</span>
              <span>{game.distance_km} km</span>
            </>
          )}
          {price && (
            <>
              <span className="sep">·</span>
              <span className="price">{price}</span>
            </>
          )}
          {game.spots_wanted && (
            <>
              <span className="sep">·</span>
              <span className="spots">{game.spots_wanted} wanted</span>
            </>
          )}
        </div>

        <div className="facts" style={{ marginTop: 8, gap: 6 }}>
          {tonight && !game.is_filled && <span className="badge tonight">Tonight</span>}
          {game.is_filled && <span className="badge filled">Filled</span>}
          {game.skill && <span className="badge skill">{game.skill}</span>}
        </div>

        {expanded ? (
          <div className="raw-strip expanded">
            <span className="raw-label">Original message</span>
            {game.source_text}
          </div>
        ) : (
          game.confidence === 'partial' &&
          game.source_text && (
            <div className="raw-strip">
              <span className="raw-label">Couldn't read it all — here's the post</span>
              {game.source_text}
            </div>
          )
        )}

        <div className="card-actions">
          <a
            className="open-link"
            href={game.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            Open in Telegram →
          </a>
          {game.posted_by && <span className="posted-by">by {game.posted_by}</span>}
        </div>
      </div>
    </article>
  )
}
