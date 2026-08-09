from typing import Optional
from discord import app_commands
import discord
import src.core.configs.sBotDetails as Config
from discord.ext import commands, tasks

from src.core.database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.features.agents.controller.lily_agent_controller import LilyAgentController
from src.core.logging.lily_logging import LilyLoggingController
from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.moderation.components.sLilyModerationComponents import AppealButton
from src.core.configs.path import CONFIG_DB
from src.api.app import LilyAPI
import uvicorn
import re


class Lily(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all() 
        intents.presences = False
        intents.members = False
        intents.message_content = False

        self.lily_session = None
        self.db: Optional[BotGlobalsDatabaseAccess] = None
        self.logging_controller: Optional[LilyLoggingController] = None
        self.agent_controller: LilyAgentController = LilyAgentController()

        super().__init__(command_prefix=self.prefix,intents=intents,help_command=None, owner_ids={1488556914605428988})

    async def start_api(self):
        config = uvicorn.Config(self.api.app, host="0.0.0.0", port=8000, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()

    async def setup_hook(self):
        """ Bot Globals Database """
        self.db = await BotGlobalsDatabaseAccess.connect(str(CONFIG_DB))
        self.logging_controller = LilyLoggingController(self.db)

        self.api = LilyAPI(self.db)
        self.loop.create_task(self.start_api())

        self.add_dynamic_items(AppealButton)


        extensions = [
            "src.commands.moderation",
            "src.commands.utility",
            "src.commands.blox_fruits",
            "src.commands.management",
            "src.commands.ticket_tool",
            "src.commands.applications",
            "jishaku"
        ]

        for ext in extensions:
            try:
                if ext not in self.extensions:
                    await self.load_extension(ext)
                    print(f"Loaded {ext}")
            except Exception as e:
                print(f"Load failed {ext}: {e}")

        self.tree.on_error = self.on_app_command_error
            
    def prefix(self, bot: commands.Bot, message: discord.Message):
        if bot.user is None:
            return []

        mention = re.escape(bot.user.mention)

        match = re.match(
            rf"^{mention}\s*",
            message.content
        )

        if match:
            return match.group(0)

        prefixes = commands.when_mentioned(bot, message)

        if (
            message.reference
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author.id == bot.user.id
        ):
            prefixes.append("")

        return prefixes

    async def on_ready(self):
        print('Logged on as', self.user)
        
        await self.modify_status.start()

    async def on_guild_join(self, guild: discord.Guild):
        if self.db is not None:
            await self.db.guild_initialize(guild.id)

    @tasks.loop(minutes=60)
    async def modify_status(self):
        member_count = 0
        for guild in self.guilds:
            member_count += guild.member_count or 0
        activity = discord.Activity(type=discord.ActivityType.watching, name=f"{member_count:,} members!")
        await self.change_presence(activity=activity)

    async def on_message(self, message:discord.Message): 
        if message.author == self.user:
              return
        #await self.agent_controller.on_message(self, message=message)
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.reply(embed=simple_embed(str(error), 'cross'))

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(embed=simple_embed(f"So fast! Try again after {error.retry_after:.1f} seconds.", 'cross'))
        else:
            pass

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.CheckFailure):
            if interaction.response.is_done():
                await interaction.followup.send(
                    embed=simple_embed(str(error), "cross"),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=simple_embed(str(error), "cross"),
                    ephemeral=True,
                )

    async def send(
        self,
        ctx: commands.Context | discord.Interaction,
        **kwargs,
    ) -> discord.Message | None:
        if isinstance(ctx, commands.Context):
            return await ctx.reply(**kwargs)

        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                return await ctx.followup.send(**kwargs)
            else:
                await ctx.response.send_message(**kwargs)
                try:
                    return await ctx.original_response()
                except discord.NotFound:
                    return None

        raise TypeError(f"Unsupported context type: {type(ctx)!r}")