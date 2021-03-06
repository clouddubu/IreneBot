import discord
import datetime
import pytz
from discord.ext import commands
from Utility import resources as ex
from module import logger as log


# noinspection PyBroadException,PyPep8
class Profile(commands.Cog):
    def __init__(self):
        ex.client.add_listener(self.profile_level, 'on_message')

    @commands.command()
    async def avatar(self, ctx, user: discord.Member = None):
        try:
            if not user:
                user_id = ctx.author.id
                user = ctx.author
            else:
                user_id = user.id
            embed = await ex.create_embed(title=f"{user.display_name}'s Avatar   ({user_id})")
            embed.set_image(url=user.avatar_url)
            await ctx.send(embed=embed)
        except Exception as e:
            log.console(e)

    @commands.command()
    async def profile(self, ctx, user: discord.Member = None):
        try:
            if not user:
                user_id = ctx.author.id
                user = ctx.author
                roles_list = []
            else:
                user_id = user.id
                roles_list = user.roles
            if user.bot:
                user_bot = "Yes"
            else:
                user_bot = "No"

            count = 0
            roles = ""
            for role in roles_list:
                if count and count != (len(roles_list) - 1):
                    roles += f"{role.name}, "
                if count == (len(roles_list)-1):
                    roles += role.name
                count += 1
            if len(roles) > 500:
                roles = f"{roles[0:498]}...."
            user_level = await ex.u_levels.get_level(user_id, "profile")
            shortened_money = await ex.u_currency.shorten_balance(str(await ex.u_currency.get_balance(user_id)))
            rob_beg_daily_level = f"{await ex.u_levels.get_level(user_id, 'rob')}/{await ex.u_levels.get_level(user_id, 'beg')}/{await ex.u_levels.get_level(user_id, 'daily')}"
            user_scores = f"{await ex.u_guessinggame.get_user_score('easy', user_id)}/" \
                f"{await ex.u_guessinggame.get_user_score('medium', user_id)}/" \
                f"{await ex.u_guessinggame.get_user_score('hard', user_id)}"
            user_timezone = await ex.u_reminder.get_user_timezone(user_id)
            try:
                timezone_utc = datetime.datetime.now(pytz.timezone(user_timezone)).strftime('%Z, UTC%z')
            except:
                timezone_utc = None

            if await ex.u_patreon.check_if_patreon(user_id):
                embed = discord.Embed(title=f"{user.name} ({user_id})", color=0x90ee90, url=f"{user.avatar_url}", description=f"**{user.name} is supporting Irene on Patreon!**")
            else:
                embed = discord.Embed(title=f"{user.name} ({user_id})", color=0x90ee90, url=f"{user.avatar_url}")
            embed = await ex.set_embed_author_and_footer(embed, "Thanks for using Irene!")
            try:
                user_activity = user.activity.name
            except:
                user_activity = None
            embed.set_thumbnail(url=user.avatar_url)
            embed.add_field(name="Profile Level", value=user_level, inline=True)
            embed.add_field(name="Money", value=f"${shortened_money}", inline=True)
            if type(user) == discord.Member:
                embed.add_field(name="Status", value=f"{user.status}", inline=True)
                embed.add_field(name="Server Nickname", value=user.nick, inline=True)
                embed.add_field(name="Server Join Date", value=user.joined_at, inline=True)
                if roles:
                    embed.add_field(name="Roles", value=roles, inline=False)
            embed.add_field(name="Rob/Beg/Daily Level", value=rob_beg_daily_level, inline=True)
            embed.add_field(name="Account Join Date", value=user.created_at, inline=True)
            embed.add_field(name="Bot", value=user_bot, inline=True)
            if user_activity:
                embed.add_field(name="Activity", value=user_activity, inline=True)
            if user_timezone:
                embed.add_field(name="Timezone", value=f"{user_timezone} ({timezone_utc})", inline=True)
            embed.add_field(name="GuessingGame [Easy/Medium/Hard]", value=user_scores, inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            server_prefix = await ex.get_server_prefix_by_context(ctx)
            await ctx.send(f"> **There was an error. Please {server_prefix}report it**")
            log.console(e)

    @staticmethod
    async def profile_level(msg):
        try:
            xp_per_message = 10
            user_id = msg.author.id
            current_level = await ex.u_levels.get_level(user_id, "profile")
            current_xp = await ex.u_levels.get_level(user_id, "profilexp")
            xp_needed_for_level = await ex.u_levels.get_xp(current_level, "profile")

            if current_xp + xp_per_message < xp_needed_for_level:
                await ex.u_levels.set_level(user_id, current_xp + xp_per_message, "profilexp")
            else:
                await ex.u_levels.set_level(user_id, 1, "profilexp")
                await ex.u_levels.set_level(user_id, current_level+1, "profile")
        except:
            pass
            # log.console(e)
