"""SparrowLegends, an independent MapleLegends utility bot for Fluxer.

Install with: python -m pip install requests websocket-client matplotlib
Create a dedicated public Fluxer application named SparrowLegends and use its
bot token in SPARROWLEGENDS_TOKEN. Then run: python sparrowlegends.py
Keep the process running and give community managers its authorization link.
Use View Channel, Send Messages, Embed Links, and Attach Files in bot channels.
Use !sparrowhelp for commands. Keep sparrowlegends.sqlite3 between restarts.
"""

# MIT License
#
# Copyright (c) 2022 Abram Sanderson
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
from queue import Full, Queue
import random
import re
import sqlite3
import threading
import time

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import websocket

API = "https://legends.ml/api"
GUIDES = "https://guides.sparrowtools.net"
SUPPRESS_EMBEDS = 1 << 2
USER_COMMAND_COOLDOWN = 3
BOSS_TIMER_NOTICE = "Timers are temporary and may be lost when the bot restarts or is redeployed."
# Source: Freddie Bot (MIT), Abram Sanderson.
BOSSES = {"anego":480,"samurai":660,"mano":60,"faust":120,"clang":120,"timer":120,"mushmom":120,"bmushmom":240,"dyle":120,"zmushmom":120,"fox":180,"taeroon":180,"sagecat":180,"eliza":180,"snowman":180,"manon":90,"griffey":90,"pianusl":2160,"pianusr":1440,"stumpy":60,"balrog":180,"deo":60,"seruf":60,"zeno":120,"kimera":180,"levi":240,"dodo":240,"lilynouch":240,"lyka":240,"crow":1380,"spirit":720,"shade":180,"dummy":180,"riche":180,"witch":180,"camera":180,"scholar":180,"rurumo":40,"deetnroi":40}
WASH = {
    # Minimum MP per level, constant, MP/reset, stale HP, fresh expected HP.
    "spearman": (4, 155, 4, 20, 52), "page": (4, 155, 4, 20, 52),
    "fighter": (4, 55, 4, 20, 52), "archer": (14, 135, 12, 16, 18),
    "thief": (14, 135, 12, 16, 18), "brawler": (18, 95, 16, 18, 38),
    "gunslinger": (18, 95, 16, 18, 18), "magician": (22, 449, 30, 6, 8),
}
ALIASES = {
    "buccaneer": "brawler", "bucc": "brawler", "corsair": "gunslinger",
    "hero": "fighter", "paladin": "page", "darkknight": "spearman",
    "bowmaster": "archer", "marksman": "archer", "shadower": "thief",
    "nightlord": "thief", "bishop": "magician", "archmage": "magician", "firepoison": "magician", "icelightning": "magician",
}
WASH_GUIDES = {
    "Warrior": "https://forum.legends.ml/index.php?threads/guide-krythans-warrior-washing-guide-washing-your-hero-paladin-or-dark-knight.53639/",
    "Mage": "https://forum.legends.ml/index.php?threads/guide-krythans-mage-washing-guide-washing-your-bishop-fire-poison-or-ice-lightning-arch-mage.51517/",
    "Archer": "https://forum.legends.ml/index.php?threads/guide-krythans-archer-washing-guide-washing-your-bowmaster-or-marksman.57545/",
    "Night Lord": "https://forum.legends.ml/index.php?threads/krythans-night-lord-guide-to-thirty-thousand-hit-points.49823/",
    "Shadower": "https://forum.legends.ml/index.php?threads/guide-krythans-shadower-washing-guide.59101/",
    "Buccaneer": "https://forum.legends.ml/index.php?threads/guide-krythans-buccaneer-washing-guide-washing-your-si-tl-mule.54068/",
    "Corsair": "https://forum.legends.ml/index.php?threads/krythans-corsair-washing-guide.59903/",
}
WASH_SHORT_NAMES = {
    "dk": "darkknight", "dragonknight": "darkknight", "pala": "paladin",
    "bm": "bowmaster", "mm": "marksman", "shad": "shadower", "nl": "nightlord",
    "sair": "corsair", "bish": "bishop", "am": "archmage",
    "fp": "firepoison", "il": "icelightning", "mage": "magician",
    "archmagefp": "firepoison", "archmageil": "icelightning",
    "firepoisonarchmage": "firepoison", "icelightningarchmage": "icelightning",
}
WASH_GUIDES_BY_JOB = {
    "spearman": ("Warrior",), "page": ("Warrior",), "fighter": ("Warrior",),
    "archer": ("Archer",), "magician": ("Mage",),
    "thief": ("Night Lord", "Shadower"), "nightlord": ("Night Lord",),
    "shadower": ("Shadower",), "brawler": ("Buccaneer",), "gunslinger": ("Corsair",),
}
PAGES = {
    "index": ("Sparrow’s MapleLegends Guide Index", "/"),
    "hh": ("Haunted Forest and Bigfoot guide", "/guides/finding-and-killing-bigfoot/"),
    "ninja_castle": ("Ninja Castle map", "/guides/ninja-castle-map/"),
    "zpq": ("Zakum prequest guide", "https://forum.legends.ml/index.php?threads/zakum-prequest-guide.2738/"),
    "apq": ("Amoria PQ guide", "https://forum.legends.ml/index.php?threads/apq-guide-with-pictures.52148/"),
    "apqbonus": ("APQ bonus reference", "/guides/apq-bonus-reference/"),
    "gpq": ("GPQ Stage 3 practice tool", "https://forum.legends.ml/index.php?threads/gpq-stage-3-practice-tool.41495/"),
    "lpq": ("LPQ guide", "https://forum.legends.ml/index.php?threads/lpq-guide-for-scrubs.3903/"),
    "opq": ("Orbis PQ guide", "https://forum.legends.ml/index.php?threads/orbis-party-quest-guide.54745/"),
    "hpq": ("Henesys PQ guide", "https://forum.legends.ml/index.php?threads/henesys-pq-guide.3379/"),
    "cwkpq": ("CWKPQ guide", "https://forum.legends.ml/index.php?threads/guide-crimsonwood-keep-party-quest.24194/"),
    "cwkpre": ("CWK prequests", "https://forum.legends.ml/index.php?threads/guide-crimsonwood-keep-cwk-pre-quests.54671/"),
    "cwksigils": ("CWKPQ sigils", "/guides/cwkpq-sigils/"),
    "mpq": ("Magatia PQ guide", "https://forum.legends.ml/index.php?threads/guide-comprehensive-guide-to-magatia-party-quest.45491/"),
    "wash": ("HP washing formulas", "https://forum.legends.ml/index.php?threads/nises-hp-washing-formula-compilation.38558/"),
}
GUIDE_ALIASES = {
    "bf": "hh", "phantom": "hh", "ninjacastle": "ninja_castle",
    "cwkpre": "cwkpq", "cwksigils": "cwkpq",
}
GUIDE_EXTRAS = {
    "gpq": "Stage 2 code: 2152212",
    "hh": "[Phantom Forest Navigator](https://phantomforest.sparrowtools.net/)",
}
GUIDE_TOOL_CARDS = {
    "opq": ("OPQ Helper", "https://orbis-pq-helper.vercel.app/", "A companion tool for Orbis Party Quest."),
    "mpq": ("MPQ Helper", "https://maplestory-helper.web.app/", "A helper for Magatia Party Quest Stage 6."),
}
CWKPQ_IMAGES = (
    "8CyAecT", "ucg3l0P", "Nd6dAhv", "wAy9gmo",
    "htOHH87", "vybIyrz", "XrPUoe7", "DnLvvwA",
)
CWKPQ_IMAGE_DIR = Path(__file__).resolve().parent / "cwkpq-images"
GUIDE_IMAGES = {
    "apq": "amoria-stage-2.png",
    "apqbonus": "amoria-bonus.png",
    "hh": "bigfoot-route.png",
    "ninja_castle": "ninja-castle.png",
}


def image_as_png(data):
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError):
        return None


def png_attachment(url):
    try:
        response = requests.get(url, timeout=(3, 7))
        response.raise_for_status()
        if urlsplit(response.url).path.endswith("/removed.png"):
            return None
        return image_as_png(response.content)
    except requests.RequestException:
        return None


def local_cwkpq_image(players):
    for extension in ("png", "jpg", "jpeg", "webp"):
        path = CWKPQ_IMAGE_DIR / f"{players}.{extension}"
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            logging.warning("Could not read CWKPQ image: %s", path)
            continue
        image = image_as_png(data)
        if image:
            return image
        logging.warning("Could not decode CWKPQ image: %s", path)
    return None


def cwkpq_split_image(players, each, extra):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (720, 290), "#171925")
    draw = ImageDraw.Draw(image)
    draw.text((28, 20), f"CWKPQ bonus split  |  {players} looters", fill="white",
              font=ImageFont.load_default(size=28))
    draw.text((28, 58), "Boxes per roll position", fill="#bbc1d5",
              font=ImageFont.load_default(size=17))
    for roll in range(1, players + 1):
        row, column = divmod(roll - 1, 5)
        left, top = 28 + column * 135, 93 + row * 88
        draw.rounded_rectangle((left, top, left + 122, top + 72), radius=10,
                               fill="#2c3150")
        draw.text((left + 12, top + 9), f"Roll {roll}", fill="#bbc1d5",
                  font=ImageFont.load_default(size=16))
        draw.text((left + 12, top + 33), f"{each + (roll <= extra)} boxes", fill="white",
                  font=ImageFont.load_default(size=21))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


USAGE = {
    "sparrowhelp": ("",),
    "maple": ("[IGN]",),
    "partyroll": ("create [IGN1 IGN2 IGN3 ...]", "redo [previous order] [+IGN:optional] [-IGN:optional]"),
    "washes": ("[job] [level] [MaxMP]",),
    "bosstimer": (
        "", "bosses", "show [boss:optional]",
        "add [boss] [channels 1–6 separated by commas, or all] [time ago, e.g. 5m 30s:optional]",
        "delete [boss] [channels 1–6 separated by commas, or all]",
    ),
    "bloodwash": ("[level] [base STR] [base DEX] [base INT] [base LUK]",),
    "levels": ("[IGN1 IGN2 ... up to 5]",),
    "guide": ("[topic:optional]", "cwkpq [3–10 looters]"),
    "cwkpq": ("[3–10 looters:optional]",),
    "serverinfo": ("",),
}


def command_usage(name):
    return "\n".join(f"`!{name}{' ' + args if args else ''}`" for args in USAGE[name])


class InputError(ValueError):
    pass


def guide_link(key):
    label, path = PAGES[key]
    url = path if path.startswith("https://") else f"{GUIDES}{path}"
    return f"[{label}]({url})"


def get_json(endpoint, **params):
    response = requests.get(f"{API}/{endpoint}", params=params, timeout=(4, 8))
    if response.status_code == 404 and endpoint in {"character", "getlevels"}:
        return None
    response.raise_for_status()
    return response.json()


def names(text, maximum):
    result = [part for part in re.split(r"[\s,]+", text) if part]
    if not 1 <= len(result) <= maximum or any(
        not re.fullmatch(r"[A-Za-z0-9]{1,12}", name) for name in result
    ):
        raise InputError(f"Enter 1–{maximum} MapleLegends character names.")
    if len({name.casefold() for name in result}) != len(result):
        raise InputError("Enter each character name only once.")
    return result


def duration(text):
    if not text:
        return 0
    pattern = r"(\d{1,6})\s*([dhms])"
    if not re.fullmatch(r"(?:\d{1,6}\s*[dhms]\s*)+", text.casefold()):
        raise InputError("Use an elapsed time like 5m 30s.")
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[unit] for n, unit in re.findall(pattern, text.casefold()))


def spawn_window(start, end):
    return f"<t:{start}:f> – <t:{end}:t>"


def level_plot(series):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    from matplotlib.figure import Figure

    figure = Figure(figsize=(10, 5.2), layout="constrained")
    canvas = FigureCanvasAgg(figure)
    ax = figure.subplots()
    for name, points in series.items():
        dates, levels = zip(*points)
        ax.plot(dates, levels, marker=".", linestyle="None", label=name)
    locator = AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    ax.set(title="MapleLegends level history", ylabel="Level", xlabel="Date (UTC)")
    ax.grid(alpha=0.25)
    ax.legend()
    result = io.BytesIO()
    canvas.print_png(result)
    return result.getvalue()


class MapleCommands:
    def __init__(self, client, db):
        self.client = client
        self.db = db
        self.queue = Queue(maxsize=24)
        self.recent_commands = OrderedDict()
        with closing(self.connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS boss_timers (
                    guild TEXT, room TEXT, boss TEXT, channel INTEGER,
                    killed INTEGER, start INTEGER, end INTEGER,
                    PRIMARY KEY (guild, room, boss, channel)
                )
            """)
        threading.Thread(target=self.run, name="maple-commands", daemon=True).start()

    def connect(self):
        return sqlite3.connect(self.db, timeout=5)

    def submit(self, event):
        guild = str(event.get("guild_id", ""))
        if not guild.isdecimal() or event.get("webhook_id") or event.get("flags", 0) & 2:
            return False
        author = event.get("author") or {}
        if not author.get("id") or author.get("bot") or str(author["id"]) == str(self.client.uid):
            return False
        parts = (event.get("content") or "").strip().split(maxsplit=1)
        if not parts or not parts[0].startswith("!"):
            return False
        name = parts[0][1:].casefold()
        arguments = parts[1] if len(parts) > 1 else ""
        if name not in USAGE and (name in PAGES or name in GUIDE_ALIASES) and not arguments:
            name, arguments = "guide", name
        room = str(event.get("channel_id", ""))
        if name not in USAGE or not room.isdecimal():
            return False
        user_id = str(author["id"])
        now = time.monotonic()
        cutoff = now - USER_COMMAND_COOLDOWN
        while self.recent_commands and next(iter(self.recent_commands.values())) <= cutoff:
            self.recent_commands.popitem(last=False)
        if user_id in self.recent_commands:
            return True
        try:
            self.queue.put_nowait((guild, room, name, arguments))
        except Full:
            logging.warning("Maple command queue is full")
        else:
            self.recent_commands[user_id] = now
        return True

    def send(self, room, payload, image=None, filename="levels.png"):
        payload["allowed_mentions"] = {"parse": []}
        if re.search(r"https?://", payload.get("content", "")):
            payload["flags"] = payload.get("flags", 0) | SUPPRESS_EMBEDS
        path = f"/channels/{room}/messages"
        if image is None:
            self.client.req("POST", path, json=payload)
        else:
            payload["attachments"] = [{"id": 0, "filename": filename}]
            self.client.req("POST", path, data={"payload_json": json.dumps(payload)},
                            files={"files[0]": (filename, image, "image/png")})

    def run(self):
        while True:
            guild, room, name, text = self.queue.get()
            try:
                self.dispatch(guild, room, name, text)
            except Exception:
                logging.exception("Maple command delivery failed: %s", name)

    def dispatch(self, guild, room, name, text):
        try:
            if name == "bosstimer":
                result = self.bosstimer(guild, room, text)
                result += f"\n\n{BOSS_TIMER_NOTICE}"
            else:
                result = getattr(self, name)(room, text)
        except InputError as error:
            result = f"{error}\n{command_usage(name)}"
        except (requests.RequestException, ValueError, KeyError, TypeError):
            result = "MapleLegends data is temporarily unavailable. Try again in a moment."
        if isinstance(result, tuple):
            content, image, *filename = result
            payload = content if isinstance(content, dict) else {"content": content}
            self.send(room, payload, image, *filename)
        else:
            self.send(room, result if isinstance(result, dict) else {"content": result})

    def sparrowhelp(self, room, text):
        sections = (
            ("Character and server", ("maple", "levels", "serverinfo")),
            ("HP washing", ("washes", "bloodwash")),
            ("Party and bossing", ("partyroll", "bosstimer")),
            ("Guides and party quests", ("guide", "cwkpq")),
            ("Help", ("sparrowhelp",)),
        )
        body = "\n\n".join(
            f"**{title}**\n" + "\n".join(command_usage(name) for name in commands)
            for title, commands in sections
        )
        return ("**SparrowLegends commands**\n"
                "Replace bracketed labels with your input. Leave out optional inputs you do not need.\n\n"
                + body
                + "\n\nEach user can run one command every 3 seconds. "
                "Community admins can limit the bot to one channel and enable Slowmode there.")

    def maple(self, room, text):
        name, = names(text, 1)
        stats = get_json("character", name=name)
        if not stats or not stats.get("name"):
            return f"No public character profile found for **{name}**."
        labels = {
            "job": "Job", "level": "Level", "exp": "EXP", "guild": "Guild",
            "fame": "Fame", "cards": "Monster cards", "quests": "Quests completed",
            "gender": "Gender", "donor": "Donor",
        }
        fields = []
        for key, label in labels.items():
            value = stats.get(key)
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            if value is None or value == "":
                if key != "guild":
                    continue
                value = "None"
            fields.append({"name": label, "value": str(value)[:200], "inline": True})
        return {"embeds": [{"title": str(stats["name"])[:100], "fields": fields}]}

    def partyroll(self, room, text):
        rng = random.SystemRandom()
        action, _, rest = text.partition(" ")
        if action.casefold() == "redo":
            rest = re.sub(r"^previous_roll\s+", "", rest, flags=re.I)
            rest = re.sub(r"\s+Short string format:\s*", " ", rest, flags=re.I)
            # Accept pasted numbered output as well as the plain list.
            if re.search(r"\b1\s*-\s*[a-z0-9]", rest, re.I):
                rest = rest[re.search(r"\b1\s*-\s*[a-z0-9]", rest, re.I).start():]
                rest = re.sub(r"\b\d+\s*-\s*(?=[a-z0-9])", "", rest, flags=re.I)
            parts = [item for item in re.split(r"[\s,]+", rest) if item]
            previous = []
            modifier = ""
            for item in parts:
                if item.casefold() in {"add_characters", "remove_characters"}:
                    modifier = "+" if item.casefold() == "add_characters" else "-"
                    continue
                previous.append(modifier + item if modifier and item[0] not in "+-" else item)
            parts = previous
            result = names(" ".join(item for item in parts if item[0] not in "+-"), 30)
            additions = [item[1:] for item in parts if item.startswith("+")]
            removals = [item[1:] for item in parts if item.startswith("-")]
            if additions or removals:
                names(" ".join(additions + removals), 30)
            removed = {item.casefold() for item in removals}
            if not removed <= {item.casefold() for item in result}:
                raise InputError("A character to remove is missing from the previous order.")
            result = [item for item in result if item.casefold() not in removed]
            names(" ".join(result + additions), 30)
            for item in additions:
                result.insert(rng.randrange(len(result) + 1), item)
        else:
            result = names(rest if action.casefold() == "create" else text, 30)
            rng.shuffle(result)
        short = ", ".join(f"{n} - {name}" for n, name in enumerate(result, 1))
        return "\n".join(result) + "\n\nShort string format:\n" + short

    def washes(self, room, text):
        args = text.casefold().split()
        entered_job = re.sub(r"[/()]", "", "".join(args[:-2]))
        entered_job = WASH_SHORT_NAMES.get(entered_job, entered_job)
        job = ALIASES.get(entered_job, entered_job)
        if len(args) < 3 or job not in WASH or any(not re.fullmatch(r"[0-9]{1,7}", x) for x in args[-2:]):
            raise InputError("Jobs: " + ", ".join(WASH) + ".")
        level, mp = map(int, args[-2:])
        if not 1 <= level <= 200 or mp < 1:
            raise InputError("Enter a level from 1 to 200 and a positive MaxMP.")
        rate, base, reset, stale, fresh = WASH[job]
        minimum = rate * level + base
        excess = max(mp - minimum, 0)
        count = excess // reset
        nx = 3100 * count
        note = "\nFresh wash assumes maxed HP bonus skills." if job in {"spearman", "page", "fighter", "brawler"} else ""
        guide_names = WASH_GUIDES_BY_JOB.get(entered_job, WASH_GUIDES_BY_JOB[job])
        links = "\n".join(f"[Krythan's {name} HP Washing Guide]({WASH_GUIDES[name]})"
                          for name in guide_names)
        return (f"**{job.title()} · Lv. {level}**\nMin MP: {minimum:,} · Extra MP: {excess:,}\n"
                f"**{count:,} washes** · Stale: +{count * stale:,} HP\n"
                f"Fresh: ~+{count * fresh:,} HP ({count * (fresh - 2):,}–{count * (fresh + 2):,})\n"
                f"AP resets: {nx:,} NX ({(nx + 4999) // 5000:,} votes at 5,000 NX each)"
                f"{note}\n{links}")

    def bloodwash(self, room, text):
        args = text.split()
        if len(args) != 5 or any(not re.fullmatch(r"[0-9]{1,4}", x) for x in args):
            raise InputError("Enter level and four base stats.")
        level, *stats = map(int, args)
        if not 1 <= level <= 200 or min(stats) < 4:
            raise InputError("Use level 1–200 and base stats of at least 4.")
        total = 25 + 5 * (level - 1) + 5 * (level >= 70) + 5 * (level >= 120)
        unused_or_washed = total - sum(stats)
        if unused_or_washed < 0:
            raise InputError("Base stats exceed the AP available at that level. Check for equipment bonuses.")
        return (f"**{unused_or_washed} AP** outside base stats. This is the amount assigned to HP/MP "
                "if you have spent all available AP and completed the eligible job advancements.")

    def guide(self, room, text):
        topic = text.split(maxsplit=1)
        if len(topic) == 2 and topic[0].casefold() == "cwkpq":
            return self.cwkpq(room, topic[1])
        key = re.sub(r"[\s-]", "", text.casefold())
        key = GUIDE_ALIASES.get(key, key)
        if key == "cwkpq":
            return self.cwkpq(room, "")
        if key in GUIDE_IMAGES:
            filename = GUIDE_IMAGES[key]
            url = f"{GUIDES}/assets/{filename}"
            image = png_attachment(url)
            if key == "apqbonus":
                if image:
                    return {}, image, filename
                return "The APQ bonus image is temporarily unavailable."
            content = guide_link(key)
            if key in GUIDE_EXTRAS:
                content += "\n" + GUIDE_EXTRAS[key]
            if image:
                return content, image, filename
            return f"{content}\n[Open reference image]({url})"
        if key in GUIDE_TOOL_CARDS:
            title, url, description = GUIDE_TOOL_CARDS[key]
            return {"embeds": [{
                "title": title,
                "url": url,
                "description": f"{description}\n\n{guide_link(key)}",
            }]}
        if key in PAGES:
            link = guide_link(key)
            return f"{link}\n{GUIDE_EXTRAS[key]}" if key in GUIDE_EXTRAS else link
        shortcuts = "\n".join(f"`!guide {topic}` — {label}"
                              for topic, (label, _) in PAGES.items() if topic not in GUIDE_ALIASES)
        shortcuts += "\n`!guide cwkpq [3–10 looters]` — CWKPQ bonus split"
        intro = "**Available guide topics**"
        if key:
            intro = f"No shortcut for that topic.\n\n{intro}"
        return intro + "\n" + shortcuts

    def cwkpq(self, room, text):
        links = " · ".join(guide_link(key) for key in ("cwkpq", "cwkpre", "cwksigils"))
        if not text:
            content = "\n".join(guide_link(key) for key in ("cwkpq", "cwkpre"))
            filename = "cwkpq-sigils.png"
            try:
                image = (CWKPQ_IMAGE_DIR / filename).read_bytes()
            except OSError:
                image = png_attachment(f"{GUIDES}/assets/{filename}")
            if image:
                return content, image, filename
            return content + "\nThe CWKPQ sigils image is temporarily unavailable."
        if not re.fullmatch(r"[3-9]|10", text):
            raise InputError("Enter a looter count from 3 to 10.")
        players = int(text)
        each, extra = divmod(30, players)
        split = f"Each player gets **{each} boxes**."
        if extra:
            split = (f"Roll positions **1–{extra}** get **{each + 1} boxes each**. "
                     f"Positions **{extra + 1}–{players}** get **{each} boxes each**.")
        url = f"https://i.imgur.com/{CWKPQ_IMAGES[players - 3]}.png"
        image = local_cwkpq_image(players) or png_attachment(url)
        if not image:
            image = cwkpq_split_image(players, each, extra)
        content = f"**CWKPQ Bonus Stage · {players} looters**\n{split}\n\n{links}"
        return content, image, f"cwkpq-{players}-looters.png"

    def serverinfo(self, room, text):
        if text:
            raise InputError("Use !serverinfo to show all server stats.")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        online = get_json("get_online_users")
        unique = get_json("get_unique_users")
        counts = " · ".join(f"{period.title()} {unique[period]:,}"
                            for period in ("daily", "weekly", "monthly"))
        return (f"**Online:** {online['usercount']:,} characters · {online['uniquecount']:,} unique users\n"
                f"**Time:** {now}\n**Unique users:** {counts}")

    def levels(self, room, text):
        series, missing = {}, []
        for name in names(text, 5):
            history = get_json("getlevels", name=name)
            if not isinstance(history, list) or not history:
                missing.append(name)
                continue
            points = []
            for entry in history:
                date = datetime.fromisoformat(entry["date"].replace("Z", "+00:00"))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                points.append((date, int(entry["level"])))
            series[name] = sorted(points)
        missing_text = "\nNo public level history for: " + ", ".join(missing) if missing else ""
        if not series:
            return missing_text.strip()
        summary = "\n".join(f"**{name}:** Lv. {points[0][1]} → {points[-1][1]} ({len(points)} records)"
                            for name, points in series.items()) + missing_text
        try:
            return summary, level_plot(series)
        except ImportError:
            return summary + "\nLevel graph requires matplotlib on the bot host."

    def bosstimer(self, guild, room, text):
        args = text.casefold().split(maxsplit=3) if text else ["show"]
        action = args[0]
        boss = args[1] if len(args) > 1 else None
        if action == "bosses" and len(args) == 1:
            return "**Supported bosses**\n" + ", ".join(sorted(BOSSES))
        if (action not in {"show", "add", "delete"} or
                (boss is not None and boss not in BOSSES) or
                (action == "show" and len(args) > 2) or
                (action != "show" and len(args) < 3) or
                (action == "delete" and len(args) != 3)):
            raise InputError("Use `!bosstimer bosses` to see supported boss names.")
        with closing(self.connect()) as conn, conn:
            if action == "show":
                if boss:
                    records = conn.execute(
                        "SELECT channel, start, end FROM boss_timers "
                        "WHERE guild=? AND room=? AND boss=?", (guild, room, boss),
                    ).fetchall()
                    windows = {ch: (start, end) for ch, start, end in records}
                    now = time.time()
                    lines = [f"**{boss} timers**", ""]
                    for ch in range(1, 7):
                        if ch not in windows:
                            detail = "no spawn time found"
                        else:
                            start, end = windows[ch]
                            if end <= now:
                                detail = f"last known spawn between <t:{start}:f> and <t:{end}:f> *(timer expired)*"
                            else:
                                detail = f"spawn window <t:{start}:t> – <t:{end}:t>"
                        lines.append(f"Channel {ch}: {detail}")
                    lines.extend(("", f"Save a kill with `!bosstimer add {boss} 3`."))
                    return "\n".join(lines)
                rows = conn.execute(
                    "SELECT boss, channel, killed, start, end FROM boss_timers WHERE guild=? AND room=? "
                    "AND (? IS NULL OR boss=?) ORDER BY killed DESC, boss, channel LIMIT 19",
                    (guild, room, boss, boss),
                ).fetchall()
                if not rows:
                    return "No saved timers for this channel."
                lines = [f"**{name}** ch. {ch} · Kill <t:{killed}:R> · Spawn {spawn_window(start, end)}"
                         + (" (expired)" if end < time.time() else "")
                         for name, ch, killed, start, end in rows[:18]]
                if len(rows) > 18:
                    lines.append("Showing the latest 18 entries. Use `!bosstimer show <boss>` to filter.")
                return "\n".join(lines)
            channels = list(range(1, 7)) if args[2] == "all" else args[2].split(",")
            if any(str(channel) not in "123456" or len(str(channel)) != 1 for channel in channels):
                raise InputError("Use channels 1–6 separated by commas, or all.")
            channels = sorted(set(map(int, channels)))
            label = ", ".join(map(str, channels))
            if action == "delete":
                before = conn.total_changes
                conn.executemany("DELETE FROM boss_timers WHERE guild=? AND room=? AND boss=? AND channel=?",
                                 [(guild, room, boss, channel) for channel in channels])
                return f"Deleted {conn.total_changes - before} **{boss}** timer(s)."
            killed = int(time.time()) - duration(args[3] if len(args) > 3 else "")
            cooldown = BOSSES[boss] * 60
            start, end = round(killed + cooldown * 0.9), round(killed + cooldown * 1.1)
            conn.executemany(
                "INSERT INTO boss_timers (guild, room, boss, channel, killed, start, end) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(guild, room, boss, channel) DO UPDATE SET "
                "killed=excluded.killed, start=excluded.start, end=excluded.end",
                [(guild, room, boss, channel, killed, start, end) for channel in channels],
            )
            return f"Saved **{boss}** ch. {label} · Kill <t:{killed}:R> · Spawn {spawn_window(start, end)}"


class DeliveryError(RuntimeError):
    pass


class FluxerClient:
    def __init__(self, origin, token):
        response = requests.get(f"{origin.rstrip('/')}/.well-known/fluxer", timeout=(5, 15))
        response.raise_for_status()
        endpoints = response.json()["endpoints"]
        self.api = endpoints["api_public"].rstrip("/") + "/v1"
        gateway = urlsplit(endpoints["gateway"])
        query = dict(parse_qsl(gateway.query))
        query.update(v="1", encoding="json")
        self.gateway = urlunsplit(gateway._replace(query=urlencode(query)))
        if urlsplit(self.api).scheme != "https" or gateway.scheme != "wss":
            raise DeliveryError("Fluxer discovery must advertise HTTPS and WSS endpoints.")
        self.token = token
        self.uid = str(self.req("GET", "/users/@me")["id"])
        self.session_id = None
        self.sequence = None

    def req(self, method, path, **kwargs):
        for attempt in range(4):
            response = requests.request(
                method, self.api + path, headers={"Authorization": f"Bot {self.token}"},
                timeout=(5, 15), allow_redirects=False, **kwargs,
            )
            if response.status_code == 429 and attempt < 3:
                delay = float(response.json().get("retry_after", 1))
                if delay <= 15:
                    time.sleep(max(delay, 0) + 0.1)
                    continue
            if not 200 <= response.status_code < 300:
                raise DeliveryError(f"Fluxer API HTTP {response.status_code}")
            return response.json() if response.content else None

    def run(self, commands):
        delay = 2
        while True:
            try:
                self.listen(commands)
                delay = 2
            except (OSError, ValueError, KeyError, websocket.WebSocketException) as error:
                logging.warning("Fluxer gateway disconnected (%s)", type(error).__name__)
            time.sleep(delay)
            delay = min(delay * 2, 30)

    def listen(self, commands):
        ws = websocket.create_connection(self.gateway, timeout=90)
        stop = threading.Event()
        ack = threading.Event()
        ack.set()
        heartbeat = None

        def send(op, data):
            ws.send(json.dumps({"op": op, "d": data}))

        def beat():
            while not stop.wait(interval):
                if not ack.is_set():
                    ws.abort()
                    return
                ack.clear()
                try:
                    send(1, self.sequence)
                except (OSError, websocket.WebSocketException):
                    ws.abort()
                    return

        def identify():
            send(2, {"token": self.token, "properties": {
                "os": os.name, "browser": "SparrowLegends", "device": "SparrowLegends",
            }})

        try:
            hello = json.loads(ws.recv())
            if hello["op"] != 10:
                raise ValueError("Expected Gateway Hello")
            interval = hello["d"]["heartbeat_interval"] / 1000
            if self.session_id and self.sequence is not None:
                send(6, {"token": self.token, "session_id": self.session_id, "seq": self.sequence})
            else:
                identify()
            heartbeat = threading.Thread(target=beat, name="fluxer-heartbeat", daemon=True)
            heartbeat.start()
            while True:
                opcode, frame = ws.recv_data()
                if opcode == websocket.ABNF.OPCODE_CLOSE:
                    code = int.from_bytes(frame[:2], "big")
                    if code in {4004, 4010, 4011, 4012}:
                        raise DeliveryError(f"Fluxer rejected the Gateway connection (code {code}).")
                    if code not in {4000, 4008, 4009}:
                        self.session_id = self.sequence = None
                    return
                payload = json.loads(frame)
                op = payload["op"]
                if op == 0:
                    event = payload["t"]
                    if event == "READY":
                        self.session_id = payload["d"]["session_id"]
                        logging.info("SparrowLegends connected to Fluxer")
                    elif event == "MESSAGE_CREATE":
                        commands.submit(payload["d"])
                    self.sequence = payload["s"]
                elif op == 1:
                    send(1, self.sequence)
                elif op == 11:
                    ack.set()
                elif op == 7:
                    return
                elif op == 9:
                    self.session_id = self.sequence = None
                    identify()
        finally:
            stop.set()
            ws.shutdown()
            if heartbeat:
                heartbeat.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description="Run the SparrowLegends bot for Fluxer.")
    parser.add_argument("--instance", default="https://fluxer.app", help="Fluxer instance origin")
    parser.add_argument("--database", type=Path,
                        default=Path(__file__).resolve().with_name("sparrowlegends.sqlite3"),
                        help="Path to the persistent boss timer database")
    args = parser.parse_args()
    token = os.environ.get("SPARROWLEGENDS_TOKEN", "").strip()
    if not token:
        parser.exit(2, "Set SPARROWLEGENDS_TOKEN to the dedicated Fluxer bot token.\n")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        fluxer = FluxerClient(args.instance, token)
        fluxer.run(MapleCommands(fluxer, args.database))
    except KeyboardInterrupt:
        logging.info("SparrowLegends stopped")
    except (DeliveryError, requests.RequestException, KeyError, sqlite3.Error) as error:
        logging.error("SparrowLegends could not run: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
