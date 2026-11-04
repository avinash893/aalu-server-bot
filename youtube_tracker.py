"""
Tillu YouTube Live Timing & Stream Status Tracker
Fetches owner live broadcast status, scheduled stream timings, and stream metadata
via YouTube Data API v3 and live channel endpoint parsing.
"""

import os
import re
import json
import time
import logging
import datetime
from typing import Dict, Any, Optional
import aiohttp
import requests

logger = logging.getLogger("TilluYouTubeTracker")

class YouTubeTracker:
    def __init__(self, channel_id: Optional[str] = None, handle: Optional[str] = None, api_key: Optional[str] = None):
        self.channel_id = channel_id or os.environ.get("YOUTUBE_CHANNEL_ID", "UCS__Q82af4iKTPDwDQ19UZQ")
        self.handle = handle or os.environ.get("YOUTUBE_HANDLE", "@AALU_CHIPAS")
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        self.cache: Dict[str, Any] = {}
        self.cache_ttl = 90  # cache 90 seconds to avoid spamming
        self.last_fetch = 0.0

    async def get_live_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch whether the channel is currently live or has an upcoming stream scheduled."""
        now = time.time()
        if not force_refresh and self.cache and (now - self.last_fetch < self.cache_ttl):
            return self.cache

        result = {
            "status": "offline",           # 'live', 'upcoming', or 'offline'
            "is_live": False,
            "title": "",
            "video_id": "",
            "url": f"https://www.youtube.com/{self.handle}/live",
            "viewers": 0,
            "scheduled_start_iso": None,
            "scheduled_start_formatted": None,
            "time_until_stream": None,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "channel_title": "AALU_CHIPAS",
            "channel_url": f"https://www.youtube.com/{self.handle}"
        }

        # Method 1: Try via YouTube live HTML endpoint
        try:
            live_url = f"https://www.youtube.com/{self.handle}/live"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(live_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        parsed = self._parse_youtube_html(html)
                        if parsed:
                            result.update(parsed)
                            self.cache = result
                            self.last_fetch = now
                            return result
        except Exception as e:
            logger.warning(f"[YouTubeTracker] HTML live parse failed: {e}")

        # Method 2: Try via YouTube Data API v3 if API key is valid
        if self.api_key and self.channel_id:
            try:
                api_result = await self._fetch_via_api()
                if api_result:
                    result.update(api_result)
                    self.cache = result
                    self.last_fetch = now
                    return result
            except Exception as e:
                logger.warning(f"[YouTubeTracker] API live fetch failed: {e}")

        self.cache = result
        self.last_fetch = now
        return result

    def _parse_youtube_html(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract live status and scheduled start times from YouTube ytInitialData."""
        try:
            # Check for canonical video ID
            vid_match = re.search(r'\"videoId\":\"([a-zA-Z0-9_-]{11})\"', html)
            video_id = vid_match.group(1) if vid_match else ""

            # Check if currently live
            is_live = False
            title = ""
            scheduled_start_iso = None

            if '"isLive":true' in html or '"isLiveContent":true' in html:
                # Distinguish between active live stream and upcoming premiere/scheduled live
                if '"liveStreamability":' in html or '"isLiveNow":true' in html:
                    is_live = True

            # Extract title
            title_match = re.search(r'\"title\":\{\"runs\":\[\{\"text\":\"(.*?)\"\}\]\}', html)
            if not title_match:
                title_match = re.search(r'\"videoDetails\":\{.*?\"title\":\"(.*?)\"', html)
            if title_match:
                title = title_match.group(1).encode('utf-8').decode('unicode_escape', errors='ignore')

            # Extract scheduled start time if upcoming
            start_match = re.search(r'\"scheduledStartTime\":\"([0-9]+)\"', html)
            if start_match:
                ts = int(start_match.group(1))
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                scheduled_start_iso = dt.isoformat()

            # Viewers
            viewers = 0
            view_match = re.search(r'\"viewCount\":\{\"runs\":\[\{\"text\":\"([\d,]+)\"\}', html)
            if view_match:
                viewers = int(view_match.group(1).replace(",", ""))

            time_until_stream = None
            scheduled_formatted = None
            if scheduled_start_iso:
                scheduled_dt = datetime.datetime.fromisoformat(scheduled_start_iso)
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                diff = scheduled_dt - now_dt
                # Convert to IST (UTC +5:30)
                ist_offset = datetime.timedelta(hours=5, minutes=30)
                ist_dt = scheduled_dt + ist_offset
                scheduled_formatted = ist_dt.strftime("%d %b, %I:%M %p IST")

                if diff.total_seconds() > 0:
                    hours, rem = divmod(int(diff.total_seconds()), 3600)
                    minutes, _ = divmod(rem, 60)
                    if hours > 0:
                        time_until_stream = f"{hours} ghante {minutes} minute me"
                    else:
                        time_until_stream = f"{minutes} minute me"
                else:
                    time_until_stream = "Abhi shuru hone wala hai!"

            status = "live" if is_live else ("upcoming" if scheduled_start_iso else "offline")

            return {
                "status": status,
                "is_live": is_live,
                "title": title or "AALU_CHIPAS Stream",
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else f"https://www.youtube.com/{self.handle}/live",
                "viewers": viewers,
                "scheduled_start_iso": scheduled_start_iso,
                "scheduled_start_formatted": scheduled_formatted,
                "time_until_stream": time_until_stream
            }
        except Exception as e:
            logger.error(f"Error parsing YouTube HTML: {e}")
            return None

    async def _fetch_via_api(self) -> Optional[Dict[str, Any]]:
        """Fallback to official YouTube Data API v3 search endpoint."""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": self.channel_id,
            "eventType": "live",
            "type": "video",
            "key": self.api_key
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        vid = item.get("id", {}).get("videoId", "")
                        snippet = item.get("snippet", {})
                        return {
                            "status": "live",
                            "is_live": True,
                            "title": snippet.get("title", "Live Stream"),
                            "video_id": vid,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "channel_title": snippet.get("channelTitle", "AALU_CHIPAS")
                        }

        # Check for upcoming streams if not live
        params["eventType"] = "upcoming"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        vid = item.get("id", {}).get("videoId", "")
                        snippet = item.get("snippet", {})
                        return {
                            "status": "upcoming",
                            "is_live": False,
                            "title": snippet.get("title", "Upcoming Stream"),
                            "video_id": vid,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "channel_title": snippet.get("channelTitle", "AALU_CHIPAS")
                        }
        return None

    def format_timing_reply(self, data: Dict[str, Any], mood: str = "witty") -> str:
        """Format a personalized Hinglish response based on current live status and mood."""
        status = data.get("status", "offline")
        url = data.get("url", f"https://www.youtube.com/{self.handle}/live")
        title = data.get("title", "Stream")

        if status == "live":
            viewers = data.get("viewers", 0)
            v_str = f" ({viewers} log dekh rahe hain)" if viewers else ""
            if mood == "sarcastic":
                return f"🔴 Aalu bhai abhi live baitha hai maje se! Stream: \"{title}\"{v_str}\nTum yahan chat me timepass kar rahe ho, jaldi join karo: {url}"
            elif mood == "sad_sarcastic":
                return f"🔴 Aalu live chala gaya aur mujhe yahan bot bana ke chhod diya... 🥲\nStream: \"{title}\"\nDekh lo tum bhi jaake: {url}"
            else:
                return f"🔴 **Aalu abhi LIVE hai!**\n🎮 **Title:** {title}{v_str}\n📺 **Link:** {url}\nChalo sab log stream pe aao!"

        elif status == "upcoming":
            timing = data.get("scheduled_start_formatted") or "Jald hi"
            countdown = data.get("time_until_stream")
            c_str = f" ({countdown})" if countdown else ""
            if mood == "sarcastic":
                return f"⏰ Agli stream ka schedule lag chuka hai babu!\n📅 **Timing:** {timing}{c_str}\nTitle: \"{title}\"\nPopcorn taiyar rakhna, late mat hona: {url}"
            elif mood == "sad_sarcastic":
                return f"⏰ Stream schedule ho gayi: {timing}{c_str}. Tab tak mere paas tum logo ke ajeeb sawal sunne ke alawa koi kaam nahi hai... 🙃\nLink: {url}"
            else:
                return f"⏰ **Next Stream Scheduled!**\n📅 **Timing:** {timing}{c_str}\n🎮 **Title:** {title}\n🔔 Reminder set kar lo: {url}"

        else:
            if mood == "sarcastic":
                return f"😴 Abhi koi live stream schedule nahi hai bhai! Aalu aaram farma raha hai ya content plan kar raha hai. Raat ke time notification check karte rehna ya channel dekh lo: {data.get('channel_url')}"
            elif mood == "sad_sarcastic":
                return f"💤 Na live hai, na schedule hai... bas main akela yahan server pe pehra de raha hoon. Notification on rakho: {data.get('channel_url')}"
            else:
                return f"📺 Abhi Aalu live nahi hai aur koi upcoming stream scheduled nahi hai. Streams usually shaam/raat ko hoti hain! Notification bell on rakho: {data.get('channel_url')} 🔔"
