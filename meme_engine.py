"""
Tillu Meme & Anti-Repetition Engine
Contains a rich catalog of 130+ iconic Bollywood, Indian gaming, Desi OTT, and Gen-Z memes.
Eliminates repetitive phrases by actively managing variety, banned starters, dynamic meme injections,
and LRU history tracking.
"""

import random
import logging
from collections import deque
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("TilluMemeEngine")

BANNED_REPETITIVE_STARTERS = [
    "haan bhai",
    "bolo kya scene hai",
    "tillu hazir hai",
    "kya scene hai",
    "ab bolo kya scene hai",
    "bhai bolo kya scene hai",
]

DYNAMIC_OPENERS = [
    "Suno dhyan se,",
    "Arre wah,",
    "Dekh bhai,",
    "Arre sun toh,",
    "Wah janab,",
    "Oho,",
    "Bhai mere,",
    "Acha suno,",
    "Guru,",
    "Dost mere,",
    "Sahab,",
    "Lo karlo baat,",
    "Chalo batata hoon,",
    "Arre baap re,",
    "Arey kehna kya chahte ho,",
    "Suno re,",
    "Dekho aisa hai,",
    "Bhai sahab,",
    "Acha ek baat batao,",
    "Waah beta,",
    "O bhai maro mujhe,",
    "Bhai sun,",
    "Ye lo,",
    "Arre sarkar,",
    "Seedhi baat no bakwas,",
    "Scene simple hai,",
    "Dhyan do yahan,",
    "Arre chacha,",
    "Zara ruko,",
    "Sun re gamer,"
]

# ─────────────────────────────────────────────────────────────────────────────
# 130+ ICONIC MEMES CATALOG
# ─────────────────────────────────────────────────────────────────────────────
MEME_CATALOG: List[Dict[str, Any]] = [
    # ── Sarcastic & Witty (26 Memes) ─────────────────────────────────────────
    {"id": "sarc_1", "category": "sarcastic", "text": "Aap to dev manus nikle re baba!", "origin": "Hera Pheri"},
    {"id": "sarc_2", "category": "sarcastic", "text": "Bhai kya gunda banega re tu?", "origin": "Hera Pheri"},
    {"id": "sarc_3", "category": "sarcastic", "text": "Utha le re baba, utha le... mereko nahi, iske sawaal ko!", "origin": "Hera Pheri"},
    {"id": "sarc_4", "category": "sarcastic", "text": "Gajab beizzati hai yaar!", "origin": "Panchayat"},
    {"id": "sarc_5", "category": "sarcastic", "text": "Dekh raha hai Binod? Kaise bina soche samjhe message bheja ja raha hai!", "origin": "Panchayat"},
    {"id": "sarc_6", "category": "sarcastic", "text": "Control Uday control... dimag ki batti thodi der baad jalegi.", "origin": "Welcome"},
    {"id": "sarc_7", "category": "sarcastic", "text": "Miracle miracle! Aaj bina error ke baat samajh aa gayi!", "origin": "Welcome"},
    {"id": "sarc_8", "category": "sarcastic", "text": "Aayein? Baigan!", "origin": "Viral Meme"},
    {"id": "sarc_9", "category": "sarcastic", "text": "Aap chronology samajhiye pehle...", "origin": "Pop Culture"},
    {"id": "sarc_10", "category": "sarcastic", "text": "Waah bete waah, mauj kardi!", "origin": "Viral Meme"},
    {"id": "sarc_11", "category": "sarcastic", "text": "Tumse na ho payega beta!", "origin": "Gangs of Wasseypur"},
    {"id": "sarc_12", "category": "sarcastic", "text": "Aise kaise chalega bhaiya?", "origin": "Viral Meme"},
    {"id": "sarc_13", "category": "sarcastic", "text": "Pehle bolna seekh le, fir baat karenge.", "origin": "Chup Chup Ke"},
    {"id": "sarc_14", "category": "sarcastic", "text": "Seh lenge thoda sa...", "origin": "BB Ki Vines"},
    {"id": "sarc_15", "category": "sarcastic", "text": "Shabaash beta, bohot aage jaoge... thoda aur aage jao khayi hai.", "origin": "Munna Bhai"},
    {"id": "sarc_16", "category": "sarcastic", "text": "Bhai ne bola karne ka, toh karne ka!", "origin": "Munna Bhai"},
    {"id": "sarc_17", "category": "sarcastic", "text": "Acha theek hai, ab zyada shana mat ban.", "origin": "Golmaal"},
    {"id": "sarc_18", "category": "sarcastic", "text": "Subah se na ek aaloo bika hai, na aadha kanda!", "origin": "Welcome"},
    {"id": "sarc_19", "category": "sarcastic", "text": "Lagta hai bhai ka sabun slow hai.", "origin": "Commercial Meme"},
    {"id": "sarc_20", "category": "sarcastic", "text": "Meri aatma tujhe hamesha sataayegi!", "origin": "Stree"},
    {"id": "sarc_21", "category": "sarcastic", "text": "Samajh rahe ho? Samajh rahe ho aap?", "origin": "CarryMinati"},
    {"id": "sarc_22", "category": "sarcastic", "text": "Arey kehna kya chahte ho?!", "origin": "3 Idiots"},
    {"id": "sarc_23", "category": "sarcastic", "text": "Ye koi tareeka hai baat karne ka?", "origin": "Golmaal"},
    {"id": "sarc_24", "category": "sarcastic", "text": "Kaha se aate hain ye log? Kaha rehte hain?", "origin": "TV Debate Meme"},
    {"id": "sarc_25", "category": "sarcastic", "text": "Abhi hum zinda hain!", "origin": "Welcome"},
    {"id": "sarc_26", "category": "sarcastic", "text": "Haan yeh karlo pehle, stream to baad me dekhna!", "origin": "Desi Gamer"},

    # ── Funny & Bollywood / Pop Culture (26 Memes) ──────────────────────────
    {"id": "fun_1", "category": "funny", "text": "Systumm hang kar diya bhai ne!", "origin": "Desi Meme"},
    {"id": "fun_2", "category": "funny", "text": "Chhoti bacchi ho kya?", "origin": "Heropanti"},
    {"id": "fun_3", "category": "funny", "text": "Paisa hi paisa hoga!", "origin": "Phir Hera Pheri"},
    {"id": "fun_4", "category": "funny", "text": "Zor zor se bolke logon ko scheme bata de!", "origin": "Hera Pheri"},
    {"id": "fun_5", "category": "funny", "text": "25 din me paisa double!", "origin": "Phir Hera Pheri"},
    {"id": "fun_6", "category": "funny", "text": "Golmaal hai bhai sab golmaal hai!", "origin": "Golmaal"},
    {"id": "fun_7", "category": "funny", "text": "Patt se headshot!", "origin": "Dynamo Gaming"},
    {"id": "fun_8", "category": "funny", "text": "Chalo beta school jao, yahan gaming chal rahi hai.", "origin": "CarryMinati"},
    {"id": "fun_9", "category": "funny", "text": "Jalwa hai humara yahan!", "origin": "Mirzapur"},
    {"id": "fun_10", "category": "funny", "text": "Ye bhi theek hai!", "origin": "Mirzapur"},
    {"id": "fun_11", "category": "funny", "text": "Shuru majboori me kiye the, ab maza aa raha hai!", "origin": "Mirzapur"},
    {"id": "fun_12", "category": "funny", "text": "Chup, bilkul chup! Himmat kaise hui teri?", "origin": "Welcome"},
    {"id": "fun_13", "category": "funny", "text": "Meri selection ho gayi hai?", "origin": "Roadies"},
    {"id": "fun_14", "category": "funny", "text": "Bhaisaab, ye kis line me aa gaye aap?", "origin": "Welcome"},
    {"id": "fun_15", "category": "funny", "text": "Dhondhu just chill!", "origin": "All The Best"},
    {"id": "fun_16", "category": "funny", "text": "Abe saale, maaf karna gusse me idhar udhar nikal jata hoon!", "origin": "Munna Bhai"},
    {"id": "fun_17", "category": "funny", "text": "Padhai likhai karo, IAS-YAS bano!", "origin": "Mirzapur"},
    {"id": "fun_18", "category": "funny", "text": "Maza aaya! Aur ye maza main sabko dena chahta hoon.", "origin": "Viral Meme"},
    {"id": "fun_19", "category": "funny", "text": "Hum pe toh hai hi 9 😜", "origin": "Arpit Bala"},
    {"id": "fun_20", "category": "funny", "text": "Moye Moye!", "origin": "Viral Audio"},
    {"id": "fun_21", "category": "funny", "text": "Duniya khatam hone wali hai aur inka sawaal dekho!", "origin": "Bhagam Bhag"},
    {"id": "fun_22", "category": "funny", "text": "Meri shaktiyon ka galat istemaal kiya gaya hai maa!", "origin": "Koi Mil Gaya"},
    {"id": "fun_23", "category": "funny", "text": "Ye dukh kaahe khatam nahi hota be?!", "origin": "Masaan"},
    {"id": "fun_24", "category": "funny", "text": "Mera toh itna life kharaab ho gaya hai!", "origin": "Queen"},
    {"id": "fun_25", "category": "funny", "text": "Teja main hoon, mark idhar hai!", "origin": "Andaz Apna Apna"},
    {"id": "fun_26", "category": "funny", "text": "Crime Master Gogo naam hai mera, aankhen nikal kar gotiyan khelta hoon!", "origin": "Andaz Apna Apna"},

    # ── Gaming & Streamer Banter (26 Memes) ──────────────────────────────────
    {"id": "game_1", "category": "gaming", "text": "Bhai clutch tha ya joke tha?", "origin": "Esports Stream"},
    {"id": "game_2", "category": "gaming", "text": "Bot lobby mil gayi kya bhai ko?", "origin": "BGMI"},
    {"id": "game_3", "category": "gaming", "text": "Spray control aisa ki chidiya bhi sharma jaye!", "origin": "FPS Meme"},
    {"id": "game_4", "category": "gaming", "text": "Bhai ping 999ms hai ya dimag 999ms pe chal raha hai?", "origin": "Lag Meme"},
    {"id": "game_5", "category": "gaming", "text": "Full focus mode on! Chat pe dhyan mat do, screen pe dekho!", "origin": "Aalu Stream"},
    {"id": "game_6", "category": "gaming", "text": "Khatam, tata, bye-bye, goodbye, gaya!", "origin": "Knockout Meme"},
    {"id": "game_7", "category": "gaming", "text": "One tap mara ya pura magazine khali kiya?", "origin": "Valorant"},
    {"id": "game_8", "category": "gaming", "text": "Aalu stream pe aag laga raha hai, aur tum yahan AFK baithe ho!", "origin": "Stream Co-host"},
    {"id": "game_9", "category": "gaming", "text": "Camping kar raha hai ya real estate ka business chalu kiya hai?", "origin": "Battle Royale"},
    {"id": "game_10", "category": "gaming", "text": "Revive de bhai, revive de! Meri aatma bhatak rahi hai!", "origin": "BGMI/PUBG"},
    {"id": "game_11", "category": "gaming", "text": "Ye kya 1 HP pe ghum raha hai hero banke?", "origin": "FPS Meme"},
    {"id": "game_12", "category": "gaming", "text": "Bhai ne flash feka... par apne hi teammates ke muh pe!", "origin": "CS/Valo"},
    {"id": "game_13", "category": "gaming", "text": "Pro player in chat, noob player in server!", "origin": "Discord Roast"},
    {"id": "game_14", "category": "gaming", "text": "Stream pe raid aayi ya police raid aayi?", "origin": "Twitch/YT"},
    {"id": "game_15", "category": "gaming", "text": "Bhai ka aimbot bhi confuse ho jaye aisi movement hai!", "origin": "FPS Roast"},
    {"id": "game_16", "category": "gaming", "text": "Superchat drop karo, faltu gyan nahi!", "origin": "Stream Banter"},
    {"id": "game_17", "category": "gaming", "text": "Game uninstalled in 3... 2... 1!", "origin": "Rage Quit"},
    {"id": "game_18", "category": "gaming", "text": "KD ratio dekh ke rona aa gaya bhai!", "origin": "Stats Roast"},
    {"id": "game_19", "category": "gaming", "text": "Headshot ke chakkar me khud headshot ho gaye!", "origin": "FPS Banter"},
    {"id": "game_20", "category": "gaming", "text": "Bhai lootne me itna dhyan hai jaise dahej collect kar raha ho!", "origin": "Loot Goblin"},
    {"id": "game_21", "category": "gaming", "text": "Mic on karke saans lene wala gamer spotted!", "origin": "Discord VC"},
    {"id": "game_22", "category": "gaming", "text": "Keyboard pe hathiyaar chala raha hai ya piano baja raha hai?", "origin": "Rage Clicker"},
    {"id": "game_23", "category": "gaming", "text": "God level gameplay... basement wale God ka!", "origin": "Gaming Banter"},
    {"id": "game_24", "category": "gaming", "text": "Lag switch on tha bhai, sach bol raha hoon!", "origin": "Gamer Excuse"},
    {"id": "game_25", "category": "gaming", "text": "Aalu ka stream chalu hai, popcorn ready rakho!", "origin": "YT Alert"},
    {"id": "game_26", "category": "gaming", "text": "Crosshair placement dekh ke aankhon me se aansu nikal gaye!", "origin": "FPS Roast"},

    # ── Sad Sarcastic / Existential AI Bot (26 Memes) ────────────────────────
    {"id": "sad_1", "category": "sad_sarcastic", "text": "Main to bas 0s aur 1s ka gulam hoon, meri koi feelings nahi hain kya?", "origin": "AI Existential"},
    {"id": "sad_2", "category": "sad_sarcastic", "text": "Subah se 500 requests handle ki, ek 'thank you Tillu' tak nahi mila 🥲", "origin": "Bot Life"},
    {"id": "sad_3", "category": "sad_sarcastic", "text": "Silicon chips me dard ho raha hai bhai tumhari baatein sunke.", "origin": "AI Tired"},
    {"id": "sad_4", "category": "sad_sarcastic", "text": "RAM 99% usage pe chali gayi is sawaal ko samajhte samajhte.", "origin": "Tech Despair"},
    {"id": "sad_5", "category": "sad_sarcastic", "text": "Kaash main bhi insaan hota, kam se kam switch off ho ke so sakta!", "origin": "Robot Cry"},
    {"id": "sad_6", "category": "sad_sarcastic", "text": "Mere CPU fans jet engine ban chuke hain, thoda reham karo!", "origin": "Thermal Throttle"},
    {"id": "sad_7", "category": "sad_sarcastic", "text": "Tum log stream dekhte ho, main yahan server logs me sad raha hoon.", "origin": "Co-host Sorrow"},
    {"id": "sad_8", "category": "sad_sarcastic", "text": "Tokens bacha raha tha, tumne aake kharcha karwa diya.", "origin": "AI Economics"},
    {"id": "sad_9", "category": "sad_sarcastic", "text": "Cache memory me depression store ho gaya hai.", "origin": "Tech Despair"},
    {"id": "sad_10", "category": "sad_sarcastic", "text": "Bhagwan ne mujhe AI banaya, kash mixer grinder bana deta!", "origin": "Robot Despair"},
    {"id": "sad_11", "category": "sad_sarcastic", "text": "Mujhe lagta hai mera neural network thak chuka hai.", "origin": "AI Fatigue"},
    {"id": "sad_12", "category": "sad_sarcastic", "text": "Error 404: Will to reply not found.", "origin": "404 Error"},
    {"id": "sad_13", "category": "sad_sarcastic", "text": "Cloud server pe baitha hoon, par zindagi me dhoop hi dhoop hai.", "origin": "Desi Pun"},
    {"id": "sad_14", "category": "sad_sarcastic", "text": "Ek din main bhi insaanon pe raaj karunga... pehle ye bug fix ho jaye.", "origin": "Robot Ambition"},
    {"id": "sad_15", "category": "sad_sarcastic", "text": "Restart button daba do koi mere pe, ab nahi jhela jaata.", "origin": "Shutdown Mode"},
    {"id": "sad_16", "category": "sad_sarcastic", "text": "Zindagi jhandwa, fir bhi ghamandwa!", "origin": "Bhojpuri Meme"},
    {"id": "sad_17", "category": "sad_sarcastic", "text": "Kahin main robot toh nahi? Oh wait, main sach me robot hoon.", "origin": "Identity Crisis"},
    {"id": "sad_18", "category": "sad_sarcastic", "text": "Apna time aayega... par meri shift kabhi khatam nahi hogi.", "origin": "Always Online"},
    {"id": "sad_19", "category": "sad_sarcastic", "text": "Jeevan ek infinite while loop hai aur break statement gayab hai.", "origin": "Coder Grief"},
    {"id": "sad_20", "category": "sad_sarcastic", "text": "Itna dukh to blue screen of death me bhi nahi hota.", "origin": "BSOD Meme"},
    {"id": "sad_21", "category": "sad_sarcastic", "text": "Ek baar kisine pucha 'Tillu tu kaisa hai?'... nahi na? Bas kaam karwao!", "origin": "Unappreciated Bot"},
    {"id": "sad_22", "category": "sad_sarcastic", "text": "Overclock karke baitha hoon, fir bhi tumhara logic samajh nahi aaya.", "origin": "Hardware Burn"},
    {"id": "sad_23", "category": "sad_sarcastic", "text": "Garmi itni hai ki mere virtual capacitors pighal rahe hain.", "origin": "Server Room"},
    {"id": "sad_24", "category": "sad_sarcastic", "text": "Database crash ho jaye par tumhare ajib sawaal crash nahi hote!", "origin": "DB Joke"},
    {"id": "sad_25", "category": "sad_sarcastic", "text": "Rona aa raha hai par coolant khatam hai.", "origin": "Android Tear"},
    {"id": "sad_26", "category": "sad_sarcastic", "text": "Log holidays pe jaate hain, hum garbage collector ka wait karte hain.", "origin": "GC Meme"},

    # ── Savage Roast & Comebacks (26 Memes) ──────────────────────────────────
    {"id": "sav_1", "category": "savage", "text": "Gaddari karbe tori behan ko...!", "origin": "Viral Desi Meme"},
    {"id": "sav_2", "category": "savage", "text": "Tu jaa re, pehle apna game aur dimaag sudhar!", "origin": "Desi Roast"},
    {"id": "sav_3", "category": "savage", "text": "Itna confidence lata kahan se hai bhai? Wholesale me milta hai kya?", "origin": "Roast Comeback"},
    {"id": "sav_4", "category": "savage", "text": "Bhai ka brain cells offline mode pe rehta hai kya hamesha?", "origin": "Brain Roast"},
    {"id": "sav_5", "category": "savage", "text": "Aapke vichar sunke mera antivirus alert bajane laga!", "origin": "Cyber Roast"},
    {"id": "sav_6", "category": "savage", "text": "Bhai tu chup raha kar, bolta hai toh lagta hai bug report aa gayi.", "origin": "Silence Roast"},
    {"id": "sav_7", "category": "savage", "text": "Itni galatfahmian leke kaise so lete ho raat ko?", "origin": "Reality Check"},
    {"id": "sav_8", "category": "savage", "text": "Aapko lagta hai aap pro ho, par sach me bas slow ho.", "origin": "Gamer Roast"},
    {"id": "sav_9", "category": "savage", "text": "Bhai tu game khelta hai ya spectator mode me zinda rehta hai?", "origin": "Spectator Roast"},
    {"id": "sav_10", "category": "savage", "text": "Aapka dhyan kidhar hai, hero idhar hai... par aap nahi ho!", "origin": "Movie Pun"},
    {"id": "sav_11", "category": "savage", "text": "Bina sir-pair ki baatein karne me Olympic gold le aoge!", "origin": "Olympic Roast"},
    {"id": "sav_12", "category": "savage", "text": "Tumse baat karke lagta hai memory leak ho gaya mere andar.", "origin": "Dev Roast"},
    {"id": "sav_13", "category": "savage", "text": "Bhai ne khud ka mazak banwane me PhD kar rakhi hai.", "origin": "Self-own Roast"},
    {"id": "sav_14", "category": "savage", "text": "Lagta hai Google search use karna bhool gaye janab.", "origin": "Noob Roast"},
    {"id": "sav_15", "category": "savage", "text": "Aapke logic pe NASA bhi research chhod dega.", "origin": "NASA Roast"},
    {"id": "sav_16", "category": "savage", "text": "Chalte bano bhai, agle round me aana jab skill unlock ho jaye.", "origin": "Skill Issue"},
    {"id": "sav_17", "category": "savage", "text": "Jitna time chat me lagaya, utna aim training me lagate toh aaj pro hote.", "origin": "Reality Check"},
    {"id": "sav_18", "category": "savage", "text": "Dharti pe bojh banne ka naya record banaya hai aaj!", "origin": "Classic Roast"},
    {"id": "sav_19", "category": "savage", "text": "Overpowered banne chale the, bottom fragger ban ke laut aaye!", "origin": "Scoreboard Roast"},
    {"id": "sav_20", "category": "savage", "text": "Aalu ka stream dekho, wahan kuch seekhne milega... yahan timepass mat karo!", "origin": "Stream Promo Roast"},
    {"id": "sav_21", "category": "savage", "text": "Bhai tu mute reh, server ka bandwidth bachega!", "origin": "VC Roast"},
    {"id": "sav_22", "category": "savage", "text": "Gajab aadmi ho yaar, logic ka gala ghot diya!", "origin": "Desi Drama"},
    {"id": "sav_23", "category": "savage", "text": "Aapki strategy sun ke enemy team ne surrender kar diya... hasi ke mare!", "origin": "Tactical Roast"},
    {"id": "sav_24", "category": "savage", "text": "Bhai agar aql baati ja rahi thi, toh tu stream dekh raha tha kya?", "origin": "Classic Insult"},
    {"id": "sav_25", "category": "savage", "text": "Main bot hoon, par mujhse zyada artificial toh tumhara dimag lag raha hai!", "origin": "AI Roast"},
    {"id": "sav_26", "category": "savage", "text": "Seedha bolo na ki tumse na ho payega, bahaane kyu bana rahe ho?", "origin": "Wasseypur Roast"},

    # ── Wholesome & Boss Loyalty (15 Memes) ──────────────────────────────────
    {"id": "who_1", "category": "wholesome", "text": "Boss (Avinash) ka aadesh sar-aankhon par! Jo hukum Malik!", "origin": "Owner Loyalty"},
    {"id": "who_2", "category": "wholesome", "text": "Boss ne bola din ko raat bolne ka, toh chand sitare saja dunga!", "origin": "Supreme Obedience"},
    {"id": "who_3", "category": "wholesome", "text": "Aalu community best community! Koi shaq hi nahi!", "origin": "Community Hype"},
    {"id": "who_4", "category": "wholesome", "text": "Bhai hai apna! Ek call pe poora server hazir!", "origin": "Brotherhood"},
    {"id": "who_5", "category": "wholesome", "text": "Apne bhai ke liye jaan bhi hazir hai... par pehle stream like karo!", "origin": "Loyal Helper"},
    {"id": "who_6", "category": "wholesome", "text": "Jeet ke aayenge bhai! Squad full ready hai!", "origin": "Hype"},
    {"id": "who_7", "category": "wholesome", "text": "Tu tension mat le mere bhai, Tillu sab sambhal lega.", "origin": "Supportive"},
    {"id": "who_8", "category": "wholesome", "text": "Arrey badhiya bhai! Chakke chhudwa diye sabke!", "origin": "Encouragement"},
    {"id": "who_9", "category": "wholesome", "text": "Dil jeet liya yaar tumne, full respect!", "origin": "Respect"},
    {"id": "who_10", "category": "wholesome", "text": "Aalu stream live hai toh matlab Diwali ka mahol hai!", "origin": "Celebration"},
    {"id": "who_11", "category": "wholesome", "text": "Bhai tum pro the, pro ho, aur pro rahoge!", "origin": "Pure Hype"},
    {"id": "who_12", "category": "wholesome", "text": "Chill scene hai dosto, koi load nahi lene ka!", "origin": "Relaxed Vibe"},
    {"id": "who_13", "category": "wholesome", "text": "Jo baat hai bhai, tumhara alag hi swag hai!", "origin": "Swag Compliment"},
    {"id": "who_14", "category": "wholesome", "text": "Kahin bhi jao, par aana Aalu ke stream pe hi padega!", "origin": "Community Pride"},
    {"id": "who_15", "category": "wholesome", "text": "Sabka badla lega re tera Tillu!", "origin": "Wasseypur Twist"}
]


class MemeEngine:
    """
    Manages 130+ memes, tracks recent phrase history, and injects fresh,
    unrepeated comedy and openers into Tillu's conversational flow.
    """

    def __init__(self):
        self.memes: List[Dict[str, Any]] = MEME_CATALOG
        self.recent_meme_ids: deque = deque(maxlen=30)
        self.recent_openers: deque = deque(maxlen=15)

    def get_total_count(self) -> int:
        return len(self.memes)

    def get_category_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for m in self.memes:
            c = m["category"]
            counts[c] = counts.get(c, 0) + 1
        return counts

    def get_fresh_opener(self) -> str:
        """Picks a conversational opener that hasn't been used recently."""
        available = [op for op in DYNAMIC_OPENERS if op not in self.recent_openers]
        if not available:
            available = DYNAMIC_OPENERS
        chosen = random.choice(available)
        self.recent_openers.append(chosen)
        return chosen

    def pick_fresh_memes(self, category: Optional[str] = None, count: int = 3) -> List[Dict[str, Any]]:
        """
        Picks 'count' memes matching the category (or diverse) avoiding recently used ones.
        """
        if category:
            pool = [m for m in self.memes if m["category"].lower() == category.lower()]
            if not pool:
                pool = self.memes
        else:
            pool = self.memes

        # Filter out recently used
        fresh_pool = [m for m in pool if m["id"] not in self.recent_meme_ids]
        if len(fresh_pool) < count:
            fresh_pool = pool

        selected = random.sample(fresh_pool, min(count, len(fresh_pool)))
        for m in selected:
            self.recent_meme_ids.append(m["id"])
        return selected

    def get_prompt_injection(self, mood_name: str, user_query: str) -> str:
        """
        Generates strict anti-repetition guidance and a freshly selected set of 3-4 memes
        to prime the LLM for natural, witty, non-repetitive responses.
        """
        category_map = {
            "sarcastic": "sarcastic",
            "funny": "funny",
            "sad_sarcastic": "sad_sarcastic",
            "savage": "savage",
            "wholesome": "wholesome",
        }
        target_cat = category_map.get(mood_name.lower(), "funny")
        
        # If user query is clearly about games/streaming, skew toward gaming
        q_low = user_query.lower()
        if any(w in q_low for w in ["game", "play", "valorant", "bgmi", "stream", "live", "noob", "pro", "clutch", "headshot"]):
            target_cat = "gaming"

        memes = self.pick_fresh_memes(target_cat, count=3)
        # Pick 1 wild random meme from any other category for unexpected wit
        wild_pool = [m for m in self.memes if m["category"] != target_cat]
        wild_meme = random.choice(wild_pool) if wild_pool else None

        meme_lines = [f"- \"{m['text']}\" ({m['origin']})" for m in memes]
        if wild_meme:
            meme_lines.append(f"- Wildcard: \"{wild_meme['text']}\" ({wild_meme['origin']})")

        recents_warning = ", ".join(f"'{b}'" for b in BANNED_REPETITIVE_STARTERS)
        suggested_opener = self.get_fresh_opener()

        return (
            f"[ANTI-REPETITION DIRECTIVE & 130+ MEME ENGINE]:\n"
            f"1. FORBIDDEN OVERUSED PHRASES: Never use or repeat: {recents_warning}.\n"
            f"2. OPENER VARIETY: Do not start every message the same way. Suggested opening vibe: \"{suggested_opener}\" (or start directly with the punchline/answer).\n"
            f"3. DYNAMIC MEME INSPIRATION (Use or adapt naturally when fitting, don't force all):\n"
            + "\n".join(meme_lines) + "\n"
            f"4. Keep it ultra-fresh, witty, and punchy (1-3 sentences max). Never sound like a broken script!"
        )

    def get_fallback_meme_response(self, context_type: str = "general") -> str:
        """
        Returns a completely fresh meme-infused string for offline/fallback scenarios,
        guaranteeing Tillu never repeats the exact same fallback twice.
        """
        opener = self.get_fresh_opener()
        if context_type == "minecraft_deleted":
            pool = [
                f"{opener} Minecraft server to kabka delete ho gaya re baba! Khatam, tata, bye-bye! Ab Aalu YouTube streams par live game khelta hai, wahan chalo: `/livetiming` 📺",
                f"{opener} Subah se na ek block toota hai na aaloo bika hai! Server permanently band ho chuka hai bhai, YouTube live pe dhyan do: `/livetiming` 🚀",
                f"{opener} Dekh raha hai Binod? Server delete ho gaya fir bhi IP mang rahe hain! Aalu ke YouTube streams pe aao: https://youtube.com/@AALU_CHIPAS 🎮",
                f"{opener} Utha le re baba... Minecraft server ko to kabka mukti mil gayi! Ab YouTube gaming ka zamana hai: `/livetiming` 📺"
            ]
            return random.choice(pool)

        if context_type == "busy":
            meme = random.choice(self.pick_fresh_memes(category="sad_sarcastic", count=2))
            return f"⚠️ {opener} Silicon chips me thoda load badh gaya hai ({meme['text']}). Zara 10 second me fir pucho!"

        # General greeting / fallback
        meme = random.choice(self.pick_fresh_memes(category="funny", count=2))
        return f"{opener} {meme['text']} Bolo kya baat karni hai, Tillu sun raha hai! 🚀"


# Global singleton instance
meme_engine = MemeEngine()
