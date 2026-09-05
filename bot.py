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
# VOICE_CATEGORY_ID = 123456789012345678
#
# Если оставить 0 — бот будет искать/создавать категорию "Сборы".

VOICE_CATEGORY_ID = 1280575533565870273

VOICE_CATEGORY_NAME = "Сборы"

# ID ОБЩЕГО ГОЛОСОВОГО КАНАЛА
# Сюда будут возвращаться игроки после окончания 5x5.
GENERAL_VOICE_ID = 0

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
# READY
# ============================================================

@bot.event
async def on_ready():

    print("========================================")
    print(f"Бот запущен: {bot.user}")
    print(f"ID бота: {bot.user.id}")
    print(f"Серверов: {len(bot.guilds)}")
    print("========================================")

    try:

        # ----------------------------------------------------
        # Удаляем старые серверные регистрации команд
        # ----------------------------------------------------

        for guild in bot.guilds:

            bot.tree.clear_commands(
                guild=guild
            )

            await bot.tree.sync(
                guild=guild
            )

            print(
                f"🧹 Старые команды сервера "
                f"'{guild.name}' очищены."
            )

        # ----------------------------------------------------
        # Регистрируем актуальные команды глобально
        # ----------------------------------------------------

        synced = await bot.tree.sync()

        print(
            f"✅ Глобально синхронизировано команд: "
            f"{len(synced)}"
        )

        print("========================================")

    except Exception as error:

        print(
            f"❌ Ошибка синхронизации команд: "
            f"{error}"
        )

# ============================================================
# СБОР 5X5
# ============================================================

gatherings_5x5 = {}

next_gathering_5x5_id = 1


# ============================================================
# НАСТРОЙКИ СБОРА 5X5
# ============================================================

TEAM_CATEGORY_NAME = "Сборы"

TEAM_1_NAME = "🔵 Команда 1"
TEAM_2_NAME = "🔴 Команда 2"

COMMON_VOICE_NAME = "Общий"


# ============================================================
# EMBED СБОРА 5X5
# ============================================================

def build_5x5_embed(
    gathering: dict,
    guild: discord.Guild
):

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

    # --------------------------------------------------------
    # Статус
    # --------------------------------------------------------

    if len(participants) >= 10:

        status = (
            "🟢 **Сбор набран! Можно начинать матч.**"
        )

    else:

        status = (
            f"🟡 **Нужно ещё "
            f"{10 - len(participants)} игроков.**"
        )

    # --------------------------------------------------------
    # Embed
    # --------------------------------------------------------

    embed = discord.Embed(

        title=(
            f"🎮 СБОР 5X5 — "
            f"{gathering['name']}"
        ),

        description=(
            "Нажмите **«Участвовать»**, "
            "чтобы попасть в сбор.\n\n"
            f"{status}"
        ),

        color=discord.Color.blurple()
    )

    embed.add_field(

        name="👥 Игроки",

        value=(
            f"**{len(participants)} / 10**"
        ),

        inline=True
    )

    embed.add_field(

        name="📅 Дата",

        value=gathering["date"],

        inline=True
    )

    embed.add_field(

        name="⏰ Время",

        value=gathering["time"],

        inline=True
    )

    embed.add_field(

        name="📋 Участники",

        value=players_text,

        inline=False
    )

    embed.set_footer(

        text=f"Сбор 5X5 №{gathering['id']}"
    )

    return embed


# ============================================================
# ОБНОВЛЕНИЕ СООБЩЕНИЯ 5X5
# ============================================================

async def update_5x5_message(
    gathering_id: int
):

    gathering = gatherings_5x5.get(
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


# ============================================================
# ПОЛУЧЕНИЕ VIEW 5X5
# ============================================================

def build_5x5_view(
    gathering_id: int
):

    return Gathering5x5View(
        gathering_id
    )


# ============================================================
# VIEW СОЗДАНИЯ СБОРА 5X5
# ============================================================

class Create5x5View(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    @discord.ui.button(

        label="Создать сбор 5x5",

        emoji="🎮",

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
# MODAL СОЗДАНИЯ СБОРА 5X5
# ============================================================

class Gathering5x5Modal(
    discord.ui.Modal
):

    def __init__(self):

        super().__init__(
            title="🎮 Создание сбора 5X5"
        )

        # ----------------------------------------------------
        # Название
        # ----------------------------------------------------

        self.event_name = discord.ui.TextInput(

            label="Название сбора",

            placeholder=(
                "Например: CS2 5X5"
            ),

            required=True,

            max_length=100
        )

        # ----------------------------------------------------
        # Дата
        # ----------------------------------------------------

        self.event_date = discord.ui.TextInput(

            label="Дата",

            placeholder=(
                "Например: 10.09.2026"
            ),

            required=True,

            max_length=30
        )

        # ----------------------------------------------------
        # Время
        # ----------------------------------------------------

        self.event_time = discord.ui.TextInput(

            label="Время",

            placeholder=(
                "Например: 21:00"
            ),

            required=True,

            max_length=30
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

    # ========================================================
    # СОЗДАНИЕ
    # ========================================================

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

            "started": False,

            "finished": False,

            "creator_id": interaction.user.id,

            "team_1_id": None,

            "team_2_id": None,

            "common_voice_id": None,

            "full_announced": False
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


# ============================================================
# VIEW СБОРА 5X5
# ============================================================

class Gathering5x5View(
    discord.ui.View
):

    def __init__(

        self,

        gathering_id: int
    ):

        super().__init__(
            timeout=None
        )

        self.gathering_id = gathering_id

        gathering = gatherings_5x5.get(
            gathering_id
        )

        started = False

        full = False

        finished = False

        if gathering:

            started = gathering["started"]

            full = (
                len(
                    gathering["participants"]
                ) >= 10
            )

            finished = gathering["finished"]

        # ====================================================
        # УЧАСТВОВАТЬ
        # ====================================================

        join_button = discord.ui.Button(

            label="Участвовать",

            emoji="✅",

            style=discord.ButtonStyle.success,

            custom_id=(
                f"5x5_join_{gathering_id}"
            ),

            disabled=(
                started
                or finished
                or full
            )
        )

        join_button.callback = (
            self.join_callback
        )

        self.add_item(
            join_button
        )

        # ====================================================
        # ВЫЙТИ
        # ====================================================

        leave_button = discord.ui.Button(

            label="Выйти",

            emoji="🚪",

            style=discord.ButtonStyle.secondary,

            custom_id=(
                f"5x5_leave_{gathering_id}"
            ),

            disabled=(
                started
                or finished
            )
        )

        leave_button.callback = (
            self.leave_callback
        )

        self.add_item(
            leave_button
        )

        # ====================================================
        # НАЧАТЬ
        # ====================================================

        start_button = discord.ui.Button(

            label="Начать матч",

            emoji="🚀",

            style=discord.ButtonStyle.primary,

            custom_id=(
                f"5x5_start_{gathering_id}"
            ),

            disabled=(
                not full
                or started
                or finished
            )
        )

        start_button.callback = (
            self.start_callback
        )

        self.add_item(
            start_button
        )

        # ====================================================
        # КОНЕЦ
        # ====================================================

        end_button = discord.ui.Button(

            label="Конец матча",

            emoji="🏁",

            style=discord.ButtonStyle.danger,

            custom_id=(
                f"5x5_end_{gathering_id}"
            ),

            disabled=(
                not started
                or finished
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

                "❌ Этот сбор больше не существует.",

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
        ) >= 10:

            await interaction.response.send_message(

                "❌ В сборе уже 10 игроков.",

                ephemeral=True
            )

            return

        if interaction.user.id in gathering[
            "participants"
        ]:

            await interaction.response.send_message(

                "⚠️ Ты уже участвуешь.",

                ephemeral=True
            )

            return

        gathering[
            "participants"
        ].append(
            interaction.user.id
        )

        # ====================================================
        # ЕСЛИ НАБРАЛИ 10
        # ====================================================

        if len(
            gathering["participants"]
        ) == 10:

            if not gathering[
                "full_announced"
            ]:

                gathering[
                    "full_announced"
                ] = True

                mentions = " ".join(

                    f"<@{user_id}>"

                    for user_id in gathering[
                        "participants"
                    ]
                )

                await interaction.response.send_message(

                    "✅ Ты записан в сбор!",

                    ephemeral=True
                )

                await interaction.channel.send(

                    f"🎉 **СБОР 5X5 НАБРАН!**\n\n"
                    f"{mentions}\n\n"
                    f"👥 **10 / 10 игроков**\n\n"
                    f"🚀 Создатель сбора может "
                    f"нажать **«Начать матч»**."
                )

            else:

                await interaction.response.send_message(

                    "✅ Ты записан в сбор!",

                    ephemeral=True
                )

        else:

            await interaction.response.send_message(

                "✅ Ты записан в сбор!",

                ephemeral=True
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

                "❌ Этот сбор больше не существует.",

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

        if user_id not in gathering[
            "participants"
        ]:

            await interaction.response.send_message(

                "⚠️ Ты не участвуешь в этом сборе.",

                ephemeral=True
            )

            return

        gathering[
            "participants"
        ].remove(user_id)

        gathering[
            "full_announced"
        ] = False

        await interaction.response.send_message(

            "🚪 Ты вышел из сбора.",

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

        # ====================================================
        # ТОЛЬКО СОЗДАТЕЛЬ
        # ====================================================

        if interaction.user.id != gathering[
            "creator_id"
        ]:

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

                "❌ Для начала нужно 10 игроков.",

                ephemeral=True
            )

            return

        # ====================================================
        # ИЩЕМ КАТЕГОРИЮ
        # ====================================================

        category = None

        for cat in interaction.guild.categories:

            if cat.name == TEAM_CATEGORY_NAME:

                category = cat

                break

        if category is None:

            try:

                category = await interaction.guild.create_category(

                    TEAM_CATEGORY_NAME,

                    reason="Создание каналов матча 5X5"
                )

            except discord.Forbidden:

                await interaction.response.send_message(

                    "❌ Бот не может создать категорию.\n"
                    "Нужно право **Manage Channels**.",

                    ephemeral=True
                )

                return

        # ====================================================
        # СОЗДАЁМ ПЕРВЫЙ ВОЙС
        # ====================================================

        try:

            team_1 = await interaction.guild.create_voice_channel(

                name=TEAM_1_NAME,

                category=category,

                reason=(
                    f"Матч 5X5 №"
                    f"{self.gathering_id}"
                )
            )

        except discord.Forbidden:

            await interaction.response.send_message(

                "❌ Бот не может создавать голосовые каналы.\n"
                "Нужно право **Manage Channels**.",

                ephemeral=True
            )

            return

        # ====================================================
        # СОЗДАЁМ ВТОРОЙ ВОЙС
        # ====================================================

        try:

            team_2 = await interaction.guild.create_voice_channel(

                name=TEAM_2_NAME,

                category=category,

                reason=(
                    f"Матч 5X5 №"
                    f"{self.gathering_id}"
                )
            )

        except discord.Forbidden:

            try:

                await team_1.delete(
                    reason="Не удалось создать второй войс"
                )

            except discord.HTTPException:

                pass

            await interaction.response.send_message(

                "❌ Бот не смог создать второй голосовой канал.",

                ephemeral=True
            )

            return

        # ====================================================
        # РАНДОМНО ДЕЛИМ 10 ИГРОКОВ
        # ====================================================

        players = list(
            gathering["participants"]
        )

        random.shuffle(players)

        team_1_players = players[:5]

        team_2_players = players[5:]

        # ====================================================
        # СОХРАНЯЕМ
        # ====================================================

        gathering[
            "started"
        ] = True

        gathering[
            "team_1_id"
        ] = team_1.id

        gathering[
            "team_2_id"
        ] = team_2.id

        # ====================================================
        # ОТВЕТ
        # ====================================================

        await interaction.response.send_message(

            "🚀 **Матч 5X5 начинается!**\n\n"
            f"🔵 {team_1.mention}\n"
            f"🔴 {team_2.mention}",

            ephemeral=True
        )

        # ====================================================
        # ПЕРЕМЕЩЕНИЕ ИГРОКОВ
        # ====================================================

        team_1_mentions = []

        team_2_mentions = []

        moved_1 = 0

        moved_2 = 0

        failed = 0

        # ----------------------------------------------------
        # КОМАНДА 1
        # ----------------------------------------------------

        for user_id in team_1_players:

            member = interaction.guild.get_member(
                user_id
            )

            if not member:

                continue

            team_1_mentions.append(
                member.mention
            )

            if member.voice is None:

                failed += 1

                continue

            try:

                await member.move_to(

                    team_1,

                    reason=(
                        f"Перемещение в "
                        f"команду 1 матча "
                        f"5X5 №"
                        f"{self.gathering_id}"
                    )
                )

                moved_1 += 1

            except (
                discord.Forbidden,
                discord.HTTPException
            ):

                failed += 1

        # ----------------------------------------------------
        # КОМАНДА 2
        # ----------------------------------------------------

        for user_id in team_2_players:

            member = interaction.guild.get_member(
                user_id
            )

            if not member:

                continue

            team_2_mentions.append(
                member.mention
            )

            if member.voice is None:

                failed += 1

                continue

            try:

                await member.move_to(

                    team_2,

                    reason=(
                        f"Перемещение в "
                        f"команду 2 матча "
                        f"5X5 №"
                        f"{self.gathering_id}"
                    )
                )

                moved_2 += 1

            except (
                discord.Forbidden,
                discord.HTTPException
            ):

                failed += 1

        # ====================================================
        # ОБНОВЛЯЕМ СООБЩЕНИЕ
        # ====================================================

        await update_5x5_message(

            self.gathering_id
        )

        # ====================================================
        # ОТПРАВЛЯЕМ КОМАНДЫ
        # ====================================================

        await interaction.channel.send(

            f"🚀 **МАТЧ НАЧАЛСЯ!**\n\n"

            f"🔵 **КОМАНДА 1**\n"
            f"{' '.join(team_1_mentions)}\n"
            f"🔊 {team_1.mention}\n\n"

            f"🔴 **КОМАНДА 2**\n"
            f"{' '.join(team_2_mentions)}\n"
            f"🔊 {team_2.mention}\n\n"

            f"📊 Перемещено:\n"
            f"🔵 Команда 1: {moved_1}/5\n"
            f"🔴 Команда 2: {moved_2}/5\n"
            f"⚠️ Не перемещено: {failed}"
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

        # ====================================================
        # ТОЛЬКО СОЗДАТЕЛЬ
        # ====================================================

        if interaction.user.id != gathering[
            "creator_id"
        ]:

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

        if gathering["finished"]:

            await interaction.response.send_message(

                "❌ Матч уже завершён.",

                ephemeral=True
            )

            return

        # ====================================================
        # ИЩЕМ ОБЩИЙ ВОЙС
        # ====================================================

        common_voice = None

        for channel in interaction.guild.voice_channels:

            if channel.name == COMMON_VOICE_NAME:

                common_voice = channel

                break

        if common_voice is None:

            await interaction.response.send_message(

                f"❌ Я не нашёл общий голосовой канал "
                f"**{COMMON_VOICE_NAME}**.\n\n"

                f"Создай его вручную и снова нажми "
                f"**«Конец матча»**.",

                ephemeral=True
            )

            return

        gathering[
            "common_voice_id"
        ] = common_voice.id

        # ====================================================
        # ПЕРЕМЕЩАЕМ ВСЕХ В ОБЩИЙ
        # ====================================================

        moved = 0

        failed = 0

        for user_id in gathering[
            "participants"
        ]:

            member = interaction.guild.get_member(

                user_id
            )

            if not member:

                continue

            if member.voice is None:

                continue

            try:

                await member.move_to(

                    common_voice,

                    reason=(
                        f"Завершение матча "
                        f"5X5 №"
                        f"{self.gathering_id}"
                    )
                )

                moved += 1

            except (
                discord.Forbidden,
                discord.HTTPException
            ):

                failed += 1

        # ====================================================
        # ПРОВЕРЯЕМ КОМАНДНЫЕ ВОЙСЫ
        # ====================================================

        team_channels = []

        if gathering["team_1_id"]:

            channel = interaction.guild.get_channel(

                gathering["team_1_id"]
            )

            if isinstance(
                channel,
                discord.VoiceChannel
            ):

                team_channels.append(channel)

        if gathering["team_2_id"]:

            channel = interaction.guild.get_channel(

                gathering["team_2_id"]
            )

            if isinstance(
                channel,
                discord.VoiceChannel
            ):

                team_channels.append(channel)

        # ====================================================
        # УДАЛЯЕМ ПУСТЫЕ КАНАЛЫ
        # ====================================================

        deleted = 0

        not_empty = 0

        for channel in team_channels:

            # ------------------------------------------------
            # Если в канале остались люди — не удаляем
            # ------------------------------------------------

            if len(channel.members) > 0:

                not_empty += 1

                continue

            try:

                await channel.delete(

                    reason=(
                        f"Завершение матча "
                        f"5X5 №"
                        f"{self.gathering_id}"
                    )
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

        gathering[
            "finished"
        ] = True

        # ====================================================
        # ОБНОВЛЯЕМ СООБЩЕНИЕ
        # ====================================================

        await update_5x5_message(

            self.gathering_id
        )

        # ====================================================
        # РЕЗУЛЬТАТ
        # ====================================================

        await interaction.response.send_message(

            f"🏁 **Матч завершён!**\n\n"

            f"🔊 Общий войс: "
            f"{common_voice.mention}\n"

            f"👥 Перемещено в общий: "
            f"**{moved}**\n"

            f"❌ Ошибок перемещения: "
            f"**{failed}**\n\n"

            f"🗑️ Удалено командных войсов: "
            f"**{deleted}**\n"

            f"⚠️ Осталось занятых войсов: "
            f"**{not_empty}**",

            ephemeral=False
        )

        # ====================================================
        # ЕСЛИ ВСЕ ВОЙСЫ УДАЛЕНЫ
        # МОЖНО УДАЛИТЬ СБОР ИЗ ПАМЯТИ
        # ====================================================

        if not_empty == 0:

            gatherings_5x5.pop(

                self.gathering_id,

                None
            )


# ============================================================
# /СБОР5X5
# ============================================================

@bot.tree.command(

    name="сбор5x5",

    description="Создать сбор 5 на 5"
)

@app_commands.guild_only()

async def gathering_5x5_command(

    interaction: discord.Interaction
):

    embed = discord.Embed(

        title="🎮 Сбор 5X5",

        description=(

            "Создай матч **5 на 5**.\n\n"

            "После создания нужно набрать "
            "**10 игроков**.\n\n"

            "Когда 10 игроков будут набраны, "
            "создатель сможет начать матч.\n\n"

            "Бот случайным образом разделит "
            "игроков на две команды по 5 человек."
        ),

        color=discord.Color.blurple()
    )

    view = Create5x5View()

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
# ЗАПУСК БОТА
# ============================================================

if not TOKEN:

    print(
        "❌ ОШИБКА: переменная "
        "DISCORD_TOKEN не установлена!"
    )

else:

    bot.run(TOKEN)
