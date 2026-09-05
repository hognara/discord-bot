import discord
import os
import random

from discord.ext import commands
from discord import app_commands
from typing import Optional

# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

# Если хочешь использовать конкретную категорию,
# вставь сюда ID категории.
#
# Например:
# VOICE_CATEGORY_ID = 0
#
# Если оставить  — бот будет искать/создавать категорию "Сборы".

VOICE_CATEGORY_ID = 0

VOICE_CATEGORY_NAME = "Сборы"

# ID ОБЩЕГО ГОЛОСОВОГО КАНАЛА
# Сюда будут возвращаться игроки после окончания 5x5.
GENERAL_VOICE_ID = 123456789012345678

# Через сколько часов автоматически удалить сбор
GATHERING5X5_TIMEOUT_HOURS = 6

# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

intents.members = True
intents.voice_states = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# ХРАНЕНИЕ СБОРОВ
# ============================================================

gatherings = {}

next_gathering_id = 1


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_gathering(gathering_id: int):
    return gatherings.get(gathering_id)


def get_role(
    guild: discord.Guild,
    role_id: Optional[int]
):
    if role_id is None:
        return None

    return guild.get_role(role_id)


# ============================================================
# EMBED СБОРА
# ============================================================

def build_gathering_embed(
    gathering: dict,
    guild: discord.Guild
):

    participants = gathering["participants"]

    max_players = gathering["max_players"]

    role = get_role(
        guild,
        gathering["role_id"]
    )

    # --------------------------------------------------------
    # Роль
    # --------------------------------------------------------

    if role:
        role_text = role.mention
    else:
        role_text = "Не указана"

    # --------------------------------------------------------
    # Список игроков
    # --------------------------------------------------------

    if participants:

        lines = []

        for i, user_id in enumerate(
            participants,
            start=1
        ):

            member = guild.get_member(
                user_id
            )

            if member:

                lines.append(
                    f"`{i}.` {member.mention}"
                )

            else:

                lines.append(
                    f"`{i}.` <@{user_id}>"
                )

        participant_text = "\n".join(
            lines
        )

    else:

        participant_text = (
            "Пока никто не записался."
        )

    # --------------------------------------------------------
    # Статус
    # --------------------------------------------------------

    if len(participants) >= max_players:

        status = (
            "🟢 **Игроки набраны! Можно начинать.**"
        )

    else:

        status = (
            f"🟡 **Нужно ещё "
            f"{max_players - len(participants)} "
            f"игрок(а/ов).**"
        )

    # --------------------------------------------------------
    # Embed
    # --------------------------------------------------------

    embed = discord.Embed(

        title=f"🎮 {gathering['name']}",

        description=(
            "Нажмите **«Участвовать»**, чтобы "
            "попасть в список игроков.\n\n"
            f"{status}"
        ),

        color=discord.Color.blurple()
    )

    embed.add_field(

        name="👥 Игроки",

        value=(
            f"**{len(participants)} / "
            f"{max_players}**"
        ),

        inline=True
    )

    embed.add_field(

        name="🏷 Тег участников",

        value=role_text,

        inline=True
    )

    embed.add_field(

        name="⏰ Время",

        value=gathering["time"],

        inline=True
    )

    embed.add_field(

        name="📋 Участники",

        value=participant_text,

        inline=False
    )

    embed.set_footer(

        text=f"Сбор №{gathering['id']}"
    )

    return embed


# ============================================================
# СОЗДАНИЕ VIEW
# ============================================================

def build_gathering_view(
    gathering_id: int
):

    gathering = gatherings[
        gathering_id
    ]

    view = GatheringView(

        gathering_id=gathering_id,

        started=gathering["started"],

        full=(
            len(gathering["participants"])
            >= gathering["max_players"]
        )
    )

    return view


# ============================================================
# ОБНОВЛЕНИЕ СООБЩЕНИЯ СБОРА
# ============================================================

async def update_gathering_message(
    gathering_id: int
):

    gathering = gatherings.get(
        gathering_id
    )

    if not gathering:
        return

    guild = bot.get_guild(
        gathering["guild_id"]
    )

    if not guild:
        return

    channel = guild.get_channel(
        gathering["channel_id"]
    )

    if not channel:
        return

    try:

        message = await channel.fetch_message(
            gathering["message_id"]
        )

    except discord.NotFound:

        return

    except discord.Forbidden:

        return

    embed = build_gathering_embed(
        gathering,
        guild
    )

    view = build_gathering_view(
        gathering_id
    )

    try:

        await message.edit(

            embed=embed,

            view=view
        )

    except discord.NotFound:

        pass


# ============================================================
# ПОЛУЧЕНИЕ КАТЕГОРИИ ДЛЯ ВОЙСОВ
# ============================================================

async def get_voice_category(
    guild: discord.Guild
):

    # --------------------------------------------------------
    # Используем указанную категорию
    # --------------------------------------------------------

    if VOICE_CATEGORY_ID != 0:

        category = guild.get_channel(
            VOICE_CATEGORY_ID
        )

        if isinstance(
            category,
            discord.CategoryChannel
        ):

            return category

    # --------------------------------------------------------
    # Ищем категорию "Сборы"
    # --------------------------------------------------------

    for category in guild.categories:

        if category.name == VOICE_CATEGORY_NAME:

            return category

    # --------------------------------------------------------
    # Создаём категорию
    # --------------------------------------------------------

    try:

        category = await guild.create_category(

            VOICE_CATEGORY_NAME,

            reason=(
                "Создание категории "
                "для сборов"
            )
        )

        return category

    except discord.Forbidden:

        return None


# ============================================================
# MODAL — СОЗДАНИЕ СБОРА
# ============================================================

class GatheringModal(
    discord.ui.Modal
):

    def __init__(self):

        super().__init__(
            title="🎮 Создание сбора"
        )

        # ----------------------------------------------------
        # Название
        # ----------------------------------------------------

        self.event_name = discord.ui.TextInput(

            label="Название события",

            placeholder=(
                "Например: Игра в CS2"
            ),

            required=True,

            max_length=100
        )

        # ----------------------------------------------------
        # Количество игроков
        # ----------------------------------------------------

        self.players_count = discord.ui.TextInput(

            label="Количество игроков",

            placeholder="Например: 5",

            required=True,

            max_length=3
        )

        # ----------------------------------------------------
        # Роль
        # ----------------------------------------------------

        self.role = discord.ui.TextInput(

            label="Тег участников",

            placeholder=(
                "ID роли или @роль"
            ),

            required=False,

            max_length=100
        )

        # ----------------------------------------------------
        # Время
        # ----------------------------------------------------

        self.event_time = discord.ui.TextInput(

            label="Время",

            placeholder="Например: 21:00",

            required=True,

            max_length=30
        )

        self.add_item(
            self.event_name
        )

        self.add_item(
            self.players_count
        )

        self.add_item(
            self.role
        )

        self.add_item(
            self.event_time
        )

    # ========================================================
    # СОЗДАНИЕ СБОРА
    # ========================================================

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        global next_gathering_id

        # ----------------------------------------------------
        # Количество игроков
        # ----------------------------------------------------

        try:

            players_count = int(
                self.players_count.value
            )

        except ValueError:

            await interaction.response.send_message(

                "❌ Количество игроков "
                "должно быть числом.",

                ephemeral=True
            )

            return

        if players_count < 1:

            await interaction.response.send_message(

                "❌ Количество игроков "
                "должно быть больше 0.",

                ephemeral=True
            )

            return

        if players_count > 99:

            await interaction.response.send_message(

                "❌ Максимальное количество "
                "игроков — 99.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Получаем роль
        # ----------------------------------------------------

        role_id = None

        role_text = self.role.value.strip()

        if role_text:

            cleaned = (
                role_text
                .replace("<@&", "")
                .replace(">", "")
                .strip()
            )

            try:

                possible_role_id = int(
                    cleaned
                )

            except ValueError:

                await interaction.response.send_message(

                    "❌ Тег роли указан неправильно.\n\n"
                    "Укажи **ID роли** или вставь "
                    "упоминание роли.",

                    ephemeral=True
                )

                return

            role = interaction.guild.get_role(
                possible_role_id
            )

            if not role:

                await interaction.response.send_message(

                    "❌ Я не нашёл такую "
                    "роль на сервере.",

                    ephemeral=True
                )

                return

            role_id = role.id

        # ----------------------------------------------------
        # ID сбора
        # ----------------------------------------------------

        gathering_id = next_gathering_id

        next_gathering_id += 1

        # ----------------------------------------------------
        # Создаём объект сбора
        # ----------------------------------------------------

        gathering = {

            "id": gathering_id,

            "guild_id": interaction.guild.id,

            "channel_id": interaction.channel.id,

            "message_id": 0,

            "name": self.event_name.value,

            "max_players": players_count,

            "role_id": role_id,

            "time": self.event_time.value,

            "participants": [],

            "started": False,

            "voice_id": None,

            "creator_id": interaction.user.id,

            # Важно:
            # чтобы сообщение "СБОР НАБРАН"
            # не отправлялось повторно

            "full_announced": False
        }

        gatherings[
            gathering_id
        ] = gathering

        # ----------------------------------------------------
        # Создаём Embed
        # ----------------------------------------------------

        embed = build_gathering_embed(

            gathering,

            interaction.guild
        )

        view = build_gathering_view(

            gathering_id
        )

        # ----------------------------------------------------
        # Отправляем сообщение
        # ----------------------------------------------------

        await interaction.response.send_message(

            embed=embed,

            view=view
        )

        message = await interaction.original_response()

        gathering["message_id"] = message.id

        # ----------------------------------------------------
        # Упоминаем роль
        # ----------------------------------------------------

        if role_id:

            role = interaction.guild.get_role(
                role_id
            )

            if role:

                try:

                    await message.edit(

                        content=role.mention,

                        embed=embed,

                        view=view
                    )

                except discord.Forbidden:

                    pass


# ============================================================
# VIEW — СОЗДАНИЕ СБОРА
# ============================================================

class CreateGatheringView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    @discord.ui.button(

        label="🎮 Создать сбор",

        style=discord.ButtonStyle.primary
    )

    async def create_gathering(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button
    ):

        await interaction.response.send_modal(

            GatheringModal()
        )


# ============================================================
# VIEW — КНОПКИ СБОРА
# ============================================================

class GatheringView(
    discord.ui.View
):

    def __init__(

        self,

        gathering_id: int,

        started: bool,

        full: bool
    ):

        super().__init__(
            timeout=None
        )

        self.gathering_id = gathering_id

        # ====================================================
        # КНОПКА УЧАСТВОВАТЬ
        # ====================================================

        participate_button = discord.ui.Button(

            label="Участвовать",

            emoji="✅",

            style=discord.ButtonStyle.success,

            custom_id=(
                f"gathering_join_"
                f"{gathering_id}"
            )
        )

        participate_button.callback = (
            self.join_callback
        )

        self.add_item(
            participate_button
        )

        # ====================================================
        # КНОПКА ВЫЙТИ
        # ====================================================

        leave_button = discord.ui.Button(

            label="Выйти",

            emoji="🚪",

            style=discord.ButtonStyle.secondary,

            custom_id=(
                f"gathering_leave_"
                f"{gathering_id}"
            )
        )

        leave_button.callback = (
            self.leave_callback
        )

        self.add_item(
            leave_button
        )

        # ====================================================
        # КНОПКА НАЧАТЬ
        # ====================================================

        start_button = discord.ui.Button(

            label="Начать",

            emoji="🚀",

            style=discord.ButtonStyle.primary,

            custom_id=(
                f"gathering_start_"
                f"{gathering_id}"
            ),

            disabled=(
                started
                or not full
            )
        )

        start_button.callback = (
            self.start_callback
        )

        self.add_item(
            start_button
        )

    # ========================================================
    # УЧАСТВОВАТЬ
    # ========================================================

    async def join_callback(

        self,

        interaction: discord.Interaction
    ):

        gathering = gatherings.get(

            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Этот сбор больше "
                "не существует.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Сбор уже начался
        # ----------------------------------------------------

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Сбор уже начался.",

                ephemeral=True
            )

            return

        participants = gathering[
            "participants"
        ]

        # ----------------------------------------------------
        # Игрок уже записан
        # ----------------------------------------------------

        if interaction.user.id in participants:

            await interaction.response.send_message(

                "⚠️ Ты уже участвуешь "
                "в этом сборе.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Мест больше нет
        # ----------------------------------------------------

        if len(participants) >= gathering[
            "max_players"
        ]:

            await interaction.response.send_message(

                "❌ В этом сборе уже набрано "
                "нужное количество игроков.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Добавляем игрока
        # ----------------------------------------------------

        participants.append(

            interaction.user.id
        )

        # ====================================================
        # ПРОВЕРЯЕМ — ВСЕ ЛИ МЕСТА ЗАПОЛНЕНЫ
        # ====================================================

        if (
            len(participants)
            >= gathering["max_players"]
        ):

            # ------------------------------------------------
            # Защита от повторного сообщения
            # ------------------------------------------------

            if not gathering[
                "full_announced"
            ]:

                gathering[
                    "full_announced"
                ] = True

                # --------------------------------------------
                # Создаём упоминания
                # --------------------------------------------

                mentions = " ".join(

                    f"<@{user_id}>"

                    for user_id in participants
                )

                # --------------------------------------------
                # Ответ тому, кто нажал
                # --------------------------------------------

                await interaction.response.send_message(

                    "✅ Ты успешно записался в сбор!",

                    ephemeral=True
                )

                # --------------------------------------------
                # Сообщение всем игрокам
                # --------------------------------------------

                await interaction.channel.send(

                    f"🎉 **СБОР НАБРАН!**\n\n"

                    f"{mentions}\n\n"

                    f"👥 Все **"
                    f"{len(participants)}"
                    f"/"
                    f"{gathering['max_players']}"
                    f"** игроков собрались!\n\n"

                    f"🔊 **Можете заходить "
                    f"и начинать!**"
                )

            else:

                await interaction.response.send_message(

                    "✅ Ты успешно записался в сбор!",

                    ephemeral=True
                )

        else:

            # ------------------------------------------------
            # Обычный ответ
            # ------------------------------------------------

            await interaction.response.send_message(

                "✅ Ты успешно записался в сбор!",

                ephemeral=True
            )

        # ----------------------------------------------------
        # Обновляем Embed
        # ----------------------------------------------------

        await update_gathering_message(

            self.gathering_id
        )

    # ========================================================
    # ВЫЙТИ
    # ========================================================

    async def leave_callback(

        self,

        interaction: discord.Interaction
    ):

        gathering = gatherings.get(

            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Этот сбор больше "
                "не существует.",

                ephemeral=True
            )

            return

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Сбор уже начался.",

                ephemeral=True
            )

            return

        user_id = interaction.user.id

        if user_id not in gathering[
            "participants"
        ]:

            await interaction.response.send_message(

                "⚠️ Ты не участвуешь "
                "в этом сборе.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Удаляем игрока
        # ----------------------------------------------------

        gathering[
            "participants"
        ].remove(user_id)

        # ----------------------------------------------------
        # Если после выхода сбор снова неполный,
        # разрешаем повторное объявление.
        # ----------------------------------------------------

        if len(
            gathering["participants"]
        ) < gathering["max_players"]:

            gathering[
                "full_announced"
            ] = False

        await interaction.response.send_message(

            "🚪 Ты вышел из сбора.",

            ephemeral=True
        )

        await update_gathering_message(

            self.gathering_id
        )

    # ========================================================
    # НАЧАТЬ
    # ========================================================

    async def start_callback(

        self,

        interaction: discord.Interaction
    ):

        gathering = gatherings.get(

            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Этот сбор больше "
                "не существует.",

                ephemeral=True
            )

            return

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Сбор уже был начат.",

                ephemeral=True
            )

            return

        # ----------------------------------------------------
        # Проверяем количество игроков
        # ----------------------------------------------------

        if len(
            gathering["participants"]
        ) < gathering["max_players"]:

            await interaction.response.send_message(

                "❌ Пока недостаточно игроков.",

                ephemeral=True
            )

            return

        # ====================================================
        # ПРОВЕРКА ПРАВ
        # ====================================================

        is_creator = (

            interaction.user.id
            == gathering["creator_id"]
        )

        is_admin = (

            interaction.user.guild_permissions
            .administrator
        )

        is_participant = (

            interaction.user.id
            in gathering["participants"]
        )

        if not (

            is_creator
            or is_admin
            or is_participant
        ):

            await interaction.response.send_message(

                "❌ Начать сбор может только "
                "создатель, администратор "
                "или участник сбора.",

                ephemeral=True
            )

            return

        # ====================================================
        # ПОЛУЧАЕМ КАТЕГОРИЮ
        # ====================================================

        category = await get_voice_category(

            interaction.guild
        )

        if not category:

            await interaction.response.send_message(

                "❌ Я не могу создать "
                "голосовой канал.\n\n"
                "Проверь право "
                "**Manage Channels**.",

                ephemeral=True
            )

            return

        # ====================================================
        # СОЗДАЁМ ВОЙС
        # ====================================================

        voice_name = (

            f"🎮 {gathering['name']}"
        )

        try:

            voice_channel = (

                await interaction.guild.create_voice_channel(

                    name=voice_name[:100],

                    category=category,

                    reason=(
                        f"Запуск сбора "
                        f"№{self.gathering_id}"
                    )
                )
            )

        except discord.Forbidden:

            await interaction.response.send_message(

                "❌ У бота нет права "
                "**Manage Channels**.",

                ephemeral=True
            )

            return

        except discord.HTTPException as error:

            await interaction.response.send_message(

                f"❌ Не удалось создать войс.\n"
                f"Ошибка: `{error}`",

                ephemeral=True
            )

            return

        # ====================================================
        # СОХРАНЯЕМ ИНФОРМАЦИЮ
        # ====================================================

        gathering[
            "started"
        ] = True

        gathering[
            "voice_id"
        ] = voice_channel.id

        # ====================================================
        # ОТВЕТ
        # ====================================================

        await interaction.response.send_message(

            f"🚀 **Сбор начался!**\n\n"
            f"🔊 Голосовой канал: "
            f"{voice_channel.mention}",

            ephemeral=True
        )

        # ====================================================
        # ПЕРЕМЕЩАЕМ ИГРОКОВ
        # ====================================================

        moved = 0

        not_in_voice = 0

        failed = 0

        for user_id in gathering[
            "participants"
        ]:

            member = interaction.guild.get_member(

                user_id
            )

            if not member:

                continue

            # ------------------------------------------------
            # Игрок не находится в голосовом
            # ------------------------------------------------

            if member.voice is None:

                not_in_voice += 1

                continue

            try:

                await member.move_to(

                    voice_channel,

                    reason=(
                        f"Перемещение в сбор "
                        f"№{self.gathering_id}"
                    )
                )

                moved += 1

            except discord.Forbidden:

                failed += 1

            except discord.HTTPException:

                failed += 1

        # ====================================================
        # ОБНОВЛЯЕМ СООБЩЕНИЕ
        # ====================================================

        await update_gathering_message(

            self.gathering_id
        )

        # ====================================================
        # ИНФОРМАЦИЯ О ЗАПУСКЕ
        # ====================================================

        text = (

            f"🚀 **Сбор запущен!**\n\n"

            f"🎮 **{gathering['name']}**\n"

            f"🔊 Войс: "
            f"{voice_channel.mention}\n"

            f"👥 Участников: "
            f"{len(gathering['participants'])}\n\n"

            f"✅ Перемещено: {moved}\n"

            f"⚠️ Не были в войсе: "
            f"{not_in_voice}\n"

            f"❌ Ошибок перемещения: "
            f"{failed}"
        )

        try:

            await interaction.channel.send(

                text
            )

        except discord.Forbidden:

            pass


# ============================================================
# SLASH COMMAND /СБОР
# ============================================================

@bot.tree.command(

    name="сбор",

    description="Создать новый сбор игроков"
)

@app_commands.guild_only()

async def gathering_command(

    interaction: discord.Interaction
):

    embed = discord.Embed(

        title="🎮 Создание сбора",

        description=(

            "Нажми кнопку ниже, "
            "чтобы создать новый сбор.\n\n"

            "Тебе потребуется указать:\n"

            "• название события\n"

            "• количество игроков\n"

            "• роль участников\n"

            "• время начала"
        ),

        color=discord.Color.blurple()
    )

    view = CreateGatheringView()

    await interaction.response.send_message(

        embed=embed,

        view=view,

        ephemeral=True
    )


# ============================================================
# КОМАНДА УДАЛЕНИЯ СБОРА
# ============================================================

@bot.tree.command(

    name="удалить_сбор",

    description="Удалить сбор"
)

@app_commands.describe(

    gathering_id="Номер сбора"
)

@app_commands.guild_only()

async def delete_gathering(

    interaction: discord.Interaction,

    gathering_id: int
):

    # --------------------------------------------------------
    # Проверяем права
    # --------------------------------------------------------

    if not (

        interaction.user.guild_permissions
        .manage_guild

        or

        interaction.user.guild_permissions
        .administrator
    ):

        await interaction.response.send_message(

            "❌ У тебя нет прав.",

            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Ищем сбор
    # --------------------------------------------------------

    gathering = gatherings.get(

        gathering_id
    )

    if not gathering:

        await interaction.response.send_message(

            "❌ Сбор с таким ID не найден.",

            ephemeral=True
        )

        return

    # --------------------------------------------------------
    # Удаляем войс
    # --------------------------------------------------------

    if gathering["voice_id"]:

        voice = interaction.guild.get_channel(

            gathering["voice_id"]
        )

        if voice:

            try:

                await voice.delete(

                    reason="Удаление сбора"
                )

            except discord.HTTPException:

                pass

    # --------------------------------------------------------
    # Удаляем сбор
    # --------------------------------------------------------

    del gatherings[
        gathering_id
    ]

    await interaction.response.send_message(

        f"✅ Сбор №{gathering_id} удалён."
    )


# ============================================================
# АВТОМАТИЧЕСКОЕ УДАЛЕНИЕ ПУСТОГО ВОЙСА
# ============================================================

@bot.event
async def on_voice_state_update(

    member: discord.Member,

    before: discord.VoiceState,

    after: discord.VoiceState
):

    # --------------------------------------------------------
    # Пользователь не выходил из войса
    # --------------------------------------------------------

    if before.channel is None:

        return

    channel = before.channel

    # --------------------------------------------------------
    # В канале ещё кто-то есть
    # --------------------------------------------------------

    if len(channel.members) > 0:

        return

    # ========================================================
    # ИЩЕМ СБОР
    # ========================================================

    for gathering_id, gathering in list(
        gatherings.items()
    ):

        if gathering.get(
            "voice_id"
        ) != channel.id:

            continue

        # ====================================================
        # УДАЛЯЕМ ВОЙС
        # ====================================================

        try:

            await channel.delete(

                reason=(
                    "Голосовой канал "
                    "сбора стал пустым"
                )
            )

            print(

                f"🗑️ Голосовой канал "
                f"'{channel.name}' "
                f"автоматически удалён."
            )

        except discord.NotFound:

            pass

        except discord.Forbidden:

            print(

                f"❌ Не могу удалить "
                f"'{channel.name}'. "
                f"Проверь право "
                f"Manage Channels."
            )

        except discord.HTTPException as error:

            print(

                f"❌ Ошибка удаления "
                f"канала: {error}"
            )

        # ====================================================
        # УДАЛЯЕМ СБОР ИЗ ПАМЯТИ
        # ====================================================

        gatherings.pop(

            gathering_id,

            None
        )

        break



# ============================================================
# 5X5
# ============================================================

import random
import asyncio
from datetime import datetime, timedelta


# ------------------------------------------------------------
# ХРАНИЛИЩЕ СБОРОВ 5X5
# ------------------------------------------------------------

gatherings_5x5 = {}

next_gathering_5x5_id = 1


# ------------------------------------------------------------
# EMBED 5X5
# ------------------------------------------------------------

def build_5x5_embed(gathering, guild):

    participants = gathering["participants"]

    if participants:

        lines = []

        for i, user_id in enumerate(
            participants,
            start=1
        ):

            member = guild.get_member(user_id)

            if member:
                lines.append(
                    f"`{i}.` {member.mention}"
                )
            else:
                lines.append(
                    f"`{i}.` <@{user_id}>"
                )

        players_text = "\n".join(lines)

    else:

        players_text = "Пока никто не записался."

    if len(participants) >= 10:

        status = (
            "🟢 **Все 10 игроков набраны!**\n"
            "Создатель может начать матч."
        )

    else:

        status = (
            f"🟡 **Нужно ещё "
            f"{10 - len(participants)} игроков.**"
        )

    embed = discord.Embed(

        title=f"⚔️ 5X5 — {gathering['name']}",

        description=(
            f"📅 **Дата:** {gathering['date']}\n"
            f"⏰ **Время:** {gathering['time']}\n\n"
            f"{status}"
        ),

        color=discord.Color.blurple()
    )

    embed.add_field(

        name="👥 Игроки",

        value=f"**{len(participants)} / 10**",

        inline=True
    )

    embed.add_field(

        name="👤 Создатель",

        value=f"<@{gathering['creator_id']}>",

        inline=True
    )

    embed.add_field(

        name="📋 Участники",

        value=players_text,

        inline=False
    )

    embed.set_footer(

        text=f"5X5 сбор №{gathering['id']}"
    )

    return embed


# ------------------------------------------------------------
# ОБНОВЛЕНИЕ СООБЩЕНИЯ 5X5
# ------------------------------------------------------------

async def update_5x5_message(gathering_id):

    gathering = gatherings_5x5.get(gathering_id)

    if not gathering:
        return

    guild = bot.get_guild(
        gathering["guild_id"]
    )

    if not guild:
        return

    channel = guild.get_channel(
        gathering["channel_id"]
    )

    if not channel:
        return

    try:

        message = await channel.fetch_message(
            gathering["message_id"]
        )

    except (
        discord.NotFound,
        discord.Forbidden
    ):

        return

    embed = build_5x5_embed(
        gathering,
        guild
    )

    view = Gathering5x5View(
        gathering_id
    )

    try:

        await message.edit(

            embed=embed,

            view=view
        )

    except discord.HTTPException:

        pass


# ------------------------------------------------------------
# АВТОУДАЛЕНИЕ СБОРА
# ------------------------------------------------------------

async def auto_delete_5x5(gathering_id):

    await asyncio.sleep(
        GATHERING5X5_TIMEOUT_HOURS * 60 * 60
    )

    gathering = gatherings_5x5.get(
        gathering_id
    )

    if not gathering:
        return

    # Если сбор уже завершён —
    # он уже должен быть удалён.
    if gathering.get("finished"):

        return

    guild = bot.get_guild(
        gathering["guild_id"]
    )

    if guild:

        channel = guild.get_channel(
            gathering["channel_id"]
        )

        if channel:

            try:

                message = await channel.fetch_message(
                    gathering["message_id"]
                )

                await message.delete()

            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):

                pass

        # Удаляем созданные командные войсы
        for voice_id in gathering.get(
            "team_voice_ids",
            []
        ):

            voice = guild.get_channel(
                voice_id
            )

            if voice:

                try:

                    await voice.delete(
                        reason="Автоматическое удаление 5X5"
                    )

                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    pass

    gatherings_5x5.pop(
        gathering_id,
        None
    )

    print(
        f"🗑️ Сбор 5X5 №{gathering_id} "
        f"автоматически удалён."
    )


# ============================================================
# MODAL СОЗДАНИЯ 5X5
# ============================================================

class Gathering5x5Modal(
    discord.ui.Modal
):

    def __init__(self):

        super().__init__(
            title="⚔️ Создание сбора 5X5"
        )

        self.event_name = discord.ui.TextInput(

            label="Название сбора",

            placeholder="Например: CS2 5X5",

            required=True,

            max_length=100
        )

        self.event_date = discord.ui.TextInput(

            label="Дата",

            placeholder="Например: 10.09.2026",

            required=True,

            max_length=20
        )

        self.event_time = discord.ui.TextInput(

            label="Время",

            placeholder="Например: 20:00",

            required=True,

            max_length=20
        )

        self.add_item(
            self.event_name
        )

        self.add_item(
            self.event_date
        )

        self.add_item(
            self.event_time
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        global next_gathering_5x5_id

        gathering_id = (
            next_gathering_5x5_id
        )

        next_gathering_5x5_id += 1

        gathering = {

            "id": gathering_id,

            "guild_id": interaction.guild.id,

            "channel_id": interaction.channel.id,

            "message_id": 0,

            "name": self.event_name.value,

            "date": self.event_date.value,

            "time": self.event_time.value,

            "participants": [],

            "creator_id": interaction.user.id,

            "started": False,

            "finished": False,

            "team_voice_ids": [],

            "team1": [],

            "team2": []
        }

        gatherings_5x5[
            gathering_id
        ] = gathering

        embed = build_5x5_embed(

            gathering,

            interaction.guild
        )

        view = Gathering5x5View(

            gathering_id
        )

        await interaction.response.send_message(

            embed=embed,

            view=view
        )

        message = await interaction.original_response()

        gathering["message_id"] = message.id

        # Запускаем таймер автоматического удаления
        asyncio.create_task(
            auto_delete_5x5(
                gathering_id
            )
        )


# ============================================================
# VIEW СОЗДАНИЯ 5X5
# ============================================================

class CreateGathering5x5View(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    @discord.ui.button(

        label="Создать сбор 5X5",

        emoji="⚔️",

        style=discord.ButtonStyle.primary
    )

    async def create_5x5(

        self,

        interaction: discord.Interaction,

        button: discord.ui.Button
    ):

        await interaction.response.send_modal(

            Gathering5x5Modal()
        )


# ============================================================
# VIEW СБОРА 5X5
# ============================================================

class Gathering5x5View(
    discord.ui.View
):

    def __init__(
        self,
        gathering_id
    ):

        super().__init__(
            timeout=None
        )

        self.gathering_id = gathering_id

        gathering = gatherings_5x5.get(
            gathering_id
        )

        if not gathering:
            return

        # ----------------------------------------------------
        # УЧАСТВОВАТЬ
        # ----------------------------------------------------

        join_button = discord.ui.Button(

            label="Участвовать",

            emoji="✅",

            style=discord.ButtonStyle.success,

            custom_id=(
                f"5x5_join_{gathering_id}"
            )
        )

        join_button.callback = (
            self.join_callback
        )

        self.add_item(
            join_button
        )

        # ----------------------------------------------------
        # ВЫЙТИ
        # ----------------------------------------------------

        leave_button = discord.ui.Button(

            label="Выйти",

            emoji="🚪",

            style=discord.ButtonStyle.secondary,

            custom_id=(
                f"5x5_leave_{gathering_id}"
            )
        )

        leave_button.callback = (
            self.leave_callback
        )

        self.add_item(
            leave_button
        )

        # ----------------------------------------------------
        # НАЧАТЬ
        # ----------------------------------------------------

        start_button = discord.ui.Button(

            label="Начать 5X5",

            emoji="🚀",

            style=discord.ButtonStyle.primary,

            disabled=(
                len(gathering["participants"]) < 10
                or gathering["started"]
            ),

            custom_id=(
                f"5x5_start_{gathering_id}"
            )
        )

        start_button.callback = (
            self.start_callback
        )

        self.add_item(
            start_button
        )

        # ----------------------------------------------------
        # КОНЕЦ
        # ----------------------------------------------------

        end_button = discord.ui.Button(

            label="Конец матча",

            emoji="🏁",

            style=discord.ButtonStyle.danger,

            disabled=(
                not gathering["started"]
            ),

            custom_id=(
                f"5x5_end_{gathering_id}"
            )
        )

        end_button.callback = (
            self.end_callback
        )

        self.add_item(
            end_button
        )

    # ========================================================
    # УЧАСТВОВАТЬ
    # ========================================================

    async def join_callback(
        self,
        interaction: discord.Interaction
    ):

        gathering = gatherings_5x5.get(
            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Этот сбор уже удалён.",

                ephemeral=True
            )

            return

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Сбор уже начался.",

                ephemeral=True
            )

            return

        user_id = interaction.user.id

        # ====================================================
        # ПРОВЕРКА ПОВТОРНОЙ РЕГИСТРАЦИИ
        # ====================================================

        if user_id in gathering["participants"]:

            await interaction.response.send_message(

                "⚠️ Ты уже зарегистрирован "
                "в этом сборе 5X5!",

                ephemeral=True
            )

            return

        # ====================================================
        # ПРОВЕРКА 10 ИГРОКОВ
        # ====================================================

        if len(gathering["participants"]) >= 10:

            await interaction.response.send_message(

                "❌ В сборе уже 10 игроков.",

                ephemeral=True
            )

            return

        # ====================================================
        # ДОБАВЛЯЕМ ИГРОКА
        # ====================================================

        gathering["participants"].append(
            user_id
        )

        await interaction.response.send_message(

            "✅ Ты зарегистрирован "
            "в сборе 5X5!",

            ephemeral=True
        )

        await update_5x5_message(
            self.gathering_id
        )

        # ====================================================
        # ВСЕ 10 ИГРОКОВ
        # ====================================================

        if len(
            gathering["participants"]
        ) == 10:

            mentions = " ".join(

                f"<@{uid}>"

                for uid in gathering["participants"]
            )

            await interaction.channel.send(

                f"🔥 **СБОР 5X5 НАБРАН!**\n\n"
                f"{mentions}\n\n"
                f"👥 **10 / 10 игроков**\n"
                f"🚀 Создатель может нажать "
                f"**«Начать 5X5»**."
            )

            await update_5x5_message(
                self.gathering_id
            )

    # ========================================================
    # ВЫЙТИ
    # ========================================================

    async def leave_callback(
        self,
        interaction: discord.Interaction
    ):

        gathering = gatherings_5x5.get(
            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Этот сбор уже удалён.",

                ephemeral=True
            )

            return

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Матч уже начался.",

                ephemeral=True
            )

            return

        user_id = interaction.user.id

        if user_id not in gathering["participants"]:

            await interaction.response.send_message(

                "⚠️ Ты не зарегистрирован "
                "в этом сборе.",

                ephemeral=True
            )

            return

        gathering["participants"].remove(
            user_id
        )

        await interaction.response.send_message(

            "🚪 Ты вышел из сбора 5X5.",

            ephemeral=True
        )

        await update_5x5_message(
            self.gathering_id
        )

    # ========================================================
    # НАЧАТЬ МАТЧ
    # ========================================================

    async def start_callback(
        self,
        interaction: discord.Interaction
    ):

        gathering = gatherings_5x5.get(
            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Сбор не найден.",

                ephemeral=True
            )

            return

        # Только создатель
        if interaction.user.id != gathering["creator_id"]:

            await interaction.response.send_message(

                "❌ Только создатель сбора "
                "может начать матч.",

                ephemeral=True
            )

            return

        if gathering["started"]:

            await interaction.response.send_message(

                "❌ Матч уже начался.",

                ephemeral=True
            )

            return

        if len(
            gathering["participants"]
        ) != 10:

            await interaction.response.send_message(

                "❌ Нужно ровно 10 игроков.",

                ephemeral=True
            )

            return

        # ====================================================
        # ПЕРЕМЕШИВАЕМ
        # ====================================================

        players = gathering[
            "participants"
        ].copy()

        random.shuffle(
            players
        )

        team1 = players[:5]

        team2 = players[5:]

        gathering["team1"] = team1

        gathering["team2"] = team2

        # ====================================================
        # КАТЕГОРИЯ
        # ====================================================

        category = await get_voice_category(

            interaction.guild
        )

        if not category:

            await interaction.response.send_message(

                "❌ Не удалось найти/создать "
                "категорию для голосовых каналов.",

                ephemeral=True
            )

            return

        # ====================================================
        # СОЗДАЁМ 2 ВОЙСА
        # ====================================================

        try:

            voice1 = await interaction.guild.create_voice_channel(

                name=f"🔵 5X5 — Команда 1",

                category=category,

                reason="Создание командного войса 5X5"
            )

            voice2 = await interaction.guild.create_voice_channel(

                name=f"🔴 5X5 — Команда 2",

                category=category,

                reason="Создание командного войса 5X5"
            )

        except discord.Forbidden:

            await interaction.response.send_message(

                "❌ У бота нет права "
                "**Manage Channels**.",

                ephemeral=True
            )

            return

        gathering["team_voice_ids"] = [
            voice1.id,
            voice2.id
        ]

        gathering["started"] = True

        # ====================================================
        # ПЕРВЫЙ ОТВЕТ
        # ====================================================

        await interaction.response.send_message(

            "🚀 **Матч 5X5 начался!**",

            ephemeral=True
        )

        # ====================================================
        # ПЕРЕМЕЩАЕМ КОМАНДУ 1
        # ====================================================

        moved1 = 0

        for user_id in team1:

            member = interaction.guild.get_member(
                user_id
            )

            if not member:
                continue

            if member.voice:

                try:

                    await member.move_to(
                        voice1,
                        reason="Перемещение в команду 1"
                    )

                    moved1 += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    pass

        # ====================================================
        # ПЕРЕМЕЩАЕМ КОМАНДУ 2
        # ====================================================

        moved2 = 0

        for user_id in team2:

            member = interaction.guild.get_member(
                user_id
            )

            if not member:
                continue

            if member.voice:

                try:

                    await member.move_to(
                        voice2,
                        reason="Перемещение в команду 2"
                    )

                    moved2 += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    pass

        # ====================================================
        # СООБЩЕНИЕ С КОМАНДАМИ
        # ====================================================

        team1_mentions = " ".join(

            f"<@{uid}>"

            for uid in team1
        )

        team2_mentions = " ".join(

            f"<@{uid}>"

            for uid in team2
        )

        await interaction.channel.send(

            f"⚔️ **5X5 НАЧАЛСЯ!**\n\n"

            f"🔵 **КОМАНДА 1**\n"
            f"{team1_mentions}\n"
            f"🔊 {voice1.mention}\n\n"

            f"🔴 **КОМАНДА 2**\n"
            f"{team2_mentions}\n"
            f"🔊 {voice2.mention}\n\n"

            f"🏁 Когда матч закончится, "
            f"создатель сбора нажимает "
            f"**«Конец матча»**."
        )

        await update_5x5_message(
            self.gathering_id
        )

    # ========================================================
    # КОНЕЦ МАТЧА
    # ========================================================

    async def end_callback(
        self,
        interaction: discord.Interaction
    ):

        gathering = gatherings_5x5.get(
            self.gathering_id
        )

        if not gathering:

            await interaction.response.send_message(

                "❌ Сбор не найден.",

                ephemeral=True
            )

            return

        # Только создатель
        if interaction.user.id != gathering["creator_id"]:

            await interaction.response.send_message(

                "❌ Только создатель сбора "
                "может завершить матч.",

                ephemeral=True
            )

            return

        if not gathering["started"]:

            await interaction.response.send_message(

                "❌ Матч ещё не начался.",

                ephemeral=True
            )

            return

        await interaction.response.send_message(

            "🏁 Завершаю матч и возвращаю игроков...",

            ephemeral=True
        )

        # ====================================================
        # ОБЩИЙ ВОЙС
        # ====================================================

        general_voice = interaction.guild.get_channel(

            GENERAL_VOICE_ID
        )

        moved = 0

        if isinstance(
            general_voice,
            discord.VoiceChannel
        ):

            for user_id in gathering["participants"]:

                member = interaction.guild.get_member(
                    user_id
                )

                if not member:
                    continue

                try:

                    await member.move_to(

                        general_voice,

                        reason="Окончание матча 5X5"
                    )

                    moved += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    pass

        else:

            await interaction.channel.send(

                "⚠️ **Общий голосовой канал "
                "не настроен.**\n\n"
                "Укажи правильный "
                "`GENERAL_VOICE_ID` в коде."
            )

        # ====================================================
        # УДАЛЯЕМ КОМАНДНЫЕ ВОЙСЫ
        # ====================================================

        deleted = 0

        for voice_id in gathering.get(
            "team_voice_ids",
            []
        ):

            voice = interaction.guild.get_channel(
                voice_id
            )

            if voice:

                try:

                    await voice.delete(

                        reason="Окончание матча 5X5"
                    )

                    deleted += 1

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):

                    pass

        # ====================================================
        # ЗАВЕРШАЕМ СБОР
        # ====================================================

        gathering["finished"] = True

        await interaction.channel.send(

            f"🏁 **МАТЧ 5X5 ЗАВЕРШЁН!**\n\n"
            f"👥 Игроков: "
            f"{len(gathering['participants'])}\n"
            f"🔊 Возвращено в общий войс: "
            f"{moved}\n"
            f"🗑️ Удалено командных войсов: "
            f"{deleted}"
        )

        # Удаляем сбор из памяти
        gatherings_5x5.pop(
            self.gathering_id,
            None
        )


# ============================================================
# /СБОР5X5
# ============================================================

@bot.tree.command(

    name="сбор5x5",

    description="Создать сбор игроков 5X5"
)

@app_commands.guild_only()

async def gathering_5x5_command(

    interaction: discord.Interaction
):

    embed = discord.Embed(

        title="⚔️ Сбор 5X5",

        description=(

            "Создай матч **5 на 5**.\n\n"

            "После создания сбора нужно "
            "набрать **10 игроков**.\n\n"

            "После набора:\n"
            "• игроков будет случайно разделено "
            "на 2 команды по 5;\n"
            "• создадутся два голосовых канала;\n"
            "• игроки будут перемещены в свои команды;\n"
            "• закончить матч сможет только "
            "создатель сбора."
        ),

        color=discord.Color.blurple()
    )

    view = CreateGathering5x5View()

    await interaction.response.send_message(

        embed=embed,

        view=view,

        ephemeral=True
    )

# ------------------------------------------------------------
# /serverinfo
# ------------------------------------------------------------

@bot.tree.command(
    name="serverinfo",
    description="Показать информацию о сервере"
)
@app_commands.guild_only()
async def serverinfo_command(interaction: discord.Interaction):
    guild = interaction.guild

    embed = discord.Embed(
        title=f"📊 Информация о сервере — {guild.name}",
        color=discord.Color.blurple()
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="🆔 ID",
        value=str(guild.id),
        inline=True
    )

    embed.add_field(
        name="👥 Участники",
        value=str(guild.member_count),
        inline=True
    )

    embed.add_field(
        name="💬 Каналы",
        value=str(len(guild.channels)),
        inline=True
    )

    embed.add_field(
        name="🏷 Роли",
        value=str(len(guild.roles)),
        inline=True
    )

    embed.add_field(
        name="👑 Владелец",
        value=f"<@{guild.owner_id}>",
        inline=True
    )

    embed.add_field(
        name="📅 Создан",
        value=f"<t:{int(guild.created_at.timestamp())}:F>",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# ============================================================
# СИНХРОНИЗАЦИЯ SLASH-КОМАНД
# ============================================================

async def sync_commands():

    print("========================================")
    print("🔄 Начинаю синхронизацию команд...")
    print("========================================")

    for guild in bot.guilds:

        try:
            synced = await bot.tree.sync(guild=guild)

            print(
                f"✅ {guild.name}: "
                f"{len(synced)} команд"
            )

            for command in synced:
                print(f"   /{command.name}")

        except Exception as error:

            print(
                f"❌ Ошибка синхронизации "
                f"{guild.name}: {error}"
            )

    print("========================================")


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print("========================================")
    print(f"🤖 Бот запущен: {bot.user}")
    print(f"🆔 ID бота: {bot.user.id}")
    print(f"🌐 Серверов: {len(bot.guilds)}")
    print("========================================")

    # Не синхронизируем повторно при реконнекте
    if not hasattr(bot, "_commands_synced"):

        bot._commands_synced = True

        await sync_commands()

    print("========================================")

# ============================================================
# ЗАПУСК БОТА
# ============================================================

if not TOKEN:

    print(
        "❌ ОШИБКА: переменная "
        "DISCORD_TOKEN не установлена!"
    )

else:

    bot.run(TOKEN)
