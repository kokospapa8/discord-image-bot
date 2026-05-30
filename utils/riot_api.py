"""Riot Games API client — League of Legends match history."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

_ROUTING = "asia"   # KR, JP, OCE account + match routing
_PLATFORM = "kr"    # KR platform (summoner, rank)

_QUEUE_NAMES: dict[int, str] = {
    420: "솔랭",
    440: "자유랭",
    450: "칼바람",
    400: "일반",
    430: "일반",
    490: "빠른대전",
    700: "격전",
    1700: "아레나",
    1900: "URF",
}

_TIER_KO: dict[str, str] = {
    "IRON": "아이언", "BRONZE": "브론즈", "SILVER": "실버",
    "GOLD": "골드", "PLATINUM": "플래티넘", "EMERALD": "에메랄드",
    "DIAMOND": "다이아", "MASTER": "마스터", "GRANDMASTER": "그마",
    "CHALLENGER": "챌린저",
}


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    """'Name#Tag' → ('Name', 'Tag'). Raises ValueError if invalid."""
    riot_id = riot_id.strip()
    if "#" not in riot_id:
        raise ValueError(f"Riot ID 형식이 맞지 않아: '{riot_id}' (예: Hide#KR1)")
    name, tag = riot_id.rsplit("#", 1)
    return name.strip(), tag.strip()


async def _get(session: aiohttp.ClientSession, url: str, api_key: str, **params) -> dict | list:
    async with session.get(
        url,
        headers={"X-Riot-Token": api_key},
        params=params or None,
        timeout=aiohttp.ClientTimeout(total=8),
    ) as resp:
        if resp.status == 404:
            raise LookupError("404")
        if resp.status == 429:
            raise RuntimeError("Riot API 요청 한도 초과 — 잠시 후 다시 해줘 🫧")
        resp.raise_for_status()
        return await resp.json()


async def get_puuid(game_name: str, tag_line: str, api_key: str) -> str:
    url = f"https://{_ROUTING}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    async with aiohttp.ClientSession() as s:
        try:
            data = await _get(s, url, api_key)
        except LookupError:
            raise LookupError(f"'{game_name}#{tag_line}' 를 찾을 수 없어. Riot ID 확인해줘!")
    return data["puuid"]  # type: ignore[index]


async def _fetch_matches_parallel(
    puuid: str, count: int, api_key: str
) -> tuple[list[dict], list[dict]]:
    """Returns (match_details, rank_entries) fetched in parallel."""
    async with aiohttp.ClientSession() as s:
        # match IDs + rank in parallel
        match_ids_data, summoner_data = await asyncio.gather(
            _get(
                s,
                f"https://{_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids",
                api_key,
                count=count,
            ),
            _get(
                s,
                f"https://{_PLATFORM}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}",
                api_key,
            ),
            return_exceptions=True,
        )

        match_ids: list[str] = match_ids_data if isinstance(match_ids_data, list) else []

        # Rank
        rank_entries: list[dict] = []
        if isinstance(summoner_data, dict):
            try:
                rank_entries = await _get(  # type: ignore[assignment]
                    s,
                    f"https://{_PLATFORM}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_data['id']}",
                    api_key,
                )
            except Exception:
                pass

        # Match details in parallel
        if match_ids:
            results = await asyncio.gather(
                *[
                    _get(s, f"https://{_ROUTING}.api.riotgames.com/lol/match/v5/matches/{mid}", api_key)
                    for mid in match_ids
                ],
                return_exceptions=True,
            )
            match_details = [r for r in results if isinstance(r, dict)]
        else:
            match_details = []

    return match_details, rank_entries


def _format_rank(entries: list[dict]) -> str:
    solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
    if not solo:
        return "언랭"
    tier = _TIER_KO.get(solo["tier"], solo["tier"])
    rank = solo["rank"]
    lp = solo["leaguePoints"]
    wins = solo["wins"]
    losses = solo["losses"]
    total = wins + losses
    winrate = int(wins / total * 100) if total else 0
    return f"{tier} {rank} · {lp}LP · {wins}승 {losses}패 ({winrate}%)"


def _format_match(participant: dict, game_duration: int, queue_id: int) -> str:
    win = "✅" if participant["win"] else "❌"
    champ = participant["championName"]
    k, d, a = participant["kills"], participant["deaths"], participant["assists"]
    kda_val = (k + a) / max(d, 1)
    kda_str = f"{kda_val:.1f}"
    mins = game_duration // 60
    mode = _QUEUE_NAMES.get(queue_id, f"Q{queue_id}")
    return f"{win} {champ}  {k}/{d}/{a}  KDA {kda_str}  {mins}분  [{mode}]"


async def format_stats(riot_id: str, count: int, api_key: str) -> str:
    """Full pipeline: riot_id → formatted stats string for Claude."""
    try:
        game_name, tag_line = parse_riot_id(riot_id)
        puuid = await get_puuid(game_name, tag_line, api_key)
        matches, rank_entries = await _fetch_matches_parallel(puuid, count, api_key)
    except LookupError as exc:
        return str(exc)
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:
        log.exception("Riot API error")
        return f"전적 조회 중 오류 발생: {exc}"

    rank_str = _format_rank(rank_entries)

    if not matches:
        return f"[{riot_id}]\n랭크: {rank_str}\n\n최근 게임 기록이 없어."

    lines = [f"[{riot_id}]", f"솔랭: {rank_str}", f"\n최근 {len(matches)}게임"]
    wins = 0
    for m in matches:
        info = m.get("info", {})
        participants = info.get("participants", [])
        me = next((p for p in participants if p.get("puuid") == puuid), None)
        if me is None:
            continue
        if me["win"]:
            wins += 1
        lines.append(_format_match(me, info.get("gameDuration", 0), info.get("queueId", 0)))

    losses = len(matches) - wins
    lines[2] = f"\n최근 {len(matches)}게임  {wins}승 {losses}패"
    return "\n".join(lines)
