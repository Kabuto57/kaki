"""The canonical venue list for Singapore, plus the aliases people actually type.

This file is the single place venues are defined. The seeder writes it into the
database; the parser matches against the aliases in memory. Adding a venue means
editing this list and re-running `python -m scripts.seed_venues`.

Aliases matter more than they look. "CCK", "cck sports", and "Choa Chu Kang"
are the same building, and a matcher that only knows the official name will miss
most of the group's posts. Longest alias wins so "jurong east" beats "jurong".
"""

from __future__ import annotations

VENUES = [
    ('choa_chu_kang', 'Choa Chu Kang Sports Hall', 'West', ['choa chu kang', 'chua chu kang', 'cck sports', 'cck hall', 'cck sh', 'cck'], (1.3852, 103.744)),
    ('bukit_gombak', 'Bukit Gombak Sports Hall', 'West', ['bukit gombak', 'bt gombak', 'gombak sports', 'bkt gombak'], (1.3588, 103.7516)),
    ('bukit_batok', 'Bukit Batok Sports Centre', 'West', ['bukit batok', 'bt batok', 'bkt batok'], (1.3496, 103.7497)),
    ('bukit_panjang', 'Bukit Panjang CC', 'West', ['bukit panjang', 'bt panjang', 'bkt panjang', 'bp cc', 'senja cashew', 'senja-cashew'], (1.3774, 103.7639)),
    ('zhenghua', 'Zhenghua CC', 'West', ['zhenghua', 'zheng hua'], (1.3818, 103.7669)),
    ('jurong_east', 'Jurong East Sports Hall', 'West', ['jurong east', 'jurong east sports', 'je sports hall', 'jurong east hall'], (1.3329, 103.7436)),
    ('jurong_west', 'Jurong West Sports Hall', 'West', ['jurong west', 'jw sports hall', 'jurong west hall'], (1.3404, 103.709)),
    ('clementi', 'Clementi Sports Hall', 'West', ['clementi'], (1.3151, 103.7649)),
    ('hong_kah', 'Hong Kah North CC', 'West', ['hong kah', 'hongkah'], (1.3737, 103.7297)),
    ('boon_lay', 'Boon Lay CC', 'West', ['boon lay'], (1.3467, 103.7098)),
    ('taman_jurong', 'Taman Jurong CC', 'West', ['taman jurong'], (1.3337, 103.7208)),
    ('pioneer', 'Pioneer CC', 'West', ['pioneer cc', 'pioneer community'], (1.3376, 103.6972)),
    ('woodlands', 'Woodlands Sports Hall', 'North', ['woodlands', 'woodland sports'], (1.436, 103.786)),
    ('yishun', 'Yishun Sports Hall', 'North', ['yishun'], (1.4297, 103.835)),
    ('sembawang', 'Sembawang Sports Hall', 'North', ['sembawang', 'sembawang cc'], (1.4491, 103.82)),
    ('bukit_canberra', 'Bukit Canberra', 'North', ['bukit canberra', 'bt canberra', 'canberra'], (1.4436, 103.829)),
    ('marsiling', 'Marsiling CC', 'North', ['marsiling'], (1.4331, 103.7742)),
    ('admiralty', 'Admiralty CC', 'North', ['admiralty'], (1.4407, 103.8007)),
    ('ang_mo_kio', 'Ang Mo Kio CC / Sports Hall', 'North-East', ['ang mo kio', 'amk cc', 'amk sports', 'amk hall', 'amk'], (1.37, 103.8496)),
    ('yio_chu_kang', 'Yio Chu Kang Sports Hall', 'North-East', ['yio chu kang', 'yck sports', 'yck hall', 'yck'], (1.3822, 103.8449)),
    ('hougang', 'Hougang Sports Hall', 'North-East', ['hougang', 'hg sports hall'], (1.3714, 103.8926)),
    ('sengkang', 'Sengkang Sports Hall', 'North-East', ['sengkang', 'seng kang', 'sk sports hall'], (1.391, 103.894)),
    ('punggol', 'Punggol Sports Hall', 'North-East', ['punggol', 'pungol'], (1.4041, 103.9025)),
    ('serangoon', 'Serangoon Sports Hall', 'North-East', ['serangoon', 'heartbeat@bedok north'], (1.3554, 103.8737)),
    ('toa_payoh', 'Toa Payoh Sports Hall', 'North-East', ['toa payoh', 'tpy sports', 'tpy hall', 'tpy'], (1.3343, 103.8474)),
    ('bishan', 'Bishan Sports Hall', 'North-East', ['bishan'], (1.3506, 103.8485)),
    ('tampines', 'Tampines Sports Hall / Our Tampines Hub', 'East', ['tampines', 'our tampines hub', 'oth sports', 'oth'], (1.353, 103.9403)),
    ('pasir_ris', 'Pasir Ris Sports Hall', 'East', ['pasir ris', 'pasir-ris'], (1.3721, 103.9474)),
    ('bedok', 'Bedok Sports Hall / Heartbeat@Bedok', 'East', ['bedok', 'heartbeat@bedok', 'heartbeat bedok'], (1.3236, 103.9273)),
    ('geylang', 'Wisma Geylang Serai', 'East', ['geylang serai', 'wisma geylang', 'geylang'], (1.3167, 103.8987)),
    ('eunos', 'Eunos CC', 'East', ['eunos'], (1.3212, 103.9032)),
    ('kampong_ubi', 'Kampong Ubi CC', 'East', ['kampong ubi', 'kg ubi'], (1.3247, 103.8963)),
    ('changi', 'Changi Simei CC', 'East', ['changi simei', 'simei cc'], (1.3434, 103.953)),
    ('marine_parade', 'Marine Parade CC', 'East', ['marine parade', 'mpcc'], (1.302, 103.9068)),
    ('kallang', 'Kallang Sports Hall / OCBC Arena', 'Central', ['kallang', 'ocbc arena', 'sports hub', 'singapore sports hub'], (1.3033, 103.8749)),
    ('delta', 'Delta Sports Hall', 'Central', ['delta sports', 'delta hall', 'delta sh'], (1.2907, 103.828)),
    ('queenstown', 'Queenstown Sports Hall', 'Central', ['queenstown', 'queenstown sports'], (1.2942, 103.806)),
    ('jalan_besar', 'Jalan Besar Sports Hall', 'Central', ['jalan besar', 'jln besar'], (1.3086, 103.8556)),
    ('farrer_park', 'Farrer Park', 'Central', ['farrer park', 'farrer'], (1.3123, 103.8524)),
    ('singapore_badminton_hall', 'Singapore Badminton Hall', 'Central', ['singapore badminton hall', 'sg badminton hall', 'sbh'], (1.3057, 103.8617)),
    ('pek_kio', 'Pek Kio CC', 'Central', ['pek kio'], (1.321, 103.8461)),
    ('whampoa', 'Whampoa CC', 'Central', ['whampoa'], (1.3238, 103.8556)),
    ('bukit_merah', 'Bukit Merah / Enabling Village', 'Central', ['bukit merah', 'bt merah', 'enabling village'], (1.2838, 103.8203)),
    ('st_badminton', 'ST Badminton Academy', 'Private', ['st badminton', 'st academy'], (1.335, 103.7436)),
    ('smash_badminton', 'Smash Badminton', 'Private', ['smash badminton', 'smash sports'], (1.32, 103.89)),
    ('racket_sports', 'Racket Sports Centre', 'Private', ['racket sports', 'racquet sports'], (1.34, 103.8)),
    ('t3_sports', 'T3 Sports Hall', 'Private', ['t3 sports', 't3 hall'], (1.36, 103.99)),
    ('bliss', 'Bliss Badminton', 'Private', ['bliss badminton'], (1.33, 103.86)),
]

REGIONS = sorted({region for _, _, region, _, _ in VENUES})

BY_SLUG = {slug: (name, region, coords) for slug, name, region, _, coords in VENUES}

# Sorted longest-first so specific aliases win over substrings of themselves.
ALIAS_INDEX: list[tuple[str, str]] = sorted(
    ((alias.lower(), slug) for slug, _, _, aliases, _ in VENUES for alias in aliases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def display_name(slug: str) -> str:
    entry = BY_SLUG.get(slug)
    return entry[0] if entry else slug


def region_of(slug: str) -> str | None:
    entry = BY_SLUG.get(slug)
    return entry[1] if entry else None


def coords_of(slug: str) -> tuple[float, float] | None:
    entry = BY_SLUG.get(slug)
    return entry[2] if entry else None
