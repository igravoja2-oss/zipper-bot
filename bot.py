
import asyncio
import logging
import shutil
import zipfile
import os

from pathlib import Path, PurePosixPath

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()


# ==============================
# CONFIG
# ==============================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Add it to the environment or to a .env file."
    )

MAX_FILES = 100
MAX_UNPACKED_SIZE = 100 * 1024 * 1024
MAX_FILE_SIZE = 50 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_states = {}
BASE_DIR = Path("temp")
BASE_DIR.mkdir(exist_ok=True)


# ==============================
# KEYBOARDS
# ==============================

def main_keyboard():
    kb = InlineKeyboardBuilder()

    kb.button(
        text="🗜️ Сжать файлы",
        callback_data="compress"
    )

    kb.button(
        text="📂 Распаковать ZIP",
        callback_data="extract"
    )

    kb.button(
        text="🔍 Анализ архива",
        callback_data="analyze"
    )

    kb.button(
        text="ℹ️ О боте",
        callback_data="about"
    )

    kb.adjust(2, 1, 1)
    return kb.as_markup()


def back_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🏠 Главное меню",
        callback_data="home"
    )
    return kb.as_markup()


# ==============================
# START
# ==============================

@dp.message(CommandStart())
async def start(message: Message):

    user_states.pop(message.from_user.id, None)

    await message.answer(
        "🗜️ <b>ZIPPER BOT</b>\n"
        "<i>Free Archive Manager</i>\n\n"
        "Привет! Я бесплатный архиватор.\n\n"
        "Выбери нужную операцию:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):

    user_states.pop(call.from_user.id, None)

    await call.message.edit_text(
        "🗜️ <b>ZIPPER BOT</b>\n\n"
        "Выбери операцию:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

    await call.answer()


# ==============================
# ABOUT
# ==============================

@dp.callback_query(F.data == "about")
async def about(call: CallbackQuery):

    await call.message.answer(
        "🗜️ <b>ZIPPER BOT v1.0</b>\n\n"
        "📦 ZIP compression\n"
        "📂 ZIP extraction\n"
        "🔍 Archive analysis\n"
        "📊 Archive statistics\n"
        "🛡️ ZIP integrity check\n\n"
        "Python + Aiogram 3.x\n"
        "Полностью бесплатно.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

    await call.answer()


# ==============================
# COMPRESS
# ==============================

@dp.callback_query(F.data == "compress")
async def compress_start(call: CallbackQuery):

    uid = call.from_user.id

    user_states[uid] = {
        "mode": "compress",
        "files": []
    }

    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Создать архив",
        callback_data="finish_compress"
    )
    kb.button(
        text="❌ Отмена",
        callback_data="home"
    )
    kb.adjust(1)

    await call.message.answer(
        "🗜️ <b>Создание ZIP-архива</b>\n\n"
        "Отправляй мне файлы по одному "
        "или несколько подряд.\n\n"
        "Когда закончишь, нажми кнопку "
        "«Создать архив».",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

    await call.answer()


@dp.callback_query(F.data == "finish_compress")
async def finish_compress(call: CallbackQuery):

    uid = call.from_user.id
    state = user_states.get(uid)

    if not state or state["mode"] != "compress":
        await call.answer("Сессия не найдена.", show_alert=True)
        return

    files = state["files"]

    if not files:
        await call.answer("Сначала отправь файлы!", show_alert=True)
        return

    if len(files) > MAX_FILES:
        await call.answer("Слишком много файлов.", show_alert=True)
        return

    await call.answer("Создаю архив...")

    archive_path = BASE_DIR / f"{uid}_archive.zip"

    try:
        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6
        ) as archive:

            for item in files:
                archive.write(
                    item["path"],
                    arcname=item["name"]
                )

        await call.message.answer_document(
            FSInputFile(archive_path),
            caption=(
                "✅ <b>Архив создан!</b>\n\n"
                f"📁 Файлов: {len(files)}\n"
                f"📦 Размер: {format_size(archive_path.stat().st_size)}"
            ),
            parse_mode="HTML"
        )

    except Exception:
        logging.exception("Compression error")
        await call.message.answer("❌ Ошибка создания архива.")

    finally:
        shutil.rmtree(BASE_DIR / str(uid), ignore_errors=True)
        archive_path.unlink(missing_ok=True)
        user_states.pop(uid, None)


# ==============================
# RECEIVE FILES
# ==============================

@dp.message(F.document)
async def receive_document(message: Message):

    uid = message.from_user.id
    state = user_states.get(uid)

    if not state:
        await message.answer(
            "Сначала выбери операцию через /start."
        )
        return

    mode = state["mode"]

    filename = Path(
        message.document.file_name or "file"
    ).name

    if mode == "compress":

        if len(state["files"]) >= MAX_FILES:
            await message.answer("❌ Максимум 100 файлов.")
            return

        if message.document.file_size > MAX_FILE_SIZE:
            await message.answer("❌ Файл слишком большой.")
            return

        user_dir = BASE_DIR / str(uid)
        user_dir.mkdir(exist_ok=True)

        index = len(state["files"])
        path = user_dir / f"{index}_{filename}"

        try:
            await bot.download(
                message.document,
                destination=path
            )

            state["files"].append({
                "path": path,
                "name": filename
            })

            await message.answer(
                f"✅ Добавлен: <code>{filename}</code>\n"
                f"Файлов: {len(state['files'])}",
                parse_mode="HTML"
            )

        except Exception:
            logging.exception("Download error")
            await message.answer("❌ Не удалось скачать файл.")

    elif mode in ("extract", "analyze"):

        if not filename.lower().endswith(".zip"):
            await message.answer("❌ Отправь ZIP-архив.")
            return

        await process_archive(message, mode)


# ==============================
# EXTRACT / ANALYZE MENU
# ==============================

@dp.callback_query(F.data == "extract")
async def extract_start(call: CallbackQuery):

    user_states[call.from_user.id] = {
        "mode": "extract"
    }

    await call.message.answer(
        "📂 <b>Распаковка ZIP</b>\n\n"
        "Отправь ZIP-архив.\n"
        "Я извлеку его содержимое и отправлю файлы.",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

    await call.answer()


@dp.callback_query(F.data == "analyze")
async def analyze_start(call: CallbackQuery):

    user_states[call.from_user.id] = {
        "mode": "analyze"
    }

    await call.message.answer(
        "🔍 <b>Анализ архива</b>\n\n"
        "Отправь ZIP-файл.\n\n"
        "Я покажу:\n"
        "• Структуру папок\n"
        "• Количество файлов\n"
        "• Общий размер\n"
        "• Степень сжатия\n"
        "• Результат проверки целостности",
        parse_mode="HTML",
        reply_markup=back_keyboard()
    )

    await call.answer()


# ==============================
# HELPERS
# ==============================

def format_size(size):

    units = ["B", "KB", "MB", "GB"]

    value = float(size)

    for unit in units:
        if value < 1024 or unit == "GB":
            return f"{value:.2f} {unit}"

        value /= 1024

    return f"{value:.2f} GB"


def safe_member_path(name):

    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe archive path")

    if not path.parts or ":" in path.parts[0]:
        raise ValueError("Unsafe archive path")

    return Path(*path.parts)


def validate_archive(archive):

    infos = archive.infolist()

    if len(infos) > MAX_FILES:
        raise ValueError("Too many archive entries")

    total_size = 0

    for info in infos:

        if info.flag_bits & 0x1:
            raise ValueError("Password-protected archive")

        safe_member_path(info.filename)

        if info.file_size > MAX_FILE_SIZE:
            raise ValueError("File too large")

        total_size += info.file_size

        if total_size > MAX_UNPACKED_SIZE:
            raise ValueError("Archive is too large")

        if info.file_size > 0:
            ratio = info.compress_size / info.file_size

            if ratio < 0.001:
                raise ValueError("Suspicious compression ratio")

    return infos


# ==============================
# ARCHIVE PROCESSOR
# ==============================

async def process_archive(message: Message, mode):

    uid = message.from_user.id

    user_dir = BASE_DIR / str(uid)
    user_dir.mkdir(exist_ok=True)

    archive_path = user_dir / "input.zip"

    try:

        await bot.download(
            message.document,
            destination=archive_path
        )

        await message.answer("⏳ Проверяю архив...")

        with zipfile.ZipFile(archive_path, "r") as archive:

            infos = validate_archive(archive)

            # ======================
            # ANALYZE
            # ======================

            if mode == "analyze":

                bad_file = archive.testzip()

                files = [
                    x for x in infos
                    if not x.is_dir()
                ]

                folders = [
                    x for x in infos
                    if x.is_dir()
                ]

                original_size = sum(x.file_size for x in files)
                compressed_size = sum(x.compress_size for x in files)

                if bad_file:
                    integrity = "❌ Повреждён"
                else:
                    integrity = "✅ Исправен"

                if original_size:
                    ratio = (
                        100 - compressed_size / original_size * 100
                    )
                else:
                    ratio = 0

                tree = []

                for info in infos[:70]:

                    if info.is_dir():
                        tree.append(f"📁 {info.filename}")
                    else:
                        tree.append(
                            f"📄 {info.filename} "
                            f"({format_size(info.file_size)})"
                        )

                if len(infos) > 70:
                    tree.append(
                        f"... и ещё {len(infos) - 70} элементов"
                    )

                report = (
                    "🔍 <b>ZIPPER ANALYSIS</b>\n\n"
                    f"📦 <b>{archive_path.name}</b>\n\n"
                    f"🛡️ Целостность: {integrity}\n"
                    f"📄 Файлов: {len(files)}\n"
                    f"📁 Папок: {len(folders)}\n\n"
                    f"📊 Исходный размер: {format_size(original_size)}\n"
                    f"🗜️ Размер архива: {format_size(compressed_size)}\n"
                    f"📉 Сжатие: {ratio:.1f}%\n\n"
                    "<b>Структура архива:</b>\n"
                    "<pre>"
                    + "\n".join(tree)
                    + "</pre>"
                )

                await message.answer(
                    report,
                    parse_mode="HTML"
                )

            # ======================
            # EXTRACT
            # ======================

            elif mode == "extract":

                extracted_dir = user_dir / "extracted"
                extracted_dir.mkdir(exist_ok=True)

                extracted = []

                for info in infos:

                    if info.is_dir():
                        continue

                    relative = safe_member_path(info.filename)
                    target = extracted_dir / relative

                    target.parent.mkdir(
                        parents=True,
                        exist_ok=True
                    )

                    with archive.open(info) as source:
                        with open(target, "wb") as destination:
                            shutil.copyfileobj(source, destination)

                    extracted.append((target, info.filename))

                if not extracted:
                    await message.answer("Архив пустой.")
                    return

                await message.answer(
                    f"📂 Архив распакован!\n"
                    f"Файлов: {len(extracted)}\n\n"
                    "Отправляю содержимое..."
                )

                for path, original_name in extracted:

                    await message.answer_document(
                        FSInputFile(path),
                        caption=f"📄 {original_name}"
                    )

                await message.answer(
                    "✅ Распаковка завершена!",
                    reply_markup=main_keyboard()
                )

    except zipfile.BadZipFile:
        await message.answer("❌ Файл не является корректным ZIP.")

    except ValueError as error:
        await message.answer(
            f"❌ Архив отклонён: {error}"
        )

    except Exception:
        logging.exception("Archive processing error")
        await message.answer(
            "❌ Произошла ошибка при обработке архива."
        )

    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(uid, None)


# ==============================
# RUN
# ==============================

async def main():

    print("==========================")
    print("       ZIPPER BOT")
    print("     VERSION 1.0")
    print("==========================")
    print("Bot is running!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
