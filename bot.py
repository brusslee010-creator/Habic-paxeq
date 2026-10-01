import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)
from flask import Flask, jsonify, request, send_from_directory

# ============================================================
# REQUIRED RAILWAY VARIABLES: ONLY BOT_TOKEN AND ADMIN_ID
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add BOT_TOKEN in Railway Variables.")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as exc:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID.") from exc

# Railway automatically exposes this variable when a public domain exists.
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
if RAILWAY_DOMAIN:
    if not RAILWAY_DOMAIN.startswith("http://") and not RAILWAY_DOMAIN.startswith("https://"):
        RAILWAY_DOMAIN = "https://" + RAILWAY_DOMAIN
    ADMIN_URL = RAILWAY_DOMAIN.rstrip("/") + "/admin"
else:
    ADMIN_URL = ""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("stars-media-bot")

# ============================================================
# JSON STORAGE — NO SQLITE
# ============================================================
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_FILE = DATA_DIR / "media.json"
USERS_FILE = DATA_DIR / "users.json"
PURCHASES_FILE = DATA_DIR / "purchases.json"


def save_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_json(path: Path, default):
    if not path.exists():
        save_json(path, default)
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Could not read %s; using empty data.", path)
        return default


media_data = load_json(MEDIA_FILE, [])
users_data = load_json(USERS_FILE, [])
purchases_data = load_json(PURCHASES_FILE, [])


def get_media(media_id: int):
    return next((item for item in media_data if int(item["id"]) == media_id), None)


def all_media():
    return sorted(media_data, key=lambda item: int(item["id"]), reverse=True)


def next_media_id():
    return max((int(item["id"]) for item in media_data), default=0) + 1


def remember_user(message: Message):
    user = message.from_user
    existing = next(
        (item for item in users_data if int(item["user_id"]) == user.id),
        None,
    )
    if existing:
        existing["username"] = user.username
        existing["first_name"] = user.first_name
    else:
        users_data.append(
            {
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "created_at": int(time.time()),
            }
        )
    save_json(USERS_FILE, users_data)


def catalog_keyboard():
    rows = []
    for item in all_media():
        icon = "🎬" if item["media_type"] == "video" else "🖼️"
        price = "🆓 FREE" if int(item["price"]) == 0 else f"⭐ {item['price']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {item['title']} — {price}",
                    callback_data=f"media:{item['id']}",
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="📭 Դեռ նյութ չկա", callback_data="noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# TELEGRAM BOT — CREATED BEFORE HANDLERS
# ============================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


async def send_media_to_user(user_id: int, item: dict):
    caption = f"<b>{item['title']}</b>"
    description = item.get("description", "")
    if description:
        caption += f"\n\n{description}"

    if item["media_type"] == "video":
        await bot.send_video(user_id, item["file_id"], caption=caption)
    else:
        await bot.send_photo(user_id, item["file_id"], caption=caption)


# ============================================================
# USER SIDE
# ============================================================
@dp.message(CommandStart())
async def start_handler(message: Message):
    remember_user(message)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Վիդեոներ / 🖼️ Նկարներ",
                    callback_data="catalog",
                )
            ]
        ]
    )
    await message.answer(
        "👋 <b>Բարի գալուստ!</b>\n\n"
        "Ընտրիր նյութը կատալոգից։\n"
        "🆓 0 ⭐ = անվճար\n"
        "⭐ 1–10000 ⭐ = վճարովի",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data == "catalog")
async def catalog_handler(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📚 <b>Հասանելի նյութերը</b>",
        reply_markup=catalog_keyboard(),
    )


@dp.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer("Այս պահին նյութ չկա։")


@dp.callback_query(F.data.startswith("media:"))
async def media_details_handler(callback: CallbackQuery):
    await callback.answer()
    media_id = int(callback.data.split(":", 1)[1])
    item = get_media(media_id)

    if not item:
        await callback.message.answer("❌ Նյութը չի գտնվել։")
        return

    price = int(item["price"])
    price_text = "🆓 <b>Անվճար</b>" if price == 0 else f"⭐ <b>{price} Stars</b>"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🆓 Ստանալ" if price == 0 else f"⭐ Գնել՝ {price}",
                    callback_data=f"get:{media_id}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Հետ", callback_data="catalog")],
        ]
    )
    description = item.get("description", "")
    await callback.message.edit_text(
        f"<b>{item['title']}</b>\n\n{description}\n\n{price_text}",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("get:"))
async def get_media_handler(callback: CallbackQuery):
    await callback.answer()
    media_id = int(callback.data.split(":", 1)[1])
    item = get_media(media_id)

    if not item:
        await callback.message.answer("❌ Նյութը չի գտնվել։")
        return

    price = int(item["price"])
    if price == 0:
        await send_media_to_user(callback.from_user.id, item)
        return

    payload = f"media:{media_id}:user:{callback.from_user.id}"
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=item["title"][:32],
        description=(item.get("description") or "Digital media")[:255],
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=item["title"][:32], amount=price)],
    )


# ============================================================
# TELEGRAM STARS PAYMENT
# ============================================================
@dp.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    try:
        parts = query.invoice_payload.split(":")
        if len(parts) != 4 or parts[0] != "media":
            await query.answer(ok=False, error_message="Սխալ վճարման տվյալներ։")
            return

        media_id = int(parts[1])
        expected_user_id = int(parts[3])
        item = get_media(media_id)

        if not item or int(item["price"]) <= 0:
            await query.answer(ok=False, error_message="Նյութը այլևս հասանելի չէ։")
            return
        if query.from_user.id != expected_user_id:
            await query.answer(ok=False, error_message="Օգտատերը չի համապատասխանում։")
            return
        if query.currency != "XTR":
            await query.answer(ok=False, error_message="Սխալ արժույթ։")
            return

        await query.answer(ok=True)
    except Exception:
        log.exception("Pre-checkout error")
        await query.answer(ok=False, error_message="Չհաջողվեց ստուգել վճարումը։")


@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    try:
        parts = payment.invoice_payload.split(":")
        media_id = int(parts[1])
        item = get_media(media_id)

        if not item:
            await message.answer("⚠️ Վճարումը ստացվել է, բայց նյութը չի գտնվել։")
            return

        purchases_data.append(
            {
                "user_id": message.from_user.id,
                "media_id": media_id,
                "stars": int(payment.total_amount),
                "telegram_payment_id": payment.telegram_payment_charge_id,
                "created_at": int(time.time()),
            }
        )
        save_json(PURCHASES_FILE, purchases_data)
        await send_media_to_user(message.from_user.id, item)
    except Exception:
        log.exception("Successful payment error")
        await message.answer("⚠️ Վճարումը գրանցվեց, բայց նյութը ուղարկել չհաջողվեց։")


# ============================================================
# ADMIN FILE-ID HELPERS
# ============================================================
@dp.message(Command("getid"))
async def getid_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📌 Ուղարկիր վիդեո կամ նկար, և ես կտամ դրա Telegram file_id-ն։"
    )


@dp.message(F.video)
async def video_file_id_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"🎬 file_id:\n<code>{message.video.file_id}</code>")


@dp.message(F.photo)
async def photo_file_id_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"🖼️ file_id:\n<code>{message.photo[-1].file_id}</code>")


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not ADMIN_URL:
        await message.answer(
            "⚠️ Railway Public Domain-ը դեռ չկա։\n"
            "Ստեղծիր Railway → Settings → Networking → Public Domain, "
            "հետո նորից ուղարկիր /admin։"
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👑 Բացել Admin Panel",
                    web_app=WebAppInfo(url=ADMIN_URL),
                )
            ]
        ]
    )
    await message.answer(
        "👑 <b>Admin Panel</b>\n\n"
        "Այստեղից կարող ես ավելացնել և ջնջել նյութերը։",
        reply_markup=keyboard,
    )


# ============================================================
# WEB ADMIN PANEL
# ============================================================
app = Flask(__name__)


def validate_init_data(init_data: str):
    if not init_data:
        return None

    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = data.pop("hash", None)
        if not received_hash:
            return None

        auth_date = int(data.get("auth_date", "0"))
        if time.time() - auth_date > 86400:
            return None

        data_check_string = "\n".join(
            f"{key}={data[key]}" for key in sorted(data)
        )
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user = json.loads(data.get("user", "{}"))
        if int(user.get("id", 0)) != ADMIN_ID:
            return None
        return user
    except (ValueError, TypeError, json.JSONDecodeError, KeyError):
        return None


def authorized():
    return validate_init_data(request.headers.get("X-Telegram-Init-Data", ""))


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/admin")
def admin_page():
    return send_from_directory(".", "admin.html")


@app.get("/api/media")
def api_media():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(all_media())


@app.get("/api/stats")
def api_stats():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(
        {
            "users": len(users_data),
            "purchases": len(purchases_data),
            "stars": sum(int(item.get("stars", 0)) for item in purchases_data),
        }
    )


@app.post("/api/media")
def api_add_media():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    media_type = str(payload.get("media_type", "")).strip()
    file_id = str(payload.get("file_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()

    try:
        price = int(payload.get("price", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Գինը պետք է թիվ լինի։"}), 400

    if media_type not in {"video", "photo"}:
        return jsonify({"error": "Տեսակը պետք է լինի video կամ photo։"}), 400
    if not file_id:
        return jsonify({"error": "file_id-ը պարտադիր է։"}), 400
    if not title:
        return jsonify({"error": "Վերնագիրը պարտադիր է։"}), 400
    if not 0 <= price <= 10000:
        return jsonify({"error": "Գինը պետք է լինի 0-ից 10000։"}), 400

    item = {
        "id": next_media_id(),
        "media_type": media_type,
        "file_id": file_id,
        "title": title,
        "description": description,
        "price": price,
        "created_at": int(time.time()),
    }
    media_data.append(item)
    save_json(MEDIA_FILE, media_data)
    return jsonify(item), 201


@app.delete("/api/media/<int:media_id>")
def api_delete_media(media_id: int):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    if not get_media(media_id):
        return jsonify({"error": "Նյութը չի գտնվել։"}), 404

    media_data[:] = [item for item in media_data if int(item["id"]) != media_id]
    save_json(MEDIA_FILE, media_data)
    return jsonify({"ok": True})


def run_web():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


async def main():
    Thread(target=run_web, daemon=True).start()
    log.info("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
