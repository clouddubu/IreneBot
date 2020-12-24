import discord
from discord.ext import commands
from module import logger as log, events
import random
from Utility import resources as ex
import datetime
import pytz


class Reminder(commands.Cog):

    @commands.command(aliases=["listreminders", "reminders", "reminds"])
    async def listreminds(self, ctx):
        """List out all currently set reminders"""
        remind_list = await ex.get_reminders(ctx.author.id)

        if not remind_list:
            return await ctx.send(f"> {ctx.author.display_name}, you have no reminders.")

        m_embed = await ex.create_embed(title="Reminders List")
        embed_list = []
        remind_number = 0
        for remind in remind_list:
            remind_number += 1
            m_embed.add_field(name=f"{remind[1].strftime('%m/%d/%Y, %H:%M:%S')}", value=f"to {remind[0]}", inline=False)
            if remind_number == 25:
                embed_list.append(m_embed)
                m_embed = await ex.create_embed(title="Reminders List")
                remind_number = 0
        if remind_number:
            embed_list.append(m_embed)
        msg = await ctx.send(embed=m_embed[0])
        await ex.check_left_or_right_reaction_embed(msg, embed_list)

    @commands.command(aliases=["removereminder"])
    async def removeremind(self, ctx):
        """Remove a reminder from your set reminders.
        [Format: %removeremind (remind index)]"""
        pass

    @commands.command(aliases=["remind"])
    async def remindme(self, ctx, *, user_input):
        """Create a reminder to do a task at a certain time.
        [Format: %remindme to ______ at 9PM
        or
        %remindme to ____ in 6hrs 30mins]"""
        try:
            is_relative_time, type_index = await ex.determine_time_type(user_input)
        except ex.exceptions.TooLarge:
            return await ctx.send(
                f"> {ctx.author.display_name}, the time for a reminder can not be greater than 2 years.")
        if is_relative_time is None:
            return await ctx.send(f"> {ctx.author.display_name}, please use 'in/at' to specify time.")
        remind_reason = await ex.process_remind_reason(user_input, type_index)
        remind_time = await ex.process_remind_time(user_input, type_index, is_relative_time, ctx.author.id)
        await ex.set_reminder(remind_reason, remind_time, ctx.author.id)
        return await ctx.send(
            f"> {ctx.author.display_name}, I will remind you to {remind_reason} on {remind_time.strftime('%m/%d/%Y, %H:%M:%S')}")

    @commands.command()
    async def testremind(self, ctx, *, user_input):
        """Test command that needs to be removed"""
        is_relative_time, _ = await ex.determine_time_type(user_input)
        if is_relative_time:
            return await ctx.send(f"> The time type is relative time.")
        return await ctx.send(f"> The time type is absolute time.")

    @commands.command()
    async def gettimezone(self, ctx):
        """Get your current set timezone.
        [Format: %gettimezone]"""
        user_timezone = await ex.get_user_timezone(ctx.author.id)
        if not user_timezone:
            return await ctx.send(f"> {ctx.author.display_name}, you do not have not set a timezone. Please call "
                                  f"`%settimezone (timezone abbreviation) (country code)`")

        timezone_abbrev = datetime.datetime.now(pytz.timezone(user_timezone)).strftime('%Z%z')
        return await ctx.send(
            f"> {ctx.author.display_name}, your timezone is current set to {user_timezone} {timezone_abbrev}")

    @commands.command()
    async def settimezone(self, ctx, timezone_name=None, country_code=None):
        """Set your local timezone with the timezone abbreviation and country code.
        [Format: %settimezone (timezone name) (country code)]"""
        if not timezone_name and not country_code:
            await ex.remove_user_timezone(ctx.author.id)
            return await ctx.send(f"> {ctx.author.display_name}, if your timezone was set, it has been removed from the system.")

        user_timezone = await ex.get_time_zone_name(timezone_name, country_code)
        if not user_timezone:
            return await ctx.send(f"> That is not a valid timezone.")

        timezone_utc = datetime.datetime.now(pytz.timezone(user_timezone)).strftime('%Z%z')
        native_time = datetime.datetime.now(pytz.timezone(user_timezone)).strftime('%c')
        await ex.set_user_timezone(ctx.author.id, user_timezone)
        return await ctx.send(f"> {ctx.author.display_name}, your timezone has been set to `{user_timezone} "
                              f"{timezone_utc}` where it is currently `{native_time}`")