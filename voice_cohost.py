"""
Tillu Voice Channel AI Co-Host Engine
Connects to Discord voice channels, synthesizes natural Indian Hinglish speech using edge-tts (hi-IN-MadhurNeural),
and speaks live roasts, stream hype, and conversational commentary.
"""

import os
import asyncio
import logging
import tempfile
from typing import Optional, Dict, Tuple, List
import discord
import edge_tts

logger = logging.getLogger("TilluVoiceCoHost")

DEFAULT_VOICE = "hi-IN-MadhurNeural"  # Natural male Hindi/Indian English voice
ALT_VOICE = "hi-IN-SwaraNeural"      # Female Hindi voice alternative

class VoiceCoHost:
    def __init__(self):
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.is_speaking: Dict[int, bool] = {}
        self.speech_queues: Dict[int, asyncio.Queue] = {}

    def get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        return self.voice_clients.get(guild_id)

    async def join_channel(self, channel: discord.VoiceChannel) -> Tuple[bool, str, Optional[discord.VoiceClient]]:
        """Joins or moves to the specified voice channel."""
        guild = channel.guild
        vc = guild.voice_client

        try:
            if vc:
                if vc.channel.id == channel.id:
                    self.voice_clients[guild.id] = vc
                    return True, f"Pehle se hi **{channel.name}** me baitha hoon!", vc
                await vc.move_to(channel)
                self.voice_clients[guild.id] = vc
                return True, f"Move ho gaya **{channel.name}** me!", vc
            else:
                vc = await channel.connect(timeout=15.0, reconnect=True)
                self.voice_clients[guild.id] = vc
                return True, f"Join kar liya **{channel.name}**! Mic check 1, 2, 3!", vc
        except Exception as e:
            logger.error(f"[Voice Join Error] {e}")
            return False, f"Voice connect nahi ho paya: {e}", None

    async def leave_channel(self, guild: discord.Guild) -> Tuple[bool, str]:
        """Disconnects cleanly from the guild's voice channel."""
        vc = guild.voice_client or self.voice_clients.get(guild.id)
        if not vc:
            return False, "Main kisi voice channel me nahi hoon bhai!"

        try:
            if vc.is_playing():
                vc.stop()
            await vc.disconnect(force=True)
            self.voice_clients.pop(guild.id, None)
            self.is_speaking[guild.id] = False
            return True, "Voice channel se disconnect ho gaya! Milte hain stream pe!"
        except Exception as e:
            logger.error(f"[Voice Leave Error] {e}")
            return False, f"Disconnect error: {e}"

    async def synthesize_speech(self, text: str, voice: str = DEFAULT_VOICE) -> Optional[str]:
        """Synthesizes text to an MP3 file using Microsoft Edge TTS."""
        try:
            fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="tillu_vc_")
            os.close(fd)
            communicate = edge_tts.Communicate(text, voice, rate="+5%", pitch="+0Hz")
            await communicate.save(temp_path)
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
            return None
        except Exception as e:
            logger.error(f"[TTS Synthesize Error] {e}")
            return None

    async def play_audio_file(self, guild: discord.Guild, file_path: str):
        """Plays the audio file in the voice channel and deletes the temp file when done."""
        vc = guild.voice_client or self.voice_clients.get(guild.id)
        if not vc or not vc.is_connected():
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        def _after_play(err):
            if err:
                logger.error(f"[Voice Playback Error] {err}")
            self.is_speaking[guild.id] = False
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

        try:
            self.is_speaking[guild.id] = True
            source = discord.FFmpegPCMAudio(file_path)
            vc.play(source, after=_after_play)
        except Exception as e:
            logger.error(f"[play_audio_file Error] {e}")
            self.is_speaking[guild.id] = False
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    async def speak_text(self, guild: discord.Guild, text: str, voice: str = DEFAULT_VOICE) -> Tuple[bool, str]:
        """Synthesizes and speaks text out loud in the voice channel."""
        vc = guild.voice_client or self.voice_clients.get(guild.id)
        if not vc or not vc.is_connected():
            return False, "Tillu abhi voice channel me nahi hai! `/joinvc` se bulayein."

        # Wait if currently speaking
        wait_cycles = 0
        while vc.is_playing() and wait_cycles < 20:
            await asyncio.sleep(0.5)
            wait_cycles += 1

        audio_file = await self.synthesize_speech(text, voice)
        if not audio_file:
            return False, "TTS audio generate karne me dikkat aayi!"

        await self.play_audio_file(guild, audio_file)
        return True, "Audio bol raha hoon VC me!"

    async def speak_roast(self, guild: discord.Guild, target_name: str) -> Tuple[bool, str, str]:
        """Picks a savage/funny roast from meme_engine and speaks it in voice channel."""
        from meme_engine import meme_engine
        memes = meme_engine.pick_fresh_memes("savage", count=1)
        meme_quote = memes[0]["text"] if memes else "Bhai tu chup raha kar!"
        opener = meme_engine.get_fresh_opener()
        roast_script = f"{opener} {target_name}, dhyan se sun! {meme_quote}"
        
        ok, msg = await self.speak_text(guild, roast_script)
        return ok, msg, roast_script

    async def speak_hype(self, guild: discord.Guild, streamer_name: str = "Aalu") -> Tuple[bool, str, str]:
        """Speaks stream clutch/hype commentary in voice channel."""
        from meme_engine import meme_engine
        memes = meme_engine.pick_fresh_memes("gaming", count=1)
        gaming_quote = memes[0]["text"] if memes else "Patt se headshot!"
        opener = meme_engine.get_fresh_opener()
        hype_script = f"Are {opener} Sab log dhyan do! {streamer_name} ne clutch kar diya! {gaming_quote} Full hype in chat!"

        ok, msg = await self.speak_text(guild, hype_script)
        return ok, msg, hype_script

# Global Singleton
voice_cohost = VoiceCoHost()
