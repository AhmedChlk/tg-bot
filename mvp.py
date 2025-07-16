#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simple_inviter.py – Telegram scraper + inviter (single‑account, single‑proxy)

• Scrape les commentateurs du groupe‑discussion lié à CHANNEL_SOURCE
• Ajoute jusqu’à DAILY_QUOTA membres/jour dans CHANNEL_TARGET
• Historique posts + users dans state.json (anti‑doublon)
• Rejoint automatiquement un canal privé (+hash) si besoin
• Gère FloodWait, proxy HTTP/SOCKS, et tourne en boucle
"""
import os
import sys
import json
import time
import random
import logging
import datetime
import tempfile
import asyncio
import termios
import tty
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from telethon import events, errors
from telethon.tl.functions.channels import GetFullChannelRequest, InviteToChannelRequest
from telethon.tl.functions.messages import (
    GetDiscussionMessageRequest,
    ImportChatInviteRequest,
    GetHistoryRequest,
    SendReactionRequest,
)
from telethon.tl.types import ReactionEmoji
from telethon.tl.functions.channels import JoinChannelRequest

from opentele.api import API
from opentele.tl import TelegramClient as OTClient
from opentele.td import TDesktop
# ajoute en haut – après tes imports téléthon/opentele
from curl_cffi import requests as curl_requests
import datetime


# --------------------------------------------------------------------------- #
# 1. CONFIG                                                                   #
# --------------------------------------------------------------------------- #

load_dotenv()
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
SESSION  = os.getenv("SESSION_NAME", "session")
PHONE    = os.getenv("PHONE_NUMBER", "").strip() or None

CHANNEL_SRC    = os.getenv("CHANNEL_SOURCE", "").strip()
CHANNEL_TARGET = os.getenv("CHANNEL_TARGET", "").strip()

DAILY_QUOTA = 15  
SCRAP_LIMIT = 10 

DM_HOURLY = 3          # Max 5 DMs par heure
TOKEN_TIME = 720       # 1 token = 12 min
DELAY_BETWEEN_USERS = (900, 1200) # entre deux messages

SCRAPE_DELAY_MIN = 10
SCRAPE_DELAY_MAX = 15

tokens = DM_HOURLY
last_token = time.time()

GREETS = [
    "Hey {username} 👋, are you a Formula 1 fan?",
    "Hola {username} 😊, do you love Formula 1?",
    "Yo {username} 🙌, I’m crazy about Formula 1 too!",
    "Heyyy {username} 🚀, Formula 1 is life, right?",
    "Wassup {username} 😉, Formula 1 is the best sport ever!",
    "Heeey {username} 👋, do you follow Formula 1 races?",
    "Hey {username}! 🏎️ Big Formula 1 fan like me?",

]

INVITES = [
    "👉 Don’t miss out! Join the F1 action here: {link}",
    "📢 Exclusive access to F1 news & gossip: {link}",
    "🔥 Love Formula 1? Tap here now ➡ {link}",
    "🏎️ Get your F1 fix here 👉 {link}",
    "🔥 Discover the fastest updates on the grid: {link}",
    "🚀 Be part of the ultimate F1 fan zone: {link}",
    "💡 Your front-row seat to F1 starts here: {link}",

]


# configure le client HTTP utilisé pour des requêtes “secrètes” via le proxy
def http_get(url):
    return curl_requests.get(
        url,
        impersonate="chrome110",  # ou chrome119 etc., empreinte TLS-browser :contentReference[oaicite:1]{index=1}
        proxies={"https": f"http://{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}"}
    )


# Delais entre actions
DELAY_MIN, DELAY_MAX = 120, 300  
# ---- Logger simple --------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

def human_delay(min_sec=120, max_sec=300):  # 5 à 15 minutes
    delay = random.uniform(min_sec, max_sec)
    log.info("⏳ Pause humaine de %.2f sec", delay)
    return delay

def scrape_delay():
    return random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)

if not (API_ID and API_HASH and CHANNEL_SRC and CHANNEL_TARGET):
    print("❌ Vérifie .env (API_ID, API_HASH, CHANNEL_SOURCE, CHANNEL_TARGET)")
    sys.exit(1)



# --------------------------------------------------------------------------- #
# 2. ETAT PERSISTANT : state.json                                             #
# --------------------------------------------------------------------------- #
import json, datetime
from pathlib import Path

STATE_PATH = Path("state.json")

def init_state():
    return {
        "date": datetime.date.today().isoformat(),
        "invites_today": 0,
        "users": {}  # uid: {"username": str, "greeted": bool, "responded": bool, "invited": bool}
    }

def load_state():
    if STATE_PATH.exists():
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        data = init_state()
        save_state(data)
        return data

def save_state(data):
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

state = load_state()

def add_user(uid, username=None):
    if uid not in state["users"]:
        state["users"][uid] = {
            "username": username,
            "greeted": False,
            "responded": False,
            "invited": False
        }
        save_state(state)

def mark_greeted(uid):
    if uid in state["users"]:
        state["users"][uid]["greeted"] = True
        save_state(state)

def mark_responded(uid):
    if uid in state["users"]:
        state["users"][uid]["responded"] = True
        save_state(state)

def mark_invited(uid):
    if uid in state["users"]:
        state["users"][uid]["invited"] = True
        save_state(state)

state = load_state()

# --------------------------------------------------------------------------- #
# STATISTIQUES                                                          #
# --------------------------------------------------------------------------- #

def log_stats():
    total_users = len(state["users"])
    greeted = sum(1 for u in state["users"].values() if u.get("greeted"))
    invited = sum(1 for u in state["users"].values() if u.get("invited"))
    remaining = total_users - greeted

    log.info("📊 STATISTIQUES :")
    log.info(" • Total utilisateurs : %d", total_users)
    log.info(" • Greetés : %d", greeted)
    log.info(" • Invités : %d", invited)
    log.info(" • Restants : %d", remaining)
    log.info(" • Invites aujourd'hui : %d / %d", state["invites_today"], DAILY_QUOTA)

# --------------------------------------------------------------------------- #
# 3. OUTILS ASYNC                                                            #
# --------------------------------------------------------------------------- #

def rand_delay() -> float:
    return random.uniform(DELAY_MIN, DELAY_MAX)
async def safe_call(fn, *a, **k):
    """
    Appelle fn puis :
       • Dort si FloodWait
       • STOP immédiat si PeerFloodError (risque ban)
       • Renvoie False si privacy bloque
       • Renvoie None si erreur critique
    """
    while True:
        try:
            return await fn(*a, **k)
        except errors.FloodWaitError as e:
            log.warning("⏳ FloodWait %ds – pause forcée…", e.seconds)
            
            return None
        except errors.PeerFloodError:
            log.error("🚨 PeerFloodError : STOP immédiat pour éviter le ban.")
            save_state(state)
            log.error("Sleep Long de 2h")
            await asyncio.sleep(7200)

        except (errors.ChatWriteForbiddenError,
                errors.UserIsBlockedError,
                errors.UserPrivacyRestrictedError):
            return False
        except Exception as exc:
            log.error("Erreur %s: %s", fn.__name__, exc)
            return None

# --------------------------------------------------------------------------- #
# 4. SCRAPE COMMENTATEURS                                                    #
# --------------------------------------------------------------------------- #
async def scrape_comments(client):
    added = 0
    chan = await safe_call(client.get_entity, CHANNEL_SRC)
    if not chan:
        return added

    full = await safe_call(lambda: client(GetFullChannelRequest(chan)))
    if not full or not full.full_chat.linked_chat_id:
        log.error("Le canal source n’a pas de groupe de discussion lié.")
        return added
    discussion = await safe_call(client.get_entity, full.full_chat.linked_chat_id)

    processed = set(state.get("channels", {}).get(str(chan.id), {}).get("posts", []))
    users = state["users"]

    try:
        async for post in client.iter_messages(chan, limit=200):
            if post.id in processed or not (post.replies and post.replies.replies):
                continue

            disc_msg = await safe_call(lambda: client(GetDiscussionMessageRequest(chan, post.id)))
            if not disc_msg or not disc_msg.messages:
                continue

            root_id = min(disc_msg.messages, key=lambda m: m.id).id

            async for cm in client.iter_messages(discussion, reply_to=root_id):
                uid = str(cm.sender_id)
                if uid not in users:
                    users[uid] = {
                        "username": getattr(cm.sender, "username", None),
                        "greeted": False,
                        "responded": False,
                        "invited": False
                    }
                    added += 1
                    log.info("Scrap +1 : %s (@%s)", uid, users[uid]["username"] or "—")

                    if added >= SCRAP_LIMIT:
                        raise StopAsyncIteration  # Sortie propre si limite atteinte

                await asyncio.sleep(scrape_delay() * 2)

            processed.add(post.id)
            state.setdefault("channels", {}).setdefault(str(chan.id), {})["posts"] = list(processed)
            save_state(state)

            if added >= SCRAP_LIMIT:
                raise StopAsyncIteration

            await asyncio.sleep(scrape_delay() * 10)

    except KeyboardInterrupt:
        log.warning("⛔ Scraping interrompu manuellement. Sauvegarde de l'état…")
        save_state(state)

    except StopAsyncIteration:
        log.info("✅ Limite de scraping atteinte. Passage à la suite…")

    finally:
        save_state(state)
        log.info("✅ Scraping terminé : %d nouveaux utilisateurs ajoutés.", added)
        log_stats()

    return added

HUMAN_CHANNELS = [ch.strip() for ch in os.getenv("HUMAN_CHANNELS", "").split(",") if ch.strip()]
# Simulation de navigation / lecture dans des channels pour paraître humain
async def simulate_navigation(client):
    if not HUMAN_CHANNELS or random.random() < 0.6:
        return
    ch = random.choice(HUMAN_CHANNELS)
    msgs = await client.get_messages(ch, limit=random.randint(5,15))
    for m in msgs:
        await asyncio.sleep(random.uniform(0.5, 1.5))
    log.info(f"📖 Lecture de {len(msgs)} msgs dans {ch}")
    await asyncio.sleep(random.uniform(10, 60))  # pause de navigation

from telethon.tl.functions.messages import GetHistoryRequest

async def do_normal_action(client):
    # 1) Simulate casual scrolling/reading
    await simulate_navigation(client)
    if not HUMAN_CHANNELS or random.random() < 0.5:
        return

    # 2) Pick a random “human” channel and fetch its last 10 messages
    target = random.choice(HUMAN_CHANNELS)
    history = await client(GetHistoryRequest(
        peer=target,
        offset_id=0,
        offset_date=None,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
        hash=0
    ))
    msgs = [m for m in history.messages if getattr(m, "message", "").strip()]
    if not msgs:
        return

    # 3) “Read” a random message
    msg = random.choice(msgs)
    await asyncio.sleep(random.uniform(2, 8))

    # 4) Choose an interaction type
    action = random.choice(["reaction", "reply", "short_msg"])
    if action == "reaction":
        emoji = random.choice(["👍", "❤️", "😂", "🙌"])
        await client(SendReactionRequest(
            peer=target,
            msg_id=msg.id,
            reaction=[ReactionEmoji(emoticon=emoji)]
        ))
        log.info(f"👍 Réaction '{emoji}' au message {msg.id} dans {target}")

    elif action == "reply":
        reply_text = random.choice(["Haha 😄", "Bien dit !", "🔥", "👏"])
        await asyncio.sleep(random.uniform(1, 3))
        await client.send_message(target, reply_text, reply_to=msg.id)
        log.info(f"💬 Réponse courte envoyée au message {msg.id} dans {target}")

    else:  # short_msg
        await asyncio.sleep(random.uniform(1, 3))
        text = random.choice(["Yo 👋", "Let’s go !", "🔥"])
        await client.send_message(target, text)
        log.info(f"📢 Message court envoyé dans {target}")

    # 5) Pause briefly before next human action
    await asyncio.sleep(random.uniform(30, 120))


async def handle_reply(event):
    sender = str(event.sender_id)
    info = state["users"].get(sender)
    if not info:
        return

    if not info["responded"]:
        info["responded"] = True
        save_state(state)
        log.info(f"✅ {sender} a répondu (@{info.get('username')})")

    if info["greeted"] and not info["invited"]:
        peer = await event.get_input_sender()
        await asyncio.sleep(random.uniform(5, 15))
        async with event.client.action(peer, 'typing'):
            await asyncio.sleep(random.uniform(1, 2))
        invite_msg = random.choice(INVITES).format(link=CHANNEL_TARGET)
        res = await safe_call(event.client.send_message, peer, invite_msg)
        if res:
            info["invited"] = True
            save_state(state)
            log.info(f"✅ Lien envoyé à {sender}")
        else:
            log.error(f"❌ échec envoi lien à {sender}")

# --------------------------------------------------------------------------- #
# LIMITES STRICTES (PeerFlood-safe)                                          #
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# LIMITES STRICTES (PeerFlood-safe)
# --------------------------------------------------------------------------- #
from telethon import TelegramClient, events, errors
from telethon.tl.functions.channels import GetFullChannelRequest, InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import GetDiscussionMessageRequest, ImportChatInviteRequest
# … other imports …

# --------------------------------------------------------------------------- #
# 6. REJOINDRE LE CANAL PRIVÉ (si besoin)                                    #
# --------------------------------------------------------------------------- #
async def ensure_join(client, link: str):
    if not link:
        return
    ch = link.strip().split('/')[-1]
    try:
        if link.startswith("https://t.me/+") or "/joinchat/" in link:
            await client(ImportChatInviteRequest(ch))
        elif link.startswith("https://t.me/") or link.startswith("@"):
            username = ch if not ch.startswith("@") else ch[1:]
            await client(JoinChannelRequest(username))
        log.info(f"✅ Rejoint {link}")
    except errors.UserAlreadyParticipantError:
        pass
    except errors.InviteHashInvalidError:
        log.error("💥 Invite invalide : %s", link)
    except Exception as exc:
        log.error("Erreur ensure_join: %s", exc)


PROXY = None
if os.getenv("PROXY_ENABLED", "false").lower() == "true":
    import socks
    PROXY = (getattr(socks, os.getenv("PROXY_TYPE","socks5").upper()), os.getenv("PROXY_HOST"), int(os.getenv("PROXY_PORT")), True, os.getenv("PROXY_USER"), os.getenv("PROXY_PASS"))

async def wait_for_skip():
    """
    Écoute en arrière-plan si l'utilisateur tape 't' pour skip scraping.
    """
    loop = asyncio.get_event_loop()
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    try:
        while True:
            char = await loop.run_in_executor(None, sys.stdin.read, 1)
            if char.lower() == 't':
                logging.info("⏭ Skip demandé par l'utilisateur (t)")
                return True
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

async def dm_users(client, session_limit: int = 2):
    log.info("▶ Entering dm_users (session_limit=%d)…", session_limit)
    sent = 0
    for uid, info in state["users"].items():
        # STOP if we hit our per‑session or daily cap
        if sent >= session_limit or state["invites_today"] >= DAILY_QUOTA:
            break

        # ONLY DM folks we’ve never greeted or invited
        if info["greeted"] or info["invited"]:
            continue

        peer = await client.get_input_entity(int(uid))
        # SIMULATE reading their last few messages
        await client.get_messages(peer, limit=3)
        await asyncio.sleep(random.uniform(5, 20))

        # TYPING simulation
        greet = random.choice(GREETS).format(username=info["username"] or "toi")
        typ_time = max(len(greet) * random.uniform(0.05, 0.12), random.uniform(1, 3))
        async with client.action(peer, 'typing'):
            await asyncio.sleep(typ_time)

        # SEND the greet
        res = await safe_call(client.send_message, peer, greet)
        mark_greeted(uid)
        if res:
            state["invites_today"] += 1
            sent += 1
            log.info("✅ Greet #%d envoyé à %s", sent, uid)
        else:
            log.info("⚠️ Échec DM pour %s – marqué comme greeté", uid)

        # GHOST request for “background” traffic
        try:
            http_get("https://telegram.org")
            log.debug("📡 Requête fantôme effectuée")
        except:
            pass

        # PAUSE 1–5 min
        pause = random.uniform(500, 1000)
        log.info("⏸️ Pause de %.1fs avant le prochain DM", pause)
        await asyncio.sleep(pause)

    log.info("🔹 dm_users session terminée: %d envoyés.", sent)
    return sent


async def main():
    # 1) TELETHON CLIENT WITH MOBILE FINGERPRINT
    client = TelegramClient(
        session=SESSION,           # e.g. "learnfx_29"
        api_id=API_ID,             # int
        api_hash=API_HASH,         # str
        device_model="OnePlus9",   # mimic real Android
        system_version="11.0",
        app_version="8.5.1",
        lang_code="en"
    )

    # 2) START (this will send the code request correctly)
    await client.start(phone=PHONE)
    log.info("✅ Client connecté (empreinte officielle Telethon)")

    # 3) REPLY HANDLER
    client.add_event_handler(handle_reply, events.NewMessage(incoming=True))

    # 4) JOIN TARGET & HUMAN CHANNELS
    async def safe_join(link):
        try:
            if "joinchat" in link or link.startswith("https://t.me/+"):
                h = urlparse(link).path.rsplit("/",1)[-1]
                await client(ImportChatInviteRequest(h))
            else:
                username = link.split("/")[-1].lstrip("@")
                await client(JoinChannelRequest(username))
            log.info(f"✅ Rejoint {link}")
        except errors.UserAlreadyParticipantError:
            pass
        except Exception as e:
            log.error(f"Erreur ensure_join pour {link}: {e}")

    await safe_join(CHANNEL_TARGET)
    for ch in HUMAN_CHANNELS:
        await safe_join(ch)

    # 5) MAIN LOOP
    while True:
        # a) SCRAPE when we need more prospects
        unsent = sum(1 for u in state["users"].values() if not u["greeted"])
        if unsent < DAILY_QUOTA:
            log.info("📥 Début scraping… (t pour skip)")
            skip = asyncio.create_task(wait_for_skip())
            scrape = asyncio.create_task(scrape_comments(client))
            done, _ = await asyncio.wait(
                [skip, scrape],
                return_when=asyncio.FIRST_COMPLETED
            )
            if skip in done:
                scrape.cancel()
                try: await scrape
                except asyncio.CancelledError: pass
                log.info("✅ Scraping annulé – on passe aux DMs")
            else:
                skip.cancel()
        else:
            log.info("✅ Objectif prospects atteint, passage DM")

        # b) DM session (up to 3)
        log.info("✉️ Envoi de DMs")
        sent = await dm_users(client, session_limit=3)
        log.info(f"🔹 Session DM envoyés: {sent}")

        # c) HUMAN actions
        log.info("🤖 Navigation & interactions humaines…")
        await simulate_navigation(client)
        await do_normal_action(client)

        # d) BIG PAUSE (30–60 min)
        pause = random.uniform(1800, 3600)
        log.info(f"⏳ Pause longue: {pause/60:.1f}min")
        await asyncio.sleep(pause)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Interruption manuelle, sauvegarde état.")
        save_state(state)
