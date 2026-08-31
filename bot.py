import discord
import os
from discord.ext import commands
from discord import app_commands
from typing import Optional

TOKEN = os.getenv("DISCORD_TOKEN")

# ============================================================
# НАСТРОЙКИ
# ============================================================

# Если хочешь, чтобы войсы создавались в определённой категории,
# укажи ID категории.
# Если оставить 0, бот сам создаст категорию "Сборы".
VOICE_CATEGORY_ID = 0

# Название категории, если VOICE_CATEGORY_ID = 0
VOICE_CATEGORY_NAME = "Сборы"

# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

# Нужно для работы с участниками и голосовыми каналами
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ============================================================
# ХРАНЕНИЕ СБОРОВ
# ============================================================

# Формат:
#
# gatherings[gathering_id] = {
#     "guild_id": ID сервера,
#     "channel_id": ID текстового канала,
#     "message_id": ID сообщения,
#     "name": "Название",
#     "max_players": 5,
#     "role_id": ID роли или None,
#     "time": "21:00",
#     "participants": [ID, ID, ID],
#     "started": False,
#     "voice_id": None
# }

gatherings = {}

next_gathering_id = 1


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_gathering(gathering_id: int):
    return gatherings.get(gathering_id)


def get_role(guild: discord.Guild, role_id: Optional[int]):
    if role_id is None:
        return None

    return guild.get_role(role_id)


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

    if role:
        role_text = role.mention
    else:
        role_text = "Не указана"

    participant_text = ""

    if participants:
        lines = []

        for i, user_id in enumerate(participants, start=1):
            member = guild.get_member(user_id)

            if member:
                lines.append(
                    f"`{i}.` {member.mention}"
                )
            else:
                lines.append(
                    f"`{i}.` <@{user_id}>"
                )

        participant_text = "\n".join(lines)
    else:
        participant_text = "Пока никто не записался."

    if len(participants) >= max_players:
        status = "🟢 **Игроки набраны! Можно начинать.**"
    else:
        status = (
            f"🟡 **Нужно ещё "
            f"{max_players - len(participants)} игрок(а/ов).**"
        )

    embed = discord.Embed(
        title=f"🎮 {gathering['name']}",
        description=(
            "Нажмите **«Участвовать»**, чтобы попасть "
            "в список игроков.\n\n"
            f"{status}"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="👥 Игроки",
        value=f"**{len(participants)} / {max_players}**",
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


def build_gathering_view(gathering_id: int):
    gathering = gatherings[gathering_id]

    view = GatheringView(
        gathering_id=gathering_id,
        started=gathering["started"],
        full=(
            len(gathering["participants"])
            >= gathering["max_players"]
        )
    )

    return view


async def update_gathering_message(
    gathering_id: int
):
    gathering = gatherings.get(gathering_id)

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


async def get_voice_category(
    guild: discord.Guild
):
    # Если указана существующая категория
    if VOICE_CATEGORY_ID != 0:
        category = guild.get_channel(
            VOICE_CATEGORY_ID
        )

        if isinstance(
            category,
            discord.CategoryChannel
        ):
            return category

    # Иначе ищем категорию "Сборы"
    for category in guild.categories:
        if category.name == VOICE_CATEGORY_NAME:
            return category

    # Если её нет — создаём
    try:
        category = await guild.create_category(
            VOICE_CATEGORY_NAME,
            reason="Создание категории для сборов"
        )

        return category

    except discord.Forbidden:
        return None


# ============================================================
# MODAL — СОЗДАНИЕ СБОРА
# ============================================================

class GatheringModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(
            title="🎮 Создание сбора"
        )

        self.event_name = discord.ui.TextInput(
            label="Название события",
            placeholder="Например: Игра в CS2",
            required=True,
            max_length=100
        )

        self.players_count = discord.ui.TextInput(
            label="Количество игроков",
            placeholder="Например: 5",
            required=True,
            max_length=3
        )

        self.role = discord.ui.TextInput(
            label="Тег участников",
            placeholder="ID роли или @роль",
            required=False,
            max_length=100
        )

        self.event_time = discord.ui.TextInput(
            label="Время",
            placeholder="Например: 21:00",
            required=True,
            max_length=30
        )

        self.add_item(self.event_name)
        self.add_item(self.players_count)
        self.add_item(self.role)
        self.add_item(self.event_time)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        global next_gathering_id

        # ----------------------------------------------------
        # Проверяем количество игроков
        # ----------------------------------------------------

        try:
            players_count = int(
                self.players_count.value
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Количество игроков должно быть числом.",
                ephemeral=True
            )
            return

        if players_count < 1:
            await interaction.response.send_message(
                "❌ Количество игроков должно быть больше 0.",
                ephemeral=True
            )
            return

        if players_count > 99:
            await interaction.response.send_message(
                "❌ Максимальное количество игроков — 99.",
                ephemeral=True
            )
            return

        # ----------------------------------------------------
        # Получаем роль
        # ----------------------------------------------------

        role_id = None
        role_text = self.role.value.strip()

        if role_text:
            # Если пользователь написал <@&123>
            cleaned = (
                role_text
                .replace("<@&", "")
                .replace(">", "")
                .strip()
            )

            try:
                possible_role_id = int(cleaned)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Тег роли указан неправильно.\n\n"
                    "Укажи **ID роли** или вставь упоминание роли.",
                    ephemeral=True
                )
                return

            role = interaction.guild.get_role(
                possible_role_id
            )

            if not role:
                await interaction.response.send_message(
                    "❌ Я не нашёл такую роль на сервере.",
                    ephemeral=True
                )
                return

            role_id = role.id

        # ----------------------------------------------------
        # Создаём сбор
        # ----------------------------------------------------

        gathering_id = next_gathering_id
        next_gathering_id += 1

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
            "creator_id": interaction.user.id
        }

        gatherings[gathering_id] = gathering

        # ----------------------------------------------------
        # Создаём сообщение
        # ----------------------------------------------------

        embed = build_gathering_embed(
            gathering,
            interaction.guild
        )

        view = build_gathering_view(
            gathering_id
        )

        await interaction.response.send_message(
            embed=embed,
            view=view
        )

        message = await interaction.original_response()

        gathering["message_id"] = message.id

        # ----------------------------------------------------
        # Если указана роль — упоминаем её
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
# КНОПКА СОЗДАНИЯ СБОРА
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
# КНОПКИ САМОГО СБОРА
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

        # ----------------------------------------------------
        # Кнопка участвовать
        # ----------------------------------------------------

        participate_button = discord.ui.Button(
            label="Участвовать",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"gathering_join_{gathering_id}"
        )

        participate_button.callback = (
            self.join_callback
        )

        self.add_item(
            participate_button
        )

        # ----------------------------------------------------
        # Кнопка выйти
        # ----------------------------------------------------

        leave_button = discord.ui.Button(
            label="Выйти",
            emoji="🚪",
            style=discord.ButtonStyle.secondary,
            custom_id=f"gathering_leave_{gathering_id}"
        )

        leave_button.callback = (
            self.leave_callback
        )

        self.add_item(
            leave_button
        )

        # ----------------------------------------------------
        # Кнопка начать
        # ----------------------------------------------------

        start_button = discord.ui.Button(
            label="Начать",
            emoji="🚀",
            style=discord.ButtonStyle.primary,
            custom_id=f"gathering_start_{gathering_id}",
            disabled=(
                started or not full
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
                "❌ Этот сбор больше не существует.",
                ephemeral=True
            )
            return

        if gathering["started"]:
            await interaction.response.send_message(
                "❌ Сбор уже начался.",
                ephemeral=True
            )
            return

        participants = gathering["participants"]

        # Уже записан
        if interaction.user.id in participants:
            await interaction.response.send_message(
                "⚠️ Ты уже участвуешь в этом сборе.",
                ephemeral=True
            )
            return

        # Уже заполнено
        if len(participants) >= gathering["max_players"]:
            await interaction.response.send_message(
                "❌ В этом сборе уже набрано нужное "
                "количество игроков.",
                ephemeral=True
            )
            return

      
        # ----------------------------------------------------
        # Добавляем ID
        # ----------------------------------------------------

        participants.append(
            interaction.user.id
        )

        await interaction.response.send_message(
            "✅ Ты успешно записался в сбор!",
            ephemeral=True
        )

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
                "❌ Этот сбор больше не существует.",
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

        if user_id not in gathering["participants"]:
            await interaction.response.send_message(
                "⚠️ Ты не участвуешь в этом сборе.",
                ephemeral=True
            )
            return

        gathering["participants"].remove(
            user_id
        )

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
                "❌ Этот сбор больше не существует.",
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
        # Проверяем количество
        # ----------------------------------------------------

        if len(gathering["participants"]) < gathering[
            "max_players"
        ]:
            await interaction.response.send_message(
                "❌ Пока недостаточно игроков.",
                ephemeral=True
            )
            return

        # ----------------------------------------------------
        # Можно ли начинать?
        # ----------------------------------------------------

        # Начать может:
        # 1. создатель
        # 2. администратор
        # 3. участник сбора

        is_creator = (
            interaction.user.id
            == gathering["creator_id"]
        )

        is_admin = (
            interaction.user.guild_permissions.administrator
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
                "создатель, администратор или "
                "участник сбора.",
                ephemeral=True
            )
            return

        # ----------------------------------------------------
        # Получаем категорию
        # ----------------------------------------------------

        category = await get_voice_category(
            interaction.guild
        )

        if not category:
            await interaction.response.send_message(
                "❌ Я не могу создать голосовой канал.\n"
                "Проверь право **Manage Channels**.",
                ephemeral=True
            )
            return

        # ----------------------------------------------------
        # Создаём войс
        # ----------------------------------------------------

        voice_name = (
            f"🎮 {gathering['name']}"
        )

        try:
            voice_channel = await interaction.guild.create_voice_channel(
                name=voice_name[:100],
                category=category,
                reason=f"Запуск сбора №{self.gathering_id}"
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

        # ----------------------------------------------------
        # Отмечаем сбор начатым
        # ----------------------------------------------------

        gathering["started"] = True
        gathering["voice_id"] = voice_channel.id

        # ----------------------------------------------------
        # Сначала отвечаем пользователю
        # ----------------------------------------------------

        await interaction.response.send_message(
            f"🚀 **Сбор начался!**\n"
            f"Голосовой канал: {voice_channel.mention}",
            ephemeral=True
        )

        # ----------------------------------------------------
        # Перемещаем участников
        # ----------------------------------------------------

        moved = 0
        not_in_voice = 0
        failed = 0

        for user_id in gathering["participants"]:
            member = interaction.guild.get_member(
                user_id
            )

            if not member:
                continue

            # Участник должен находиться в каком-либо войсе
            if not member.voice:
                not_in_voice += 1
                continue

            try:
                await member.move_to(
                    voice_channel,
                    reason=f"Перемещение в сбор №{self.gathering_id}"
                )

                moved += 1

            except discord.Forbidden:
                failed += 1

            except discord.HTTPException:
                failed += 1

        # ----------------------------------------------------
        # Обновляем сообщение сбора
        # ----------------------------------------------------

        await update_gathering_message(
            self.gathering_id
        )

        # ----------------------------------------------------
        # Отправляем информацию
        # ----------------------------------------------------

        text = (
            f"🚀 **Сбор запущен!**\n\n"
            f"🎮 **{gathering['name']}**\n"
            f"🔊 Войс: {voice_channel.mention}\n"
            f"👥 Участников: "
            f"{len(gathering['participants'])}\n\n"
            f"✅ Перемещено: {moved}\n"
            f"⚠️ Не были в войсе: {not_in_voice}\n"
            f"❌ Ошибок перемещения: {failed}"
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
    # --------------------------------------------------------
    # Проверка прав
    # --------------------------------------------------------


    embed = discord.Embed(
        title="🎮 Создание сбора",
        description=(
            "Нажми кнопку ниже, чтобы создать новый сбор.\n\n"
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
# КОМАНДА ДЛЯ УДАЛЕНИЯ СБОРА
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
    if not (
        interaction.user.guild_permissions.manage_guild
        or interaction.user.guild_permissions.administrator
    ):
        await interaction.response.send_message(
            "❌ У тебя нет прав.",
            ephemeral=True
        )
        return

    gathering = gatherings.get(
        gathering_id
    )

    if not gathering:
        await interaction.response.send_message(
            "❌ Сбор с таким ID не найден.",
            ephemeral=True
        )
        return

    # Удаляем голосовой канал, если он есть
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

    del gatherings[gathering_id]

    await interaction.response.send_message(
        f"✅ Сбор №{gathering_id} удалён."
    )


# ============================================================
# СОБЫТИЕ READY
# ============================================================

@bot.event
async def on_ready():
    print(
        "========================================"
    )

    print(
        f"Бот запущен: {bot.user}"
    )

    print(
        f"ID бота: {bot.user.id}"
    )

    print(
        f"Серверов: {len(bot.guilds)}"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Синхронизация slash-команд
    # --------------------------------------------------------

    try:
        synced = await bot.tree.sync()

        print(
            f"Синхронизировано команд: {len(synced)}"
        )

    except Exception as error:
        print(
            f"Ошибка синхронизации команд: {error}"
        )


# ============================================================
# ЗАПУСК
# ============================================================

if TOKEN == "ВСТАВЬ_СЮДА_ТОКЕН_БОТА":
    print(
        "❌ ОШИБКА: ты не вставил токен бота!"
    )
else:
    bot.run(TOKEN)
