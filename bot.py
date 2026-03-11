# bot.py
import asyncio
import logging
import os
import shutil
from pathlib import Path

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, ReplyKeyboardRemove

import parser
import exporter

# Configure logging
logging.basicConfig(level=logging.INFO)

# Get BOT_TOKEN from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN provided in environment variables")

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DATA_DIR = Path("data")

def clear_data_dir():
    """Удаляет только файлы внутри DATA_DIR, не трогая саму директорию.
    Необходимо, т.к. папка может быть смонтирована как Docker volume."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in DATA_DIR.iterdir():
        if f.is_file():
            f.unlink()
        elif f.is_dir():
            shutil.rmtree(f)

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class CalcState(StatesGroup):
    waiting_for_clear_confirm = State()

def get_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="ℹ️ Инструкция")],
            [KeyboardButton(text="🗑 Очистить файлы")],
            [KeyboardButton(text="📊 Провести вычисления")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_confirm_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да, очистить")],
            [KeyboardButton(text="Нет, оставить")]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("⌨️", reply_markup=get_keyboard())

async def show_main_menu(message: types.Message):
    """Принудительно скрывает текущую клавиатуру и показывает основное меню."""
    await message.answer("⌨️", reply_markup=get_keyboard())

@dp.message(F.document)
async def handle_document(message: types.Message):
    document = message.document
    if not document.file_name.endswith('.json'):
        await message.answer("Ошибка: Пожалуйста, отправляйте только файлы формата .json")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    file_path = DATA_DIR / document.file_name
    
    # Download the file
    file_id = document.file_id
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, destination=file_path)
    
    await message.answer(f"Файл {document.file_name} успешно сохранен! Всего файлов: {len(list(DATA_DIR.glob('*.json')))}")

@dp.message(F.text == "ℹ️ Инструкция")
async def show_instruction(message: types.Message):
    await message.answer(
        "📚 **Инструкция по использованию бота:**\n\n"
        "1️⃣ **Очистка (ВАЖНО):** Перед загрузкой новых файлов *обязательно* нажимайте «🗑 Очистить файлы».\n"
        "   Это нужно, чтобы старые данные с прошлого раза не смешались с новыми и не испортили вычисления.\n\n"
        "2️⃣ **Загрузка:** Отправьте боту один или несколько `.json` файлов.\n\n"
        "3️⃣ **Обработка:** Как только все нужные файлы загружены, нажмите «📊 Провести вычисления».\n\n"
        "Бот обработает все текущие файлы в памяти и отправит готовую таблицу Excel (.xlsx)."
    )

@dp.message(F.text == "🗑 Очистить файлы")
async def clear_files(message: types.Message):
    clear_data_dir()
    await message.answer("✅ База пуста! Все старые файлы удалены.")
    await cmd_start(message)

@dp.message(F.text == "📊 Провести вычисления")
async def process_calculations_start(message: types.Message, state: FSMContext):
    # Считаем количество файлов
    json_files = list(DATA_DIR.glob("*.json"))
    files_count = len(json_files)
    
    if files_count == 0:
        await message.answer("⚠️ Нет загруженных .json файлов для вычислений. Сначала отправьте файлы.")
        await cmd_start(message)
        return
        
    await message.answer(
        f"📊 Обнаружено файлов: {files_count}\n\n"
        "❓ Вы хотите очистить старые файлы памяти **ПЕРЕД** этими вычислениями?\n"
        "(Если вы не делали очистку перед загрузкой текущих файлов, лучше сделать это сейчас, чтобы старые данные не попали в эту таблицу)",
        reply_markup=get_confirm_keyboard()
    )
    await state.set_state(CalcState.waiting_for_clear_confirm)

@dp.message(CalcState.waiting_for_clear_confirm)
async def process_calculations_finish(message: types.Message, state: FSMContext):
    if message.text not in ["Да, очистить", "Нет, оставить"]:
        await message.answer("Пожалуйста, воспользуйтесь кнопками ниже.", reply_markup=get_confirm_keyboard())
        return
        
    if message.text == "Да, очистить":
        clear_data_dir()
        await state.clear()
        await message.answer("🧹 База очищена", reply_markup=ReplyKeyboardRemove())
        await show_main_menu(message)
        return

    # Если "Нет, оставить" - сначала сбрасываем клавиатуру, затем считаем
    await message.answer("⏳ Провожу вычисления...", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    
    try:
        results = parser.process_directory(DATA_DIR)
        
        if not results:
            await message.answer("❌ Не удалось извлечь данные из загруженных файлов. Возможно, они пустые или имеют неверный формат.", reply_markup=get_keyboard())
            return
            
        excel_file = exporter.generate_excel(results)
        
        input_file = BufferedInputFile(
            excel_file.read(),
            filename="top_holder_summaries.xlsx"
        )
        
        await message.answer_document(
            document=input_file,
            caption="Вот результаты вычислений!",
            reply_markup=get_keyboard()
        )
    except Exception as e:
        logging.error(f"Error during calculation: {e}")
        await message.answer(f"⚠️ Произошла непредвиденная ошибка при вычислениях: {e}", reply_markup=get_keyboard())

@dp.message(F.text)
async def handle_unknown_text(message: types.Message):
    await message.answer("⚠️ Такой команды нет. Пожалуйста, воспользуйтесь кнопками меню.")
    # Инициируем команду /start (вызываем тот же хендлер)
    await cmd_start(message)

async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
