from module import keys, logger as log, cache, exceptions
from discord.ext import tasks
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from datadog import initialize, api
from Weverse.weverseasync import WeverseAsync
import datetime
import discord
import random
import asyncio
import os
import math
import tweepy
import json
import time
import sys
import aiofiles
import re
import pytz
import parsedatetime
import locale

"""
Utility.py
Resource Center for Irene -> Essentially serves as a client for Irene.
Any potentially useful/repeated functions will end up here
"""


class Utility:
    def __init__(self):
        self.test_bot = None  # this is changed in run.py
        self.client = keys.client
        self.session = keys.client_session
        self.conn = None  # db connection
        self.discord_cache_loaded = False
        self.cache = cache.Cache()
        self.temp_patrons_loaded = False
        self.running_loop = None  # current asyncio running loop
        self.thread_pool = None  # ThreadPoolExecutor for operations that block the event loop.
        auth = tweepy.OAuthHandler(keys.CONSUMER_KEY, keys.CONSUMER_SECRET)
        auth.set_access_token(keys.ACCESS_KEY, keys.ACCESS_SECRET)
        self.api = tweepy.API(auth)
        self.loop_count = 0
        self.recursion_limit = 10000
        self.api_issues = 0
        self.weverse_client = WeverseAsync(authorization=keys.weverse_auth_token, web_session=self.session,
                                           verbose=True, loop=asyncio.get_event_loop())
        self.exceptions = exceptions

        # SubClass Objects
        self.u_database = None
        self.u_cache = None
        self.u_currency = None
        self.u_miscellaneous = None
        self.u_blackjack = None
        self.u_levels = None
        self.u_group_members = None
        self.u_logging = None
        self.u_twitter = None
        self.u_last_fm = None
        self.u_patreon = None
        self.u_moderator = None
        self.u_custom_commands = None
        self.u_bias_game = None
        self.u_data_dog = None
        self.u_weverse = None
        self.u_self_assign_roles = None
        self.u_reminder = None




    ##################
    # ## DATABASE ## #
    ##################
    @tasks.loop(seconds=0, minutes=0, hours=0, reconnect=True)
    async def set_start_up_connection(self):
        """Looping Until A Stable Connection to DB is formed. This is to confirm Irene starts before the DB connects.
        Also creates thread pool and increases recursion limit.
        """
        if self.client.loop.is_running():
            try:
                self.conn = await self.get_db_connection()
                # Delete all active blackjack games
                await self.delete_all_games()
                self.running_loop = asyncio.get_running_loop()
                await self.create_thread_pool()
                sys.setrecursionlimit(self.recursion_limit)
            except Exception as e:
                log.console(e)
            self.set_start_up_connection.stop()

    async def create_thread_pool(self):
        self.thread_pool = ThreadPoolExecutor()

    @tasks.loop(seconds=0, minutes=1, reconnect=True)
    async def show_irene_alive(self):
        """Looped every minute to send a connection to localhost:5123 to show bot is working well."""
        source_link = "http://127.0.0.1:5123/restartBot"
        async with self.session.get(source_link) as resp:
            pass

    @staticmethod
    async def get_db_connection():
        """Retrieve Database Connection"""
        return await keys.connect_to_db()

    @staticmethod
    def first_result(record):
        """Returns the first item of a record if there is one."""
        if not record:
            return
        else:
            return record[0]

    ###############
    # ## CACHE ## #
    ###############
    async def process_cache_time(self, method, name):
        """Process the cache time."""
        past_time = time.time()
        result = await method()
        if result is None or result:  # expecting False on methods that fail to load, do not simplify None.
            log.console(f"Cache for {name} Created in {await self.get_cooldown_time(time.time() - past_time)}.")
        return result

    async def create_cache(self):
        """Create the general cache on startup"""
        past_time = time.time()
        await self.process_cache_time(self.update_idols, "Idol Photo Count")
        await self.process_cache_time(self.update_groups, "Group Photo Count")
        await self.process_cache_time(self.update_user_notifications, "User Notifications")
        # after intents was pushed in place, d.py cache loaded a lot slower and patrons are not added properly.
        # therefore it must be looped instead.
        # await self.process_cache_time(self.update_patreons, "Patrons")
        await self.process_cache_time(self.update_mod_mail, "ModMail")
        await self.process_cache_time(self.update_bot_bans, "Bot Bans")
        await self.process_cache_time(self.update_logging_channels, "Logged Channels")
        await self.process_cache_time(self.update_server_prefixes, "Server Prefixes")
        await self.process_cache_time(self.update_welcome_message_cache, "Welcome Messages")
        await self.process_cache_time(self.update_temp_channels, "Temp Channels")
        await self.process_cache_time(self.update_n_word_counter, "NWord Counter")
        await self.process_cache_time(self.update_command_counter, "Command Counter")
        await self.process_cache_time(self.create_idol_cache, "Idol Objects")
        await self.process_cache_time(self.create_group_cache, "Group Objects")
        await self.process_cache_time(self.create_restricted_channel_cache, "Restricted Idol Channels")
        await self.process_cache_time(self.create_dead_link_cache, "Dead Links")
        await self.process_cache_time(self.create_bot_status_cache, "Bot Status")
        await self.process_cache_time(self.create_bot_command_cache, "Custom Commands")
        await self.process_cache_time(self.create_weverse_channel_cache, "Weverse Text Channels")
        await self.process_cache_time(self.create_self_assignable_role_cache, "Self-Assignable Roles")
        await self.process_cache_time(self.create_reminder_cache, "Reminders")
        await self.process_cache_time(self.create_timezone_cache, "Timezones")
        if not self.test_bot and not self.weverse_client.cache_loaded:
            task = asyncio.create_task(self.process_cache_time(self.weverse_client.start, "Weverse"))
        log.console(f"Cache Completely Created in {await self.get_cooldown_time(time.time() - past_time)}.")

    async def create_timezone_cache(self):
        self.cache.timezones = {}  # reset cache
        timezones = await self.get_all_timezones_from_db()
        for user_id, timezone in timezones:
            self.cache.timezones[user_id] = timezone

    async def create_reminder_cache(self):
        """Create cache for reminders"""
        self.cache.reminders = {}  # reset cache
        all_reminders = await self.get_all_reminders_from_db()
        for reason_id, user_id, reason, time_stamp in all_reminders:
            reason_list = [reason_id, reason, time_stamp]
            user_reminder = self.cache.reminders.get(user_id)
            if user_reminder:
                user_reminder.append(reason_list)
            else:
                self.cache.reminders[user_id] = [reason_list]

    async def create_self_assignable_role_cache(self):
        """Create cache for self assignable roles"""
        all_roles = await self.conn.fetch("SELECT roleid, rolename, serverid FROM selfassignroles.roles")
        all_channels = await self.conn.fetch("SELECT channelid, serverid FROM selfassignroles.channels")
        for role_id, role_name, server_id in all_roles:
            cache_info = self.cache.assignable_roles.get(server_id)
            if not cache_info:
                self.cache.assignable_roles[server_id] = {}
                cache_info = self.cache.assignable_roles.get(server_id)
            if not cache_info.get('roles'):
                cache_info['roles'] = [[role_id, role_name]]
            else:
                cache_info['roles'].append([role_id, role_name])
        for channel_id, server_id in all_channels:
            cache_info = self.cache.assignable_roles.get(server_id)
            if cache_info:
                cache_info['channel_id'] = channel_id
            else:
                self.cache.assignable_roles[server_id] = {'channel_id': channel_id}

    async def create_weverse_channel_cache(self):
        """Create cache for channels that are following a community on weverse."""
        all_channels = await self.conn.fetch("SELECT channelid, communityname, roleid, commentsdisabled FROM weverse.channels")
        for channel_id, community_name, role_id, comments_disabled in all_channels:
            await self.add_weverse_channel_to_cache(channel_id, community_name)
            await self.add_weverse_role(channel_id, community_name, role_id)
            await self.change_weverse_comment_status(channel_id, community_name, comments_disabled)

    async def update_command_counter(self):
        """Updates Cache for command counter and sessions"""
        self.cache.command_counter = {}
        session_id = await self.get_session_id()
        all_commands = await self.conn.fetch("SELECT commandname, count FROM stats.commands WHERE sessionid = $1", session_id)
        for command_name, count in all_commands:
            self.cache.command_counter[command_name] = count
        self.cache.current_session = self.first_result(
            await self.conn.fetchrow("SELECT session FROM stats.sessions WHERE date = $1", datetime.date.today()))

    async def create_restricted_channel_cache(self):
        """Create restricted idol channel cache"""
        restricted_channels = await self.conn.fetch("SELECT channelid, serverid, sendhere FROM groupmembers.restricted")
        for channel_id, server_id, send_here in restricted_channels:
            self.cache.restricted_channels[channel_id] = [server_id, send_here]

    async def create_bot_command_cache(self):
        """Create custom command cache"""
        server_commands = await self.conn.fetch("SELECT serverid, commandname, message FROM general.customcommands")
        self.cache.custom_commands = {}
        for server_id, command_name, message in server_commands:
            cache_info = self.cache.custom_commands.get(server_id)
            if cache_info:
                cache_info[command_name] = message
            else:
                self.cache.custom_commands[server_id] = {command_name: message}

    async def create_bot_status_cache(self):
        statuses = await self.conn.fetch("SELECT status FROM general.botstatus")
        self.cache.bot_statuses = [status[0] for status in statuses] or None

    async def create_dead_link_cache(self):
        """Creates Dead Link Cache"""
        self.cache.dead_image_cache = {}
        try:
            self.cache.dead_image_channel = await self.client.fetch_channel(keys.dead_image_channel_id)
        except:
            pass
        dead_images = await self.conn.fetch("SELECT deadlink, userid, messageid, idolid, guessinggame FROM groupmembers.deadlinkfromuser")
        for dead_link, user_id, message_id, idol_id, guessing_game in dead_images:
            self.cache.dead_image_cache[message_id] = [dead_link, user_id, idol_id, guessing_game]

    async def create_idol_cache(self):
        """Create Idol Objects and store them as cache."""
        self.cache.idols = []
        for idol in await self.u_group_members.get_db_all_members():
            idol_obj = self.u_group_members.Idol(**idol)
            idol_obj.aliases, idol_obj.local_aliases = await self.u_group_members.get_db_aliases(idol_obj.id)
            # add all group ids and remove potential duplicates
            idol_obj.groups = list(dict.fromkeys(await self.u_group_members.get_db_groups_from_member(idol_obj.id)))
            idol_obj.called = await self.u_group_members.get_db_idol_called(idol_obj.id)
            idol_obj.photo_count = self.cache.idol_photos.get(idol_obj.id) or 0
            self.cache.idols.append(idol_obj)

    async def create_group_cache(self):
        """Create Group Objects and store them as cache"""
        self.cache.groups = []
        for group in await self.u_group_members.get_all_groups():
            group_obj = self.u_group_members.Group(**group)
            group_obj.aliases, group_obj.local_aliases = await self.u_group_members.get_db_aliases(group_obj.id, group=True)
            # add all idol ids and remove potential duplicates
            group_obj.members = list(dict.fromkeys(await self.u_group_members.get_db_members_in_group(group_id=group_obj.id)))
            group_obj.photo_count = self.cache.group_photos.get(group_obj.id) or 0
            self.cache.groups.append(group_obj)

    async def process_session(self):
        """Sets the new session id, total used, and time format for distinguishing days."""
        current_time_format = datetime.date.today()
        if self.cache.session_id is None:
            if self.cache.total_used is None:
                self.cache.total_used = (self.first_result(await self.conn.fetchrow("SELECT totalused FROM stats.sessions ORDER BY totalused DESC"))) or 0
            try:
                await self.conn.execute("INSERT INTO stats.sessions(totalused, session, date) VALUES ($1, $2, $3)", self.cache.total_used, 0, current_time_format)
            except Exception as e:
                # session for today already exists.
                pass
            self.cache.session_id = self.first_result(await self.conn.fetchrow("SELECT sessionid FROM stats.sessions WHERE date = $1", current_time_format))
            self.cache.session_time_format = current_time_format
        else:
            # check that the date is correct, and if not, call get_session_id to get the new session id.
            if current_time_format != self.cache.session_time_format:
                self.cache.current_session = 0
                self.cache.session_id = None
                self.cache.session_id = await self.get_session_id()

    async def get_session_id(self):
        """Force get the session id, this will also set total used and the session id."""
        await self.process_session()
        return self.cache.session_id

    async def update_n_word_counter(self):
        """Update NWord Cache"""
        self.cache.n_word_counter = {}
        user_info = await self.conn.fetch("SELECT userid, nword FROM general.nword")
        for user in user_info:
            self.cache.n_word_counter[user[0]] = user[1]

    async def update_temp_channels(self):
        """Create the cache for temp channels."""
        self.cache.temp_channels = {}
        channels = await self.get_temp_channels()
        for channel_id, delay in channels:
            removal_time = delay
            if removal_time < 60:
                removal_time = 60
            self.cache.temp_channels[channel_id] = removal_time

    async def update_welcome_message_cache(self):
        """Create the cache for welcome messages."""
        self.cache.welcome_messages = {}
        info = await self.conn.fetch("SELECT channelid, serverid, message, enabled FROM general.welcome")
        for server in info:
            self.cache.welcome_messages[server[1]] = {"channel_id": server[0], "message": server[2], "enabled": server[3]}

    async def update_server_prefixes(self):
        """Create the cache for server prefixes."""
        self.cache.server_prefixes = {}
        info = await self.conn.fetch("SELECT serverid, prefix FROM general.serverprefix")
        for server_id, prefix in info:
            self.cache.server_prefixes[server_id] = prefix

    async def update_logging_channels(self):
        """Create the cache for logged servers and channels."""
        self.cache.logged_channels = {}
        self.cache.list_of_logged_channels = []
        logged_servers = await self.conn.fetch("SELECT id, serverid, channelid, sendall FROM logging.servers WHERE status = $1", 1)
        for p_id, server_id, channel_id, send_all in logged_servers:
            channels = await self.conn.fetch("SELECT channelid FROM logging.channels WHERE server = $1", p_id)
            for channel in channels:
                self.cache.list_of_logged_channels.append(channel[0])
            self.cache.logged_channels[server_id] = {
                "send_all": send_all,
                "logging_channel": channel_id,
                "channels": [channel[0] for channel in channels]
            }

    async def update_bot_bans(self):
        """Create the cache for banned users from the bot."""
        self.cache.bot_banned = []
        banned_users = await self.conn.fetch("SELECT userid FROM general.blacklisted")
        for user in banned_users:
            user_id = user[0]
            self.cache.bot_banned.append(user_id)

    async def update_mod_mail(self):
        """Create the cache for existing mod mail"""
        self.cache.mod_mail = {}
        mod_mail = await self.conn.fetch("SELECT userid, channelid FROM general.modmail")
        for user_id, channel_id in mod_mail:
            self.cache.mod_mail[user_id] = [channel_id]

    async def update_patreons(self):
        """Create the cache for Patrons."""
        try:
            self.cache.patrons = {}
            permanent_patrons = await self.get_patreon_users()
            # normal patrons contains super patrons as well
            normal_patrons = [patron.id for patron in await self.get_patreon_role_members(super=False)]
            super_patrons = [patron.id for patron in await self.get_patreon_role_members(super=True)]

            # the reason for db cache is because of the new discord rate limit
            # where it now takes 20+ minutes for discord cache to fully load, meaning we can only
            # access the roles after 20 minutes on boot.
            # this is an alternative to get patreons instantly and later modifying the cache after the cache loads.
            # remove any patrons from db set cache that should not exist or should be modified.
            cached_patrons = await self.conn.fetch("SELECT userid, super FROM patreon.cache")
            for user_id, super_patron in cached_patrons:
                if user_id not in normal_patrons:
                    # they are not a patron at all, so remove them from db cache
                    await self.conn.execute("DELETE FROM patreon.cache WHERE userid = $1", user_id)
                elif user_id in super_patrons and not super_patron:
                    # if they are a super patron but their db is cache is a normal patron
                    await self.conn.execute("UPDATE patreon.cache SET super = $1 WHERE userid = $2", 1, user_id)
                elif user_id not in super_patrons and super_patron:
                    # if they are not a super patron, but the db cache says they are.
                    await self.conn.execute("UPDATE patreon.cache SET super = $1 WHERE userid = $2", 0, user_id)
            cached_patrons = [patron[0] for patron in cached_patrons]  # list of user ids removing patron status.

            # fix db cache and live Irene cache
            for patron in normal_patrons:
                if patron not in cached_patrons:
                    # patron includes both normal and super patrons.
                    await self.conn.execute("INSERT INTO patreon.cache(userid, super) VALUES($1, $2)", patron, 0)
                self.cache.patrons[patron] = False
            # super patrons must go after normal patrons to have a proper boolean set because
            # super patrons have both roles.
            for patron in super_patrons:
                if patron not in cached_patrons:
                    await self.conn.execute("UPDATE patreon.cache SET super = $1 WHERE userid = $2", 1, patron)
                self.cache.patrons[patron] = True
            for patron in permanent_patrons:
                self.cache.patrons[patron[0]] = True
            return True
        except Exception as e:
            return False

    async def update_user_notifications(self):
        """Set the cache for user phrases"""
        self.cache.user_notifications = []
        notifications = await self.conn.fetch("SELECT guildid,userid,phrase FROM general.notifications")
        for guild_id, user_id, phrase in notifications:
            self.cache.user_notifications.append([guild_id, user_id, phrase])

    async def update_groups(self):
        """Set cache for group photo count"""
        self.cache.group_photos = {}
        all_group_counts = await self.conn.fetch("SELECT g.groupid, g.groupname, COUNT(f.link) FROM groupmembers.groups g, groupmembers.member m, groupmembers.idoltogroup l, groupmembers.imagelinks f WHERE m.id = l.idolid AND g.groupid = l.groupid AND f.memberid = m.id GROUP BY g.groupid ORDER BY g.groupname")
        for group in all_group_counts:
            self.cache.group_photos[group[0]] = group[2]

    async def update_idols(self):
        """Set cache for idol photo count"""
        self.cache.idol_photos = {}
        all_idol_counts = await self.conn.fetch("SELECT memberid, COUNT(link) FROM groupmembers.imagelinks GROUP BY memberid")
        for idol_id, count in all_idol_counts:
            self.cache.idol_photos[idol_id] = count

    @tasks.loop(seconds=0, minutes=0, hours=12, reconnect=True)
    async def update_cache(self):
        """Looped every 12 hours to update the cache in case of anything faulty."""
        while not self.conn:
            await asyncio.sleep(1)
        await self.create_cache()

    @tasks.loop(seconds=0, minutes=0, hours=0, reconnect=True)
    async def update_patron_cache(self):
        """Looped until patron cache is loaded.
        This was added due to intents slowing d.py cache loading rate.
        """
        # create a temporary patron list based on the db cache while waiting for the discord cache to load
        if self.conn:
            if not self.temp_patrons_loaded:
                self.cache.patrons = {}
                cached_patrons = await self.conn.fetch("SELECT userid, super FROM patreon.cache")
                for user_id, super_patron in cached_patrons:
                    self.cache.patrons[user_id] = bool(super_patron)
                self.temp_patrons_loaded = True
            while not self.discord_cache_loaded:
                await asyncio.sleep(1)
            if await self.process_cache_time(self.update_patreons, "Patrons"):
                self.update_patron_cache_hour.start()
                self.update_patron_cache.stop()

    @tasks.loop(seconds=0, minutes=0, hours=1, reconnect=True)
    async def update_patron_cache_hour(self):
        """Update Patron Cache every hour in the case of unaccounted errors."""
        # this is to make sure on the first run it doesn't update since it is created elsewhere.
        if self.loop_count != 0:
            await self.process_cache_time(self.update_patreons, "Patrons")
        self.loop_count += 1

    @tasks.loop(seconds=0, minutes=1, hours=0, reconnect=True)
    async def send_cache_data_to_data_dog(self):
        """Sends metric information about cache to data dog every minute."""
        if self.thread_pool:
            active_user_reminders = 0
            for user_id in self.cache.reminders:
                reminders = self.cache.reminders.get(user_id)
                if reminders:
                    active_user_reminders += len(reminders)
            metric_info = {
                'total_commands_used': self.cache.total_used,
                'bias_games': len(self.cache.bias_games),
                'guessing_games': len(self.cache.guessing_games),
                'patrons': len(self.cache.patrons),
                'custom_server_prefixes': len(self.cache.server_prefixes),
                'session_commands_used': self.cache.current_session,
                'user_notifications': len(self.cache.user_notifications),
                'mod_mail': len(self.cache.mod_mail),
                'banned_from_bot': len(self.cache.bot_banned),
                'logged_servers': len(self.cache.logged_channels),
                # server count is based on discord.py guild cache which takes a large amount of time to load fully.
                # There may be inaccurate data points on a new instance of the bot due to the amount of time it takes.
                'server_count': len(self.client.guilds),
                'welcome_messages': len(self.cache.welcome_messages),
                'temp_channels': len(self.cache.temp_channels),
                'amount_of_idols': len(self.cache.idols),
                'amount_of_groups': len(self.cache.groups),
                'channels_restricted': len(self.cache.restricted_channels),
                'amount_of_bot_statuses': len(self.cache.bot_statuses),
                'commands_per_minute': self.cache.commands_per_minute,
                'amount_of_custom_commands': len(self.cache.custom_commands),
                'discord_ping': self.get_ping(),
                'n_words_per_minute': self.cache.n_words_per_minute,
                'bot_api_idol_calls': self.cache.bot_api_idol_calls,
                'bot_api_translation_calls': self.cache.bot_api_translation_calls,
                'messages_received_per_min': self.cache.messages_received_per_minute,
                'errors_per_minute': self.cache.errors_per_minute,
                'wolfram_per_minute': self.cache.wolfram_per_minute,
                'urban_per_minute': self.cache.urban_per_minute,
                'active_user_reminders': active_user_reminders
            }

            # set all per minute metrics to 0 since this is a 60 second loop.
            self.cache.n_words_per_minute = 0
            self.cache.commands_per_minute = 0
            self.cache.bot_api_idol_calls = 0
            self.cache.bot_api_translation_calls = 0
            self.cache.messages_received_per_minute = 0
            self.cache.errors_per_minute = 0
            self.cache.wolfram_per_minute = 0
            self.cache.urban_per_minute = 0
            for metric_name in metric_info:
                metric_value = metric_info.get(metric_name)
                # add to thread pool to prevent blocking.
                result = (self.thread_pool.submit(self.send_metric, metric_name, metric_value)).result()

    ##################
    # ## CURRENCY ## #
    ##################

    async def register_user(self, user_id):
        """Register a user to the database if they are not already registered."""
        count = self.first_result(await self.conn.fetchrow("SELECT COUNT(*) FROM currency.Currency WHERE UserID = $1", user_id))
        if not count:
            await self.conn.execute("INSERT INTO currency.Currency (UserID, Money) VALUES ($1, $2)", user_id, "100")
            return True

    async def get_user_has_money(self, user_id):
        """Check if a user has money."""
        return not self.first_result(await self.conn.fetchrow("SELECT COUNT(*) FROM currency.Currency WHERE UserID = $1", user_id)) == 0

    async def get_balance(self, user_id):
        """Get current balance of a user."""
        if not (await self.register_user(user_id)):
            money = await self.conn.fetchrow("SELECT money FROM currency.currency WHERE userid = $1", user_id)
            return int(self.first_result(money))
        else:
            return 100

    @staticmethod
    async def shorten_balance(money):  # money must be passed in as a string.
        """Shorten an amount of money to it's value places."""
        place_names = ['', 'Thousand', 'Million', 'Billion', 'Trillion', 'Quadrillion', 'Quintillion', 'Sextillion', 'Septillion', 'Octillion', 'Nonillion', 'Decillion', 'Undecillion', 'Duodecillion', 'Tredecillion', 'Quatturodecillion', 'Quindecillion', 'Sexdecillion', 'Septendecillion', 'Octodecillion', 'Novemdecillion', 'Vigintillion', 'Centillion']
        try:
            place_values = int(math.log10(int(money)) // 3)
        except Exception as e:
            # This will have a math domain error when the amount of balance is 0.
            return "0"
        try:
            return f"{int(money) // (10 ** (3 * place_values))} {place_names[place_values]}"
        except Exception as e:
            return "Too Fucking Much$"

    async def update_balance(self, user_id, new_balance):
        """Update a user's balance."""
        await self.conn.execute("UPDATE currency.Currency SET Money = $1::text WHERE UserID = $2", str(new_balance), user_id)

    @staticmethod
    async def get_robbed_amount(author_money, user_money, level):
        """The amount to rob a specific person based on their rob level."""
        max_amount = int(user_money // 100)  # b value
        if max_amount > int(author_money // 2):
            max_amount = int(author_money // 2)
        min_amount = int((max_amount * level) // 100)
        if min_amount > max_amount:  # kind of ironic, but it is possible for min to surpass max in this case
            robbed_amount = random.randint(max_amount, min_amount)
        else:
            robbed_amount = random.randint(min_amount, max_amount)
        return robbed_amount

    @staticmethod
    def remove_commas(amount):
        """Remove all commas from a string and make it an integer."""
        return int(amount.replace(',', ''))

    #######################
    # ## MISCELLANEOUS ## #
    #######################
    async def kill_api(self):
        """restart the api"""
        source_link = "http://127.0.0.1:5123/restartAPI"
        async with self.session.get(source_link) as resp:
            log.console("Restarting API.")

    async def get_number_of_emojis(self, emojis, animated=False):
        not_animated_emojis = []
        animated_emojis = []
        for emoji in emojis:
            if emoji.animated:
                animated_emojis.append(emoji)
            else:
                not_animated_emojis.append(emoji)
        return len(animated_emojis) if animated else len(not_animated_emojis)

    @staticmethod
    async def get_server_id(ctx):
        """Get the server id by context."""
        # make sure ctx.guild exists in the case discord.py cache isn't loaded.
        if ctx.guild:
            return ctx.guild.id

    async def check_if_moderator(self, ctx):
        """Check if a user is a moderator on a server"""
        return (ctx.author.permissions_in(ctx.channel)).manage_messages

    async def check_for_bot_mentions(self, message):
        """Returns true if the message is only a bot mention and nothing else."""
        return message.content == f"<@!{keys.bot_id}>"

    async def get_api_status(self):
        end_point = f"http://127.0.0.1:{keys.api_port}"
        try:
            async with self.session.get(end_point) as r:
                return r.status == 200
        except Exception as e:
            pass

    async def get_db_status(self):
        end_point = f"http://127.0.0.1:{5050}"
        try:
            async with self.session.get(end_point) as r:
                return r.status == 200

        except Exception as e:
            pass

    async def get_images_status(self):
        end_point = f"http://images.irenebot.com/index.html"
        try:
            async with self.session.get(end_point) as r:
                return r.status == 200
        except Exception as e:
            pass

    async def send_maintenance_message(self, channel):
        try:
            reason = ""
            if self.cache.maintenance_reason:
                reason = f"\nREASON: {self.cache.maintenance_reason}"
            await channel.send(
                f">>> **A maintenance is currently in progress. Join the support server for more information. <{keys.bot_support_server_link}>{reason}**")
        except Exception as e:
            pass

    async def process_commands(self, message):
        message_sender = message.author
        if not message_sender.bot:
            message_content = message.clean_content
            message_channel = message.channel
            server_prefix = await self.get_server_prefix_by_context(message)
            # check if the user mentioned the bot and send them a help message.
            if await self.check_for_bot_mentions(message):
                await message.channel.send(
                    f"Type `{server_prefix}help` for information on commands.")
            if len(message_content) >= len(server_prefix):
                changing_prefix = [keys.bot_prefix + 'setprefix', keys.bot_prefix + 'checkprefix']
                if message.content[0:len(server_prefix)].lower() == server_prefix.lower() or message.content.lower() in changing_prefix:
                    msg_without_prefix = message.content[len(server_prefix):len(message.content)]
                    # only replace the prefix portion back to the default prefix if it is not %setprefix or %checkprefix
                    if message.content.lower() not in changing_prefix:
                        # change message.content so all on_message listeners have a bot prefix
                        message.content = keys.bot_prefix + msg_without_prefix
                    # if a user is banned from the bot.
                    if await self.check_if_bot_banned(message_sender.id):
                        try:
                            guild_id = await self.get_guild_id(message)
                        except Exception as e:
                            guild_id = None
                        if await self.check_message_is_command(message) or await self.check_custom_command_name_exists(guild_id, msg_without_prefix):
                            await self.send_ban_message(message_channel)
                    else:
                        await self.client.process_commands(message)

    async def get_guild_id(self, message):
        try:
            guild_id = message.guild.id
        except Exception as e:
            guild_id = None
        return guild_id

    async def check_for_nword(self, message):
        """Processes new messages that contains the N word."""
        message_sender = message.author
        if not message_sender.bot:
            message_content = message.clean_content
            if self.check_message_not_empty(message):
                # check if the message belongs to the bot
                    if message_content[0] != '%':
                        if self.check_nword(message_content):
                            self.cache.n_words_per_minute += 1
                            author_id = message_sender.id
                            current_amount = self.cache.n_word_counter.get(author_id)
                            if current_amount:
                                await self.conn.execute("UPDATE general.nword SET nword = $1 WHERE userid = $2::bigint",
                                                        current_amount + 1, author_id)
                                self.cache.n_word_counter[author_id] = current_amount + 1
                            else:
                                await self.conn.execute("INSERT INTO general.nword VALUES ($1,$2)", author_id, 1)
                                self.cache.n_word_counter[author_id] = 1

    async def get_dm_channel(self, user_id=None, user=None):
        try:
            if user_id:
                # user = await self.client.fetch_user(user_id)
                user = self.client.get_user(user_id)
            dm_channel = user.dm_channel
            if not dm_channel:
                await user.create_dm()
                dm_channel = user.dm_channel
            return dm_channel
        except discord.errors.HTTPException as e:
            log.console(f"{e} - get_dm_channel 1")
            return None
        except Exception as e:
            log.console(f"{e} - get_dm_channel 2")
            return None

    async def check_if_temp_channel(self, channel_id):
        """Check if a channel is a temp channel"""
        return self.cache.temp_channels.get(channel_id) is not None  # do not change structure

    async def get_temp_channels(self):
        """Get all temporary channels in the DB."""
        return await self.conn.fetch("SELECT chanid, delay FROM general.tempchannels")

    async def delete_temp_messages(self, message):
        """Delete messages that are temp channels"""
        if await self.check_if_temp_channel(message.channel.id):
            await message.delete(delay=self.cache.temp_channels.get(message.channel.id))

    async def get_disabled_server_interactions(self, server_id):
        """Get a server's disabled interactions."""
        interactions = await self.conn.fetchrow("SELECT interactions FROM general.disabledinteractions WHERE serverid = $1", server_id)
        return self.first_result(interactions)

    @staticmethod
    async def check_interaction_enabled(ctx=None, server_id=None, interaction=None):
        """Check if the interaction is disabled in the current server, RETURNS False when it is disabled."""
        if not server_id and not interaction:
            server_id = await Utility.get_server_id(ctx)
            interaction = ctx.command.name
        interactions = await resources.get_disabled_server_interactions(server_id)
        if not interactions:
            return True
        interaction_list = interactions.split(',')
        if interaction in interaction_list:
            # normally we would alert the user that the command is disabled, but discord.py uses this function.
            return False
        return True

    async def disable_interaction(self, server_id, interaction):
        """Disable an interaction (to a specific server)"""
        interaction = interaction.lower()
        interactions = await self.get_disabled_server_interactions(server_id)
        if not interactions:
            await self.conn.execute("INSERT INTO general.disabledinteractions(serverid, interactions) VALUES ($1, $2)", server_id, interaction)
        else:
            interactions = interactions.split(',')
            interactions.append(interaction)
            interactions = ','.join(interactions)
            await self.conn.execute("UPDATE general.disabledinteractions SET interactions = $1 WHERE serverid = $2", interactions, server_id)

    async def enable_interaction(self, server_id, interaction):
        """Reenable an interaction that was disabled by a server"""
        interactions = await self.get_disabled_server_interactions(server_id)
        if not interactions:
            return
        else:
            interactions = interactions.split(',')
            interactions.remove(interaction)
            interactions = ','.join(interactions)
            if not interactions:
                return await self.conn.execute("DELETE FROM general.disabledinteractions WHERE serverid = $1", server_id)
            await self.conn.execute("UPDATE general.disabledinteractions SET interactions = $1 WHERE serverid = $2", interactions, server_id)

    async def interact_with_user(self, ctx, user, interaction, interaction_type, self_interaction=False):
        await self.reset_patreon_cooldown(ctx)
        try:
            if user == discord.Member:
                user = ctx.author
            list_of_links = await self.conn.fetch("SELECT url FROM general.interactions WHERE interaction = $1", interaction_type)
            if not self_interaction:
                if ctx.author.id == user.id:
                    ctx.command.reset_cooldown(ctx)
                    return await ctx.send(f"> **{ctx.author.display_name}, you cannot perform this interaction on yourself.**")
            link = random.choice(list_of_links)
            embed = discord.Embed(title=f"**{ctx.author.display_name}** {interaction} **{user.display_name}**", color=self.get_random_color())
            if not await self.check_if_patreon(ctx.author.id):
                embed.set_footer(text=f"Become a {await self.get_server_prefix_by_context(ctx)}patreon to get rid of interaction cooldowns!")
            embed.set_image(url=link[0])
            return await ctx.send(embed=embed)
        except Exception as e:
            log.console(e)
            return await ctx.send(f"> **{ctx.author.display_name}, there are no links saved for this interaction yet.**")

    async def add_command_count(self, command_name):
        """Add 1 to the specific command count and to the count of the current minute."""
        self.cache.commands_per_minute += 1
        session_id = await self.get_session_id()
        command_count = self.cache.command_counter.get(command_name)
        if not command_count:
            await self.conn.execute("INSERT INTO stats.commands(sessionid, commandname, count) VALUES($1, $2, $3)", session_id, command_name, 1)
            self.cache.command_counter[command_name] = 1
        else:
            await self.conn.execute("UPDATE stats.commands SET count = $1 WHERE commandname = $2 AND sessionid = $3", command_count + 1, command_name, session_id)
            self.cache.command_counter[command_name] += 1

    async def add_session_count(self):
        """Adds one to the current session count for commands used and for the total used."""
        session_id = await self.get_session_id()
        self.cache.current_session += 1
        self.cache.total_used += 1
        await self.conn.execute("UPDATE stats.sessions SET session = $1, totalused = $2 WHERE sessionid = $3", self.cache.current_session, self.cache.total_used, session_id)

    async def check_message_is_command(self, message, is_command_name=False):
        """Check if a message is a command."""
        if not is_command_name:
            for command_name in self.client.all_commands:
                if command_name in message.content:
                    if len(command_name) != 1:
                        return True
            return False
        if is_command_name:
            return message in self.client.all_commands

    @staticmethod
    async def send_ban_message(channel):
        """A message to send for a user that is banned from the bot."""
        await channel.send(
            f"> **You are banned from using {keys.bot_name}. Join <{keys.bot_support_server_link}>**")

    async def ban_user_from_bot(self, user_id):
        """Bans a user from using the bot."""
        await self.conn.execute("INSERT INTO general.blacklisted(userid) VALUES ($1)", user_id)
        self.cache.bot_banned.append(user_id)

    async def unban_user_from_bot(self, user_id):
        """UnBans a user from the bot."""
        await self.conn.execute("DELETE FROM general.blacklisted WHERE userid = $1", user_id)
        try:
            self.cache.bot_banned.remove(user_id)
        except Exception as e:
            pass

    async def check_if_bot_banned(self, user_id):
        """Check if the user can use the bot."""
        return user_id in self.cache.bot_banned

    @staticmethod
    def check_nword(message_content):
        """Check if a message contains the NWord."""
        message_split = message_content.lower().split()
        return 'nigga' in message_split or 'nigger' in message_split and ':' not in message_split

    @staticmethod
    def check_if_mod(ctx, mode=0):  # as mode = 1, ctx is the author id.
        """Check if the user is a bot mod/owner."""
        if not mode:
            user_id = ctx.author.id
            return user_id in keys.mods_list or user_id == keys.owner_id
        else:
            return ctx in keys.mods_list or ctx == keys.owner_id

    def get_ping(self):
        """Get the client's ping."""
        return int(self.client.latency * 1000)

    @staticmethod
    def get_int_index(original, index):
        """Retrieves the specific index of an integer. Ex: Calling index 0 for integer 51 will return 5."""
        entire_selection = ""
        counter = 0
        for value in str(original):
            if counter < index:
                entire_selection += value
            counter += 1
        return int(entire_selection)

    @staticmethod
    def get_random_color():
        """Retrieves a random hex color."""
        r = lambda: random.randint(0, 255)
        return int(('%02X%02X%02X' % (r(), r(), r())), 16)  # must be specified to base 16 since 0x is not present

    async def create_embed(self, title="Irene", color=None, title_desc=None, footer_desc="Thanks for using Irene!"):
        """Create a discord Embed."""
        if not color:
            color = self.get_random_color()
        if not title_desc:
            embed = discord.Embed(title=title, color=color)
        else:
            embed = discord.Embed(title=title, color=color, description=title_desc)
        embed.set_author(name="Irene", url=keys.bot_website,
                         icon_url='https://cdn.discordapp.com/emojis/693392862611767336.gif?v=1')
        embed.set_footer(text=footer_desc, icon_url='https://cdn.discordapp.com/emojis/683932986818822174.gif?v=1')
        return embed

    async def check_reaction(self, msg, user_id, reaction_needed):
        """Wait for a user's reaction on a message."""
        def react_check(reaction_used, user_reacted):
            return (user_reacted.id == user_id) and (reaction_used.emoji == reaction_needed)

        try:
            reaction, user = await self.client.wait_for('reaction_add', timeout=60, check=react_check)
            return True
        except asyncio.TimeoutError:
            await msg.delete()
            return False

    @staticmethod
    async def get_cooldown_time(time):
        """Turn command cooldown of seconds into hours, minutes, and seconds."""
        time = round(time)
        time_returned = ""
        if time < 1:
            return (f"{time}s")
        if time % 86400 != time:
            days = int(time//86400)
            if days != 0:
                time = time-(days*86400)
                time_returned += f"{days}d "
        if time % 3600 != time:
            hours = int(time//3600)
            if hours != 0:
                time_returned += f"{hours}h "
        if time % 3600 != 0:
            minutes = int((time % 3600) // 60)
            if minutes != 0:
                time_returned += f"{minutes}m "
        if (time % 3600) % 60 < 60:
            seconds = (time % 3600) % 60
            if seconds != 0:
                time_returned += f"{seconds}s"
        return time_returned

    @staticmethod
    def check_embed_exists(message):
        """Check if a message has embeds."""
        try:
            for embed_check in message.embeds:
                if embed_check:
                    return True
        except Exception as e:
            pass
        return False

    @staticmethod
    def check_message_not_empty(message):
        """Check if a message has content."""
        # do not simplify
        try:
            if message.clean_content:
                return True
        except Exception as e:
            pass
        return False

    def get_message_prefix(self, message):
        """Get the prefix of a message."""
        try:
            if self.check_message_not_empty(message):
                return message.clean_content[0]
        except Exception as e:
            pass
        return None

    async def check_left_or_right_reaction_embed(self, msg, embed_lists, original_page_number=0, reaction1=keys.previous_emoji, reaction2=keys.next_emoji):
        """This method is used for going between pages of embeds."""
        await msg.add_reaction(reaction1)  # left arrow by default
        await msg.add_reaction(reaction2)  # right arrow by default

        def reaction_check(user_reaction, reaction_user):
            """Check if the reaction is the right emoji and right user."""
            return ((user_reaction.emoji == '➡') or (
                        user_reaction.emoji == '⬅')) and reaction_user != msg.author and user_reaction.message.id == msg.id

        async def change_page(c_page):
            """Waits for the user's reaction and then changes the page based on their reaction."""
            try:
                reaction, user = await self.client.wait_for('reaction_add', check=reaction_check)
                if reaction.emoji == '➡':
                    c_page += 1
                    if c_page >= len(embed_lists):
                        c_page = 0  # start from the beginning of the list
                    await msg.edit(embed=embed_lists[c_page])

                elif reaction.emoji == '⬅':
                    c_page -= 1
                    if c_page < 0:
                        c_page = len(embed_lists) - 1  # going to the end of the list
                    await msg.edit(embed=embed_lists[c_page])

                # await msg.clear_reactions()
                # await msg.add_reaction(reaction1)
                # await msg.add_reaction(reaction2)
                # only remove user's reaction instead of all reactions
                try:
                    await reaction.remove(user)
                except Exception as e:
                    pass
                await change_page(c_page)
            except Exception as e:
                log.console(f"check_left_or_right_reaction_embed - {e}")
                await change_page(c_page)
        await change_page(original_page_number)

    @staticmethod
    async def set_embed_author_and_footer(embed, footer_message):
        """Sets the author and footer of an embed."""
        embed.set_author(name="Irene", url=keys.bot_website,
                         icon_url='https://cdn.discordapp.com/emojis/693392862611767336.gif?v=1')
        embed.set_footer(text=footer_message,
                         icon_url='https://cdn.discordapp.com/emojis/683932986818822174.gif?v=1')
        return embed

    async def translate(self, text, src_lang, target_lang):
        try:
            data = {
                'text': text,
                'src_lang': await self.get_language_code(src_lang),
                'target_lang': await self.get_language_code(target_lang),
                'p_key': keys.translate_private_key
            }
            end_point = f"http://127.0.0.1:{keys.api_port}/translate"
            if self.test_bot:
                end_point = f"https://api.irenebot.com/translate"
            async with self.session.post(end_point, data=data) as r:
                self.cache.bot_api_translation_calls += 1
                if r.status == 200:
                    return json.loads(await r.text())
                else:
                    return None
        except Exception as e:
            log.console(e)
            return None

    @staticmethod
    async def get_language_code(language):
        """Returns a language code that is compatible with the papago framework."""
        language = language.lower()
        languages = ['ko', 'en', 'ja', 'zh-CN', 'zh-TW', 'es', 'fr', 'vi', 'th', 'id']
        ko_keywords = ['korean', 'ko', 'kr', 'korea', 'kor']
        eng_keywords = ['en', 'eng', 'english']
        ja_keywords = ['jp', 'jap', 'japanese', 'japan']
        zh_CN_keywords = ['chinese', 'ch', 'zh-cn', 'zhcn', 'c', 'china']
        es_keywords = ['es', 'espanol', 'spanish', 'sp']
        fr_keywords = ['french', 'fr', 'f', 'fren']
        vi_keywords = ['viet', 'vi', 'vietnamese', 'vietnam']
        th_keywords = ['th', 'thai', 'thailand']
        id_keywords = ['id', 'indonesian', 'indonesia', 'ind']
        if language in ko_keywords:
            return languages[0]
        elif language in eng_keywords:
            return languages[1]
        elif language in ja_keywords:
            return languages[2]
        elif language in zh_CN_keywords:
            return languages[3]
        elif language in es_keywords:
            return languages[5]
        elif language in fr_keywords:
            return languages[6]
        elif language in vi_keywords:
            return languages[7]
        elif language in th_keywords:
            return languages[8]
        elif languages in id_keywords:
            return languages[9]
        return None

    async def get_server_prefix(self, server_id):
        """Gets the prefix of a server by the server ID."""
        prefix = self.cache.server_prefixes.get(server_id)
        if not prefix:
            return keys.bot_prefix
        else:
            return prefix

    async def get_server_prefix_by_context(self, ctx):  # this can also be passed in as a message
        """Gets the prefix of a server by the context."""
        try:
            server_id = ctx.guild.id
        except Exception as e:
            return keys.bot_prefix
        prefix = self.cache.server_prefixes.get(server_id)
        return prefix or keys.bot_prefix

    def get_user_count(self):
        """Get the amount of users that the bot is watching over."""
        counter = 0
        for guild in self.client.guilds:
            counter += guild.member_count
        return counter

    def get_server_count(self):
        """Returns the guild count the bot is connected to."""
        return len(self.client.guilds)

    def get_channel_count(self):
        """Returns the channel count from all the guilds the bot is connected to."""
        count = 0
        for guild in self.client.guilds:
            count += len(guild.channels)
        return count

    def get_text_channel_count(self):
        """Returns the text channel count from all the guilds the bot is connected to."""
        count = 0
        for guild in self.client.guilds:
            count += len(guild.text_channels)
        return count

    def get_voice_channel_count(self):
        """Returns the voice channel count from all the guilds the bot is connected to."""
        count = 0
        for guild in self.client.guilds:
            count += len(guild.voice_channels)
        return count

    ###################
    # ## BLACKJACK ## #
    ###################

    async def check_in_game(self, user_id, ctx):  # this is meant for when it is accessed by commands outside of BlackJack.
        """Check if a user is in a game."""
        check = self.first_result(await self.conn.fetchrow("SELECT COUNT(*) From blackjack.games WHERE player1 = $1 OR player2 = $1", user_id))
        if check:
            await ctx.send(f"> **{ctx.author}, you are already in a pending/active game. Please type {await self.get_server_prefix_by_context(ctx)}endgame.**")
            return True

    async def add_bj_game(self, user_id, bid, ctx, mode):
        """Add the user to a blackjack game."""
        await self.conn.execute("INSERT INTO blackjack.games (player1, bid1, channelid) VALUES ($1, $2, $3)", user_id, str(bid), ctx.channel.id)
        game_id = await self.get_game_by_player(user_id)
        if mode != "bot":
            await ctx.send(f"> **There are currently 1/2 members signed up for BlackJack. To join the game, please type {await self.get_server_prefix_by_context(ctx)}joingame {game_id} (bid)** ")

    async def process_bj_game(self, ctx, amount, user_id):
        """pre requisites for joining a blackjack game."""
        if amount >= 0:
            if not await self.check_in_game(user_id, ctx):
                if amount > await self.get_balance(user_id):
                    await ctx.send(f"> **{ctx.author}, you can not bet more than your current balance.**")
                else:
                    return True
        else:
            await ctx.send(f"> **{ctx.author}, you can not bet a negative number.**")
        return False

    async def get_game_by_player(self, player_id):
        """Get the current game of a player."""
        return self.first_result(await self.conn.fetchrow("SELECT gameid FROM blackjack.games WHERE player1 = $1 OR player2 = $1", player_id))

    async def get_game(self, game_id):
        """Get the game from its ID"""
        return await self.conn.fetchrow("SELECT gameid, player1, player2, bid1, bid2, channelid FROM blackjack.games WHERE gameid = $1", game_id)

    async def add_player_two(self, game_id, user_id, bid):
        """Add a second player to a blackjack game."""
        await self.conn.execute("UPDATE blackjack.games SET player2 = $1, bid2 = $2 WHERE gameid = $3 ", user_id, str(bid), game_id)

    async def get_current_cards(self, user_id):
        """Get the current cards of a user."""
        in_hand = self.first_result(await self.conn.fetchrow("SELECT inhand FROM blackjack.currentstatus WHERE userid = $1", user_id))
        if in_hand is None:
            return []
        return in_hand.split(',')

    async def check_player_standing(self, user_id):
        """Check if a player is standing."""
        return self.first_result(await self.conn.fetchrow("SELECT stand FROM blackjack.currentstatus WHERE userid = $1", user_id)) == 1

    async def set_player_stand(self, user_id):
        """Set a player to stand."""
        await self.conn.execute("UPDATE blackjack.currentstatus SET stand = $1 WHERE userid = $2", 1, user_id)

    async def delete_player_status(self, user_id):
        """Remove a player's status from a game."""
        await self.conn.execute("DELETE FROM blackjack.currentstatus WHERE userid = $1", user_id)

    async def add_player_status(self, user_id):
        """Add a player's status to a game."""
        await self.delete_player_status(user_id)
        await self.conn.execute("INSERT INTO blackjack.currentstatus (userid, stand, total) VALUES ($1, $2, $2)", user_id, 0)

    async def get_player_total(self, user_id):
        """Get a player's total score."""
        return self.first_result(await self.conn.fetchrow("SELECT total FROM blackjack.currentstatus WHERE userid = $1", user_id))

    async def get_card_value(self, card):
        """Get the value of a card."""
        return self.first_result(await self.conn.fetchrow("SELECT value FROM blackjack.cards WHERE id = $1", card))

    async def get_all_cards(self):
        """Get all the cards from a deck."""
        card_tuple = await self.conn.fetch("SELECT id FROM blackjack.cards")
        all_cards = []
        for card in card_tuple:
            all_cards.append(card[0])
        return all_cards

    async def get_available_cards(self, game_id):  # pass in a list of card ids
        """Get the cards that are not occupied."""
        all_cards = await self.get_all_cards()
        available_cards = []
        game = await self.get_game(game_id)
        player1_cards = await self.get_current_cards(game[1])
        player2_cards = await self.get_current_cards(game[2])
        for card in all_cards:
            if card not in player1_cards and card not in player2_cards:
                available_cards.append(card)
        return available_cards

    async def get_card_name(self, card_id):
        """Get the name of a card."""
        return self.first_result(await self.conn.fetchrow("SELECT name FROM blackjack.cards WHERE id = $1", card_id))

    async def check_if_ace(self, card_id, user_id):
        """Check if the card is an ace and is not used."""
        aces = ["1", "14", "27", "40"]
        aces_used = await self.get_aces_used(user_id)
        if card_id in aces and card_id not in aces_used:
            aces_used.append(card_id)
            await self.set_aces_used(aces_used, user_id)
            return True
        return False

    async def set_aces_used(self, card_list, user_id):
        """Mark an ace as used."""
        separator = ','
        cards = separator.join(card_list)
        await self.conn.execute("UPDATE blackjack.currentstatus SET acesused = $1 WHERE userid = $2", cards, user_id)

    async def get_aces_used(self, user_id):
        """Get the aces that were changed from 11 to 1."""
        aces_used = self.first_result(await self.conn.fetchrow("SELECT acesused FROM blackjack.currentstatus WHERE userid = $1", user_id))
        if aces_used is None:
            return []
        return aces_used.split(',')

    def check_if_bot(self, user_id):
        """Check if the player is a bot. (The bot would be Irene)"""
        return str(self.get_int_index(keys.bot_id, 9)) in str(user_id)

    async def add_card(self, user_id):
        """Check status of a game, it's player, manages the bot that plays, and then adds a card."""
        end_game = False
        check = 0

        separator = ','
        current_cards = await self.get_current_cards(user_id)
        game_id = await self.get_game_by_player(user_id)
        game = await self.get_game(game_id)
        channel = await self.client.fetch_channel(game[5])
        stand = await self.check_player_standing(user_id)
        player1_score = await self.get_player_total(game[1])
        player2_score = await self.get_player_total(game[2])
        player1_cards = await self.get_current_cards(game[1])
        if not stand:
            available_cards = await self.get_available_cards(game_id)
            random_card = random.choice(available_cards)
            current_cards.append(str(random_card))
            cards = separator.join(current_cards)
            current_total = await self.get_player_total(user_id)
            random_card_value = await self.get_card_value(random_card)
            if current_total + random_card_value > 21:
                for card in current_cards:  # this includes the random card
                    if await self.check_if_ace(card, user_id) and check != 1:
                        check = 1
                        current_total = (current_total + random_card_value) - 10
                if check == 0:  # if there was no ace
                    current_total = current_total + random_card_value
            else:
                current_total = current_total + random_card_value
            await self.conn.execute("UPDATE blackjack.currentstatus SET inhand = $1, total = $2 WHERE userid = $3", cards, current_total, user_id)
            if current_total > 21:
                if user_id == game[2] and self.check_if_bot(game[2]):
                    if player1_score > 21 and current_total >= 16:
                        end_game = True
                        await self.set_player_stand(game[1])
                        await self.set_player_stand(game[2])
                    elif player1_score > 21 and current_total < 16:
                        await self.add_card(game[2])
                    elif player1_score < 22 and current_total > 21:
                        pass
                    else:
                        end_game = True
                elif self.check_if_bot(game[2]) and not self.check_if_bot(user_id):  # if user_id is not the bot
                    if player2_score < 16:
                        await self.add_card(game[2])
                    else:
                        await self.set_player_stand(user_id)
                        await self.set_player_stand(game[2])
                        end_game = True
            else:
                if user_id == game[2] and self.check_if_bot(game[2]):
                    if current_total < 16143478541328187392 and len(player1_cards) > 2:
                        await self.add_card(game[2])
                    if await self.check_player_standing(game[1]) and current_total >= 16:
                        end_game = True
            if not self.check_if_bot(user_id):
                if self.check_if_bot(game[2]):
                    await self.send_cards_to_channel(channel, user_id, random_card, True)
                else:
                    await self.send_cards_to_channel(channel, user_id, random_card)
        else:
            await channel.send(f"> **You already stood.**")
            if await self.check_game_over(game_id):
                await self.finish_game(game_id, channel)
        if end_game:
            await self.finish_game(game_id, channel)

    async def send_cards_to_channel(self, channel, user_id, card, bot_mode=False):
        """Send the cards to a specific channel."""
        if bot_mode:
            card_file = discord.File(fp=f'Cards/{card}.jpg', filename=f'{card}.jpg', spoiler=False)
        else:
            card_file = discord.File(fp=f'Cards/{card}.jpg', filename=f'{card}.jpg', spoiler=True)
        total_score = str(await self.get_player_total(user_id))
        if len(total_score) == 1:
            total_score = '0' + total_score  # this is to prevent being able to detect the number of digits by the spoiler
        card_name = await self.get_card_name(card)
        if bot_mode:
            await channel.send(f"<@{user_id}> pulled {card_name}. Their current score is {total_score}", file=card_file)
        else:
            await channel.send(f"<@{user_id}> pulled ||{card_name}||. Their current score is ||{total_score}||", file=card_file)

    async def compare_channels(self, user_id, channel):
        """Check if the channel is the correct channel."""
        game_id = await self.get_game_by_player(user_id)
        game = await self.get_game(game_id)
        if game[5] == channel.id:
            return True
        else:
            await channel.send(f"> **{user_id}, that game ({game_id}) is not available in this text channel.**")
            return False

    async def start_game(self, game_id):
        """Start out the game of blackjack."""
        game = await self.get_game(game_id)
        player1 = game[1]
        player2 = game[2]
        await self.add_player_status(player1)
        await self.add_player_status(player2)
        # Add Two Cards to both players [ Not in a loop because the messages should be in order on discord ]
        await self.add_card(player1)
        await self.add_card(player1)
        await self.add_card(player2)
        await self.add_card(player2)

    async def check_game_over(self, game_id):
        """Check if the blackjack game is over."""
        game = await self.get_game(game_id)
        player1_stand = await self.check_player_standing(game[1])
        player2_stand = await self.check_player_standing(game[2])
        if player1_stand and player2_stand:
            return True
        else:
            return False

    @staticmethod
    def determine_winner(score1, score2):
        """Check which player won the blackjack game."""
        if score1 == score2:
            return 'tie'
        elif score1 == 21:
            return 'player1'
        elif score2 == 21:
            return 'player2'
        elif score1 > 21 or score2 > 21:
            if score1 > 21 and score2 > 21:
                if score1 - 21 < score2 - 21:
                    return 'player1'
                else:
                    return 'player2'
            elif score1 > 21 and score2 < 21:
                return 'player2'
            elif score1 < 21 and score2 > 21:
                return 'player1'
        elif score1 < 21 and score2 < 21:
            if score1 - score2 > 0:
                return 'player1'
            else:
                return 'player2'
        else:
            return None

    async def announce_winner(self, channel, winner, loser, winner_points, loser_points, win_amount):
        """Send a message to the channel of who won the game."""
        if self.check_if_bot(winner):
            await channel.send(f"> **<@{keys.bot_id}> has won ${int(win_amount):,} with {winner_points} points against <@{loser}> with {loser_points}.**")
        elif self.check_if_bot(loser):
            await channel.send(f"> **<@{winner}> has won ${int(win_amount):,} with {winner_points} points against <@{keys.bot_id}> with {loser_points}.**")
        else:
            await channel.send(f"> **<@{winner}> has won ${int(win_amount):,} with {winner_points} points against <@{loser}> with {loser_points}.**")

    async def announce_tie(self, channel, player1, player2, tied_points):
        """Send a message to the channel of a tie."""
        if self.check_if_bot(player1) or self.check_if_bot(player2):
            await channel.send(f"> **<@{player1}> and <@{keys.bot_id}> have tied with {tied_points}**")
        else:
            await channel.send(f"> **<@{player1}> and <@{player2}> have tied with {tied_points}**")

    async def finish_game(self, game_id, channel):
        """Finish off a blackjack game and terminate it."""
        game = await self.get_game(game_id)
        player1_score = await self.get_player_total(game[1])
        player2_score = await self.get_player_total(game[2])
        if player2_score < 12 and self.check_if_bot(game[2]):
            await self.add_card(game[2])
        else:
            winner = self.determine_winner(player1_score, player2_score)
            player1_current_bal = await self.get_balance(game[1])
            player2_current_bal = await self.get_balance(game[2])
            if winner == 'player1':
                await self.update_balance(game[1], player1_current_bal + int(game[4]))
                if not self.check_if_bot(game[2]):
                    await self.update_balance(game[2], player2_current_bal - int(game[4]))
                await self.announce_winner(channel, game[1], game[2], player1_score, player2_score, game[4])
            elif winner == 'player2':
                if not self.check_if_bot(game[2]):
                    await self.update_balance(game[2], player2_current_bal + int(game[3]))
                await self.update_balance(game[1], player1_current_bal - int(game[3]))
                await self.announce_winner(channel, game[2], game[1], player2_score, player1_score, game[3])
            elif winner == 'tie':
                await self.announce_tie(channel, game[1], game[2], player1_score)
            await self.delete_game(game_id)

    async def delete_game(self, game_id):
        """Delete a blackjack game."""
        game = await self.get_game(game_id)
        await self.conn.execute("DELETE FROM blackjack.games WHERE gameid = $1", game_id)
        await self.conn.execute("DELETE FROM blackjack.currentstatus WHERE userid = $1", game[1])
        await self.conn.execute("DELETE FROM blackjack.currentstatus WHERE userid = $1", game[2])
        log.console(f"Game {game_id} deleted.")

    async def delete_all_games(self):
        """Delete all blackjack games."""
        all_games = await self.conn.fetch("SELECT gameid FROM blackjack.games")
        for games in all_games:
            game_id = games[0]
            await self.delete_game(game_id)
    ################
    # ## LEVELS ## #
    ################

    async def get_level(self, user_id, command):
        """Get the level of a command (rob/beg/daily)."""
        count = self.first_result(await self.conn.fetchrow(f"SELECT COUNT(*) FROM currency.Levels WHERE UserID = $1 AND {command} > $2", user_id, 1))
        if not count:
            level = 1
        else:
            level = self.first_result(await self.conn.fetchrow(f"SELECT {command} FROM currency.Levels WHERE UserID = $1", user_id))
        return int(level)

    async def set_level(self, user_id, level, command):
        """Set the level of a user for a specific command."""
        async def update_level():
            """Updates a user's level."""
            await self.conn.execute(f"UPDATE currency.Levels SET {command} = $1 WHERE UserID = $2", level, user_id)

        count = self.first_result(await self.conn.fetchrow(f"SELECT COUNT(*) FROM currency.Levels WHERE UserID = $1", user_id))
        if not count:
            await self.conn.execute("INSERT INTO currency.Levels VALUES($1, NULL, NULL, NULL, NULL, 1)", user_id)
            await update_level()
        else:
            await update_level()

    @staticmethod
    async def get_xp(level, command):
        """Returns money/experience needed for a certain level."""
        if command == "profile":
            return 250 * level
        return int((2 * 350) * (2 ** (level - 2)))  # 350 is base value (level 1)

    @staticmethod
    async def get_rob_percentage(level):
        """Get the percentage of being able to rob. (Every 1 is 5%)"""
        chance = int(6 + (level // 10))  # first 10 levels is 6 for 30% chance
        if chance > 16:
            chance = 16
        return chance



    #################
    # ## LOGGING ## #
    #################

    async def get_servers_logged(self):
        """Get the servers that are being logged."""
        return [server_id for server_id in self.cache.logged_channels]

    async def get_channels_logged(self):
        """Get all the channels that are being logged."""
        return self.cache.list_of_logged_channels

    async def add_to_logging(self, server_id, channel_id):  # return true if status is on
        """Add a channel to be logged."""
        if (self.first_result(await self.conn.fetchrow("SELECT COUNT(*) FROM logging.servers WHERE serverid = $1", server_id))) == 0:
            await self.conn.execute("INSERT INTO logging.servers (serverid, channelid, status, sendall) VALUES ($1, $2, $3, $4)", server_id, channel_id, 1, 1)
            server = self.cache.logged_channels.get(server_id)
            if server is None:
                self.cache.logged_channels[server_id] = {"send_all": 1, "logging_channel": channel_id, "channels": []}
            else:
                self.cache.list_of_logged_channels.append(channel_id)
                server['channels'].append(channel_id)
        else:
            await self.set_logging_status(server_id, 1)
            current_channel_id = self.first_result(await self.conn.fetchrow("SELECT channelid FROM logging.servers WHERE serverid = $1", server_id))
            if current_channel_id != channel_id:
                await self.conn.execute("UPDATE logging.servers SET channelid = $1 WHERE serverid = $2", channel_id, server_id)
        return True

    async def check_if_logged(self, server_id=None, channel_id=None):  # only one parameter should be passed in
        """Check if a server or channel is being logged."""
        if channel_id:
            return channel_id in self.cache.list_of_logged_channels
        elif server_id:
            return server_id in self.cache.logged_channels

    async def get_send_all(self, server_id):
        return (self.cache.logged_channels.get(server_id))['send_all']

    async def set_logging_status(self, server_id, status):  # status can only be 0 or 1
        """Set a server's logging status."""
        await self.conn.execute("UPDATE logging.servers SET status = $1 WHERE serverid = $2", status, server_id)
        if not status:
            self.cache.logged_channels.pop(server_id, None)
        else:
            logged_server = await self.conn.fetchrow("SELECT id, serverid, channelid, sendall FROM logging.servers WHERE serverid = $1", server_id)
            channels = await self.conn.fetch("SELECT channelid FROM logging.channels WHERE server = $1", logged_server[0])
            for channel in channels:
                self.cache.list_of_logged_channels.append(channel[0])
            self.cache.logged_channels[logged_server[1]] = {
                "send_all": logged_server[3],
                "logging_channel": logged_server[2],
                "channels": [channel[0] for channel in channels]
            }

    async def get_logging_id(self, server_id):
        """Get the ID in the table of a server."""
        return self.first_result(await self.conn.fetchrow("SELECT id FROM logging.servers WHERE serverid = $1", server_id))

    async def check_logging_requirements(self, message):
        """Check if a message meets all the logging requirements."""
        try:
            if not message.author.bot:
                if await self.check_if_logged(server_id=message.guild.id):
                    if await self.check_if_logged(channel_id=message.channel.id):
                        return True
        except Exception as e:
            pass
        return False

    @staticmethod
    async def get_attachments(message):
        """Get the attachments of a message."""
        files = None
        if message.attachments:
            files = []
            for attachment in message.attachments:
                files.append(await attachment.to_file())
        return files

    async def get_log_channel_id(self, message):
        """Get the channel where logs are made on a server."""
        return self.client.get_channel((self.cache.logged_channels.get(message.guild.id))['logging_channel'])

    #################
    # ## TWITTER ## #
    #################
    async def update_status(self, context):
        self.api.update_status(status=context)
        tweet = self.api.user_timeline(user_id=f'{keys.twitter_account_id}', count=1)[0]
        return f"https://twitter.com/{keys.twitter_username}/status/{tweet.id}"

    async def delete_status(self, context):
        self.api.destroy_status(context)

    async def recent_tweets(self, context):
        tweets = self.api.user_timeline(user_id=f'{keys.twitter_account_id}', count=context)
        final_tweet = ""
        for tweet in tweets:
            final_tweet += f"> **Tweet ID:** {tweet.id} | **Tweet:** {tweet.text}\n"
        return final_tweet

    #################
    # ## LAST FM ## #
    #################

    @staticmethod
    def create_fm_payload(method, user=None, limit=None, time_period=None):
        """Creates the payload to be sent to Last FM"""
        payload = {
            'api_key': keys.last_fm_api_key,
            'method': method,
            'format': 'json'
        }
        if user:
            payload['user'] = user
        if limit:
            payload['limit'] = limit
        if time_period:
            payload['period'] = time_period
        return payload

    async def get_fm_response(self, method, user=None, limit=None, time_period=None):
        """Receives the response from Last FM"""
        async with self.session.get(keys.last_fm_root_url, headers=keys.last_fm_headers, params=self.create_fm_payload(method, user, limit, time_period)) as response:
            return await response.json()

    async def get_fm_username(self, user_id):
        """Gets Last FM username from the DB."""
        return self.first_result(await self.conn.fetchrow("SELECT username FROM lastfm.users WHERE userid = $1", user_id))

    async def set_fm_username(self, user_id, username):
        """Sets Last FM username to the DB."""
        try:
            if not await self.get_fm_username(user_id):
                await self.conn.execute("INSERT INTO lastfm.users(userid, username) VALUES ($1, $2)", user_id, username)
            else:
                await self.conn.execute("UPDATE lastfm.users SET username = $1 WHERE userid = $2", username, user_id)
            return True
        except Exception as e:
            log.console(e)
            return e

    #################
    # ## PATREON ## #
    #################
    async def get_patreon_users(self):
        """Get the permanent patron users"""
        return await self.conn.fetch("SELECT userid from patreon.users")

    async def get_patreon_role_members(self, super_patron=False):
        """Get the members in the patreon roles."""
        support_guild = self.client.get_guild(int(keys.bot_support_server_id))
        # API call will not show role.members
        if not super_patron:
            patreon_role = support_guild.get_role(int(keys.patreon_role_id))
        else:
            patreon_role = support_guild.get_role(int(keys.patreon_super_role_id))
        return patreon_role.members

    async def check_if_patreon(self, user_id, super_patron=False):
        """Check if the user is a patreon.
        There are two ways to check if a user ia a patreon.
        The first way is getting the members in the Patreon/Super Patreon Role.
        The second way is a table to check for permanent patreon users that are directly added by the bot owner.
        -- After modifying -> We take it straight from cache now.
        """
        if user_id in self.cache.patrons:
            if super_patron:
                return self.cache.patrons.get(user_id) == super_patron
            return True

    async def add_to_patreon(self, user_id):
        """Add user as a permanent patron."""
        try:
            user_id = int(user_id)
            await self.conn.execute("INSERT INTO patreon.users(userid) VALUES($1)", user_id)
            self.cache.patrons[user_id] = True
        except Exception as e:
            pass

    async def remove_from_patreon(self, user_id):
        """Remove user from being a permanent patron."""
        try:
            user_id = int(user_id)
            await self.conn.execute("DELETE FROM patreon.users WHERE userid = $1", user_id)
            self.cache.patrons.pop(user_id, None)
        except Exception as e:
            pass

    async def reset_patreon_cooldown(self, ctx):
        """Checks if the user is a patreon and resets their cooldown."""
        # Super Patrons also have the normal Patron role.
        if await self.check_if_patreon(ctx.author.id):
            ctx.command.reset_cooldown(ctx)

    ###################
    # ## MODERATOR ## #
    ###################
    async def add_welcome_message_server(self, channel_id, guild_id, message, enabled):
        """Adds a new welcome message server."""
        await self.conn.execute(
            "INSERT INTO general.welcome(channelid, serverid, message, enabled) VALUES($1, $2, $3, $4)", channel_id,
            guild_id, message, enabled)
        self.cache.welcome_messages[guild_id] = {"channel_id": channel_id, "message": message, "enabled": enabled}

    async def check_welcome_message_enabled(self, server_id):
        """Check if a welcome message server is enabled."""
        return self.cache.welcome_messages[server_id]['enabled'] == 1

    async def update_welcome_message_enabled(self, server_id, enabled):
        """Update a welcome message server's enabled status"""
        await self.conn.execute("UPDATE general.welcome SET enabled = $1 WHERE serverid = $2", int(enabled), server_id)
        self.cache.welcome_messages[server_id]['enabled'] = int(enabled)

    async def update_welcome_message_channel(self, server_id, channel_id):
        """Update the welcome message channel."""
        await self.conn.execute("UPDATE general.welcome SET channelid = $1 WHERE serverid = $2", channel_id, server_id)
        self.cache.welcome_messages[server_id]['channel_id'] = channel_id

    async def update_welcome_message(self, server_id, message):
        await self.conn.execute("UPDATE general.welcome SET message = $1 WHERE serverid = $2", message, server_id)
        self.cache.welcome_messages[server_id]['message'] = message

    ########################
    # ## CUSTOM COMMANDS## #
    ########################

    async def check_custom_command_name_exists(self, server_id, command_name):
        if server_id:
            custom_commands = self.cache.custom_commands.get(server_id)
            if custom_commands:
                if command_name.lower() in custom_commands:
                    return True
        return False

    async def add_custom_command(self, server_id, command_name, message):
        await self.conn.execute("INSERT INTO general.customcommands(serverid, commandname, message) VALUES ($1, $2, $3)", server_id, command_name, message)
        custom_commands = self.cache.custom_commands.get(server_id)
        if custom_commands:
            custom_commands[command_name] = message
        else:
            self.cache.custom_commands[server_id] = {command_name: message}

    async def remove_custom_command(self, server_id, command_name):
        await self.conn.execute("DELETE FROM general.customcommands WHERE serverid = $1 AND commandname = $2", server_id, command_name)
        custom_commands = self.cache.custom_commands.get(server_id)
        try:
            custom_commands.pop(command_name)
        except Exception as e:
            log.console(e)

    async def get_custom_command(self, server_id, command_name):
        commands = self.cache.custom_commands.get(server_id)
        return commands.get(command_name)
    ###################
    # ## BIAS GAME ## #
    ###################

    async def create_bias_game_image(self, first_idol_id, second_idol_id):
        """Uses thread pool to create bias game image to prevent IO blocking."""
        result = (self.thread_pool.submit(self.merge_images, first_idol_id, second_idol_id)).result()
        return f"{keys.bias_game_location}{first_idol_id}_{second_idol_id}.png"

    def merge_images(self, first_idol_id, second_idol_id):
        """Merge Idol Images if the merge doesn't exist already."""
        file_name = f"{first_idol_id}_{second_idol_id}.png"
        if not self.check_file_exists(f"{keys.bias_game_location}{file_name}"):
            # open the images.
            versus_image = Image.open(f'{keys.bias_game_location}versus.png')
            first_idol_image = Image.open(f'{keys.idol_avatar_location}{first_idol_id}_IDOL.png')
            second_idol_image = Image.open(f'{keys.idol_avatar_location}{second_idol_id}_IDOL.png')

            # define the dimensions
            idol_image_width = 150
            idol_image_height = 150
            first_image_area = (0, 0)
            second_image_area = (versus_image.width - idol_image_width, 0)
            image_size = (idol_image_width, idol_image_height)

            # resize the idol images
            first_idol_image = first_idol_image.resize(image_size)
            second_idol_image = second_idol_image.resize(image_size)

            # add the idol images onto the VS image.
            versus_image.paste(first_idol_image, first_image_area)
            versus_image.paste(second_idol_image, second_image_area)

            # save the versus image.
            versus_image.save(f"{keys.bias_game_location}{file_name}")

    @staticmethod
    def check_file_exists(file_name):
        return os.path.isfile(file_name)

    async def create_bias_game_bracket(self, all_games, user_id, bracket_winner):
        result = (self.thread_pool.submit(self.create_bracket, all_games, user_id, bracket_winner)).result()
        return f"{keys.bias_game_location}{user_id}.png"

    def create_bracket(self, all_games, user_id, bracket_winner):
        def get_battle_images(idol_1_id, idol_2_id):
            return Image.open(f'{keys.idol_avatar_location}{idol_1_id}_IDOL.png'), Image.open(f'{keys.idol_avatar_location}{idol_2_id}_IDOL.png')

        def resize_images(first_img, second_img, first_img_size, second_img_size):
            return first_img.resize(first_img_size), second_img.resize(second_img_size)

        def paste_image(first_idol_img, second_idol_img, first_img_area, second_img_area):
            bracket.paste(first_idol_img, first_img_area)
            bracket.paste(second_idol_img, second_img_area)

        bracket = Image.open(f'{keys.bias_game_location}bracket8.png')
        count = 1
        for c_round in all_games:
            if len(c_round) <= 4:
                for battle in c_round:
                    first_idol, second_idol = battle[0], battle[1]
                    first_idol_info = self.cache.stored_bracket_positions.get(count)
                    second_idol_info = self.cache.stored_bracket_positions.get(count + 1)

                    # get images
                    first_idol_image, second_idol_image = get_battle_images(first_idol.id, second_idol.id)

                    # resize images
                    first_idol_image, second_idol_image = resize_images(first_idol_image, second_idol_image, first_idol_info.get('img_size'), second_idol_info.get('img_size'))

                    # paste image to bracket
                    paste_image(first_idol_image, second_idol_image, first_idol_info.get('pos'), second_idol_info.get('pos'))

                    count = count + 2

        # add winner
        idol_info = self.cache.stored_bracket_positions.get(count)
        idol_image = Image.open(f'{keys.idol_avatar_location}{bracket_winner.id}_IDOL.png')
        idol_image = idol_image.resize(idol_info.get('img_size'))
        bracket.paste(idol_image, idol_info.get('pos'))
        bracket.save(f"{keys.bias_game_location}{user_id}.png")

    #######################
    # ## GENERAL GAMES ## #
    #######################

    async def stop_game(self, ctx, games):
        """Delete an ongoing game."""
        is_moderator = await self.check_if_moderator(ctx)
        game = self.find_game(ctx.channel, games)
        if game:
            if ctx.author.id == game.host or is_moderator:
                # these are passed by reference, so can directly remove from them.
                games.remove(game)
                return await game.end_game()
            else:
                return await ctx.send("> You must be a moderator or the host of the game in order to end the game.")
        return await ctx.send("> No game is currently in session.")

    @staticmethod
    def find_game(channel, games):
        """Return a game from a list of game objects if it exists in the channel."""
        for game in games:
            if game.channel == channel:
                return game

    #################
    # ## DATADOG ## #
    #################
    @staticmethod
    def initialize_data_dog():
        """Initialize The DataDog Class"""
        initialize()

    def send_metric(self, metric_name, value):
        """Send a metric value to DataDog."""
        # some values at 0 are important such as active games, this was put in place to make sure they are updated at 0.
        metrics_at_zero = ['bias_games', 'guessing_games', 'commands_per_minute', 'n_words_per_minute',
                           'bot_api_idol_calls', 'bot_api_translation_calls', 'messages_received_per_min',
                           'errors_per_minute', 'wolfram_per_minute', 'urban_per_minute']
        if metric_name in metrics_at_zero and not value:
            value = 0
        else:
            if not value:
                return
        if self.test_bot:
            metric_name = 'test_bot_' + metric_name
        else:
            metric_name = 'irene_' + metric_name
        api.Metric.send(metric=metric_name, points=[(time.time(), value)])

    #################
    # ## WEVERSE ## #
    #################
    async def add_weverse_channel(self, channel_id, community_name):
        """Add a channel to get updates for a community"""
        community_name = community_name.lower()
        await self.conn.execute("INSERT INTO weverse.channels(channelid, communityname) VALUES($1, $2)", channel_id, community_name)
        await self.add_weverse_channel_to_cache(channel_id, community_name)

    async def add_weverse_channel_to_cache(self, channel_id, community_name):
        """Add a weverse channel to cache."""
        community_name = community_name.lower()
        channels = self.cache.weverse_channels.get(community_name)
        if channels:
            channels.append([channel_id, None, False])
        else:
            self.cache.weverse_channels[community_name] = [[channel_id, None, False]]

    async def check_weverse_channel(self, channel_id, community_name):
        """Check if a channel is already getting updates for a community"""
        channels = self.cache.weverse_channels.get(community_name.lower())
        if channels:
            for channel in channels:
                if channel_id == channel[0]:
                    return True
        return False

    async def get_weverse_channels(self, community_name):
        """Get all of the channel ids for a specific community name"""
        return self.cache.weverse_channels.get(community_name.lower())

    async def delete_weverse_channel(self, channel_id, community_name):
        """Delete a community from a channel's updates."""
        community_name = community_name.lower()
        await self.conn.execute("DELETE FROM weverse.channels WHERE channelid = $1 AND communityname = $2", channel_id, community_name)
        channels = await self.get_weverse_channels(community_name)
        for channel in channels:
            if channel[0] == channel_id:
                if channels:
                    channels.remove(channel)
                else:
                    self.cache.weverse_channels.pop(community_name)

    async def add_weverse_role(self, channel_id, community_name, role_id):
        """Add a weverse role to notify."""
        await self.conn.execute("UPDATE weverse.channels SET roleid = $1 WHERE channelid = $2 AND communityname = $3", role_id, channel_id, community_name.lower())
        await self.replace_cache_role_id(channel_id, community_name, role_id)

    async def delete_weverse_role(self, channel_id, community_name):
        """Remove a weverse role from a server (no longer notifies a role)."""
        await self.conn.execute("UPDATE weverse.channels SET roleid = NULL WHERE channel_id = $1 AND communityname = $2", channel_id, community_name.lower())
        await self.replace_cache_role_id(channel_id, community_name, None)

    async def replace_cache_role_id(self, channel_id, community_name, role_id):
        """Replace the server role that gets notified on Weverse Updates."""
        channels = self.cache.weverse_channels.get(community_name)
        for channel in channels:
            cache_channel_id = channel[0]
            if cache_channel_id == channel_id:
                channel[1] = role_id

    async def change_weverse_comment_status(self, channel_id, community_name, comments_disabled, updated=False):
        """Change a channel's subscription and whether or not they receive updates on comments."""
        comments_disabled = bool(comments_disabled)
        community_name = community_name.lower()
        if updated:
            await self.conn.execute("UPDATE weverse.channels SET commentsdisabled = $1 WHERE channelid = $2 AND communityname = $3", int(comments_disabled), channel_id, community_name)
        channels = self.cache.weverse_channels.get(community_name)
        for channel in channels:
            cache_channel_id = channel[0]
            if cache_channel_id == channel_id:
                channel[2] = comments_disabled

    async def set_comment_embed(self, notification, embed_title):
        """Set Comment Embed for Weverse."""
        artist_comments = await self.weverse_client.fetch_artist_comments(notification.community_id, notification.contents_id)
        if not artist_comments:
            return
        comment = artist_comments[0]
        embed_description = f"**{notification.message}**\n\n" \
            f"Content: **{comment.body}**\n" \
            f"Translated Content: **{await self.weverse_client.translate(comment.id, is_comment=True, p_obj=comment, community_id=notification.community_id)}**"
        embed = await self.create_embed(title=embed_title, title_desc=embed_description)
        return embed

    async def set_post_embed(self, notification, embed_title):
        """Set Post Embed for Weverse."""
        post = self.weverse_client.get_post_by_id(notification.contents_id)
        if post:
            # artist = self.weverse_client.get_artist_by_id(notification.artist_id)
            embed_description = f"**{notification.message}**\n\n" \
                f"Artist: **{post.artist.name} ({post.artist.list_name[0]})**\n" \
                f"Content: **{post.body}**\n" \
                f"Translated Content: **{await self.weverse_client.translate(post.id, is_post=True, p_obj=post, community_id=notification.community_id)}**"
            embed = await self.create_embed(title=embed_title, title_desc=embed_description)
            message = "\n".join([await self.download_weverse_post(photo.original_img_url, photo.file_name) for photo in post.photos])
            return embed, message
        return None, None

    async def download_weverse_post(self, url, file_name):
        """Downloads an image url and returns image host url."""
        async with self.session.get(url) as resp:
            fd = await aiofiles.open(keys.weverse_image_folder + file_name, mode='wb')
            await fd.write(await resp.read())
        return f"https://images.irenebot.com/weverse/{file_name}"

    async def set_media_embed(self, notification, embed_title):
        """Set Media Embed for Weverse."""
        media = self.weverse_client.get_media_by_id(notification.contents_id)
        if media:
            embed_description = f"**{notification.message}**\n\n" \
                f"Title: **{media.title}**\n" \
                f"Content: **{media.body}**\n"
            embed = await self.create_embed(title=embed_title, title_desc=embed_description)
            message = media.video_link
            return embed, message
        return None, None

    async def send_weverse_to_channel(self, channel_info, message_text, embed, is_comment, community_name):
        channel_id = channel_info[0]
        role_id = channel_info[1]
        comments_disabled = channel_info[2]
        if not (is_comment and comments_disabled):
            try:
                channel = self.client.get_channel(channel_id)
                if not channel:
                    # fetch channel instead (assuming discord.py cache did not load)
                    channel = await self.client.fetch_channel(channel_id)
            except Exception as e:
                # remove the channel from future updates as it cannot be found.
                return await self.delete_weverse_channel(channel_id, community_name.lower())
            try:
                await channel.send(embed=embed)
                if message_text:
                    # Since an embed already exists, any individual content will not load
                    # as an embed -> Make it it's own message.
                    if role_id:
                        message_text = f"<@&{role_id}>\n{message_text}"
                    await channel.send(message_text)
            except Exception as e:
                # no permission to post
                return

    #########################
    # ## SelfAssignRoles ## #
    #########################
    async def add_self_role(self, role_id, role_name, server_id):
        """Adds a self-assignable role to a server."""
        role_info = [role_id, role_name]
        await self.conn.execute("INSERT INTO selfassignroles.roles(roleid, rolename, serverid) VALUES ($1, $2, $3)", role_id, role_name, server_id)
        roles = await self.get_assignable_server_roles(server_id)
        if roles:
            roles.append(role_info)
        else:
            cache_info = self.cache.assignable_roles.get(server_id)
            if not cache_info:
                self.cache.assignable_roles[server_id] = {}
                cache_info = self.cache.assignable_roles.get(server_id)
            cache_info['roles'] = [role_info]

    async def get_self_role(self, message_content, server_id):
        """Returns a discord.Object that can be used for adding or removing a role to a member."""
        roles = await self.get_assignable_server_roles(server_id)
        if roles:
            for role in roles:
                role_id = role[0]
                role_name = role[1]
                if role_name.lower() == message_content.lower():
                    return discord.Object(role_id), role_name
        return None, None

    async def check_self_role_exists(self, role_id, role_name, server_id):
        """Check if a role exists as a self-assignable role in a server."""
        cache_info = self.cache.assignable_roles.get(server_id)
        if cache_info:
            roles = cache_info.get('roles')
            if roles:
                for role in roles:
                    c_role_id = role[0]
                    c_role_name = role[1]
                    if c_role_id == role_id or c_role_name == role_name:
                        return True
        return False

    async def remove_self_role(self, role_name, server_id):
        """Remove a self-assignable role from a server."""
        await self.conn.execute("DELETE FROM selfassignroles.roles WHERE rolename = $1 AND serverid = $2", role_name, server_id)
        cache_info = self.cache.assignable_roles.get(server_id)
        if cache_info:
            roles = cache_info.get('roles')
            if roles:
                for role in roles:
                    if role[1].lower() == role_name.lower():
                        roles.remove(role)

    async def modify_channel_role(self, channel_id, server_id):
        """Add or Change a server's self-assignable role channel."""
        def update_cache():
            cache_info = self.cache.assignable_roles.get(server_id)
            if not cache_info:
                self.cache.assignable_roles[server_id] = {'channel_id': channel_id}
            else:
                cache_info['channel_id'] = channel_id

        amount_of_results = self.first_result(await self.conn.fetchrow("SELECT COUNT(*) FROM selfassignroles.channels WHERE serverid = $1", server_id))
        if amount_of_results:
            update_cache()
            return await self.conn.execute("UPDATE selfassignroles.channels SET channelid = $1 WHERE serverid = $2", channel_id, server_id)
        await self.conn.execute("INSERT INTO selfassignroles.channels(channelid, serverid) VALUES($1, $2)", channel_id, server_id)
        update_cache()

    async def get_assignable_server_roles(self, server_id):
        """Get all the self-assignable roles from a server."""
        results = self.cache.assignable_roles.get(server_id)
        if results:
            return results.get('roles')

    async def check_for_self_assignable_role(self, message):
        """Main process for processing self-assignable roles."""
        try:
            author = message.author
            server_id = await self.get_server_id(message)
            if await self.check_self_assignable_channel(server_id, message.channel):
                if message.content:
                    prefix = message.content[0]
                    if len(message.content) > 1:
                        msg = message.content[1:len(message.content)]
                    else:
                        return
                    role, role_name = await self.get_self_role(msg, server_id)
                    await self.process_member_roles(message, role, role_name, prefix, author)
        except Exception as e:
            log.console(e)

    async def check_self_assignable_channel(self, server_id, channel):
        """Check if a channel is a self assignable role channel."""
        if server_id:
            cache_info = self.cache.assignable_roles.get(server_id)
            if cache_info:
                channel_id = cache_info.get('channel_id')
                if channel_id:
                    if channel_id == channel.id:
                        return True

    @staticmethod
    async def check_member_has_role(member_roles, role_id):
        """Check if a member has a role"""
        for role in member_roles:
            if role.id == role_id:
                return True

    async def process_member_roles(self, message, role, role_name, prefix, author):
        """Adds or removes a (Self-Assignable) role from a member"""
        if role:
            if prefix == '-':
                if await self.check_member_has_role(author.roles, role.id):
                    await author.remove_roles(role, reason="Self-Assignable Role", atomic=True)
                    return await message.channel.send(f"> {author.display_name}, You no longer have the {role_name} role.", delete_after=10)
                else:
                    return await message.channel.send(f"> {author.display_name}, You do not have the {role_name} role.", delete_after=10)
            elif prefix == '+':
                if await self.check_member_has_role(author.roles, role.id):
                    return await message.channel.send(f"> {author.display_name}, You already have the {role_name} role.", delete_after=10)
                await author.add_roles(role, reason="Self-Assignable Role", atomic=True)
                return await message.channel.send(f"> {author.display_name}, You have been given the {role_name} role.", delete_after=10)
            await message.delete()

    ##################
    # ## REMINDER ## #
    ##################

    @staticmethod
    async def determine_time_type(user_input):
        """Determine if time is relative time or absolute time
        relative time: remind me to _____ in 6 days
        absolute time: remind me to _____ at 6PM"""
        # TODO: add "on", "tomorrow", and "tonight" as valid inputs

        in_index = user_input.rfind(" in ")
        at_index = user_input.rfind(" at ")
        if in_index == at_index:
            return None, None
        if in_index > at_index:
            return True, in_index
        return False, at_index

    @staticmethod
    async def process_reminder_reason(user_input, cutoff_index):
        """Return the reminder reason that comes before in/at"""
        user_input = user_input[0: cutoff_index]
        user_words = user_input.split()
        if user_words[0].lower() == "me":
            user_words.pop(0)
        if user_words[0].lower() == "to":
            user_words.pop(0)
        return " ".join(user_words)

    async def process_reminder_time(self, user_input, type_index, is_relative_time, user_id):
        """Return the datetime of the reminder depending on the time format"""
        remind_time = user_input[type_index + len(" in "): len(user_input)]

        if is_relative_time:
            if await self.process_relative_time_input(remind_time) > 2 * 3.154e7:  # 2 years in seconds
                raise exceptions.TooLarge
            return datetime.datetime.now() + datetime.timedelta(seconds=await self.process_relative_time_input(remind_time))

        return await self.process_absolute_time_input(remind_time, user_id)

    @staticmethod
    async def process_relative_time_input(time_input):
        """Returns the relative time of the input in seconds"""
        year_aliases = ["years", "year", "yr", "y"]
        month_aliases = ["months", "month", "mo"]
        week_aliases = ["weeks", "week", "wk"]
        day_aliases = ["days", "day", "d"]
        hour_aliases = ["hours", "hour", "hrs", "hr", "h"]
        minute_aliases = ["minutes", "minute", "mins", "min", "m"]
        second_aliases = ["seconds", "second", "secs", "sec", "s"]
        time_units = [[year_aliases, 31536000], [month_aliases, 2592000], [week_aliases, 604800], [day_aliases, 86400],
                      [hour_aliases, 3600], [minute_aliases, 60], [second_aliases, 1]]

        remind_time = 0  # in seconds
        input_elements = re.findall(r"[^\W\d_]+|\d+", time_input)

        all_aliases = [alias for time_unit in time_units for alias in time_unit[0]]
        if not any(alias in input_elements for alias in all_aliases):
            raise exceptions.ImproperFormat

        for time_element in input_elements:
            try:
                int(time_element)
            except Exception as e:
                # purposefully creating an error to locate which elements are words vs integers.
                for time_unit in time_units:
                    if time_element in time_unit[0]:
                        remind_time += time_unit[1] * int(input_elements[input_elements.index(time_element) - 1])
        return remind_time

    async def process_absolute_time_input(self, time_input, user_id):
        """Returns the absolute date time of the input"""
        user_timezone = await self.get_user_timezone(user_id)
        if not user_timezone:
            raise exceptions.NoTimeZone
        cal = parsedatetime.Calendar()
        try:
            datetime_obj, _ = cal.parseDT(datetimeString=time_input, tzinfo=pytz.timezone(user_timezone))
            reminder_datetime = datetime_obj.astimezone(pytz.utc)
            return reminder_datetime
        except:
            raise exceptions.ImproperFormat

    async def get_user_timezone(self, user_id):
        """Returns the user's timezone"""
        return self.cache.timezones.get(user_id)

    async def set_user_timezone(self, user_id, timezone):
        """Set user timezone"""
        user_timezone = self.cache.timezones.get(user_id)
        self.cache.timezones[user_id] = timezone
        if user_timezone:
            await self.conn.execute("UPDATE reminders.timezones SET timezone = $1 WHERE userid = $2", timezone, user_id)
        else:
            await self.conn.execute("INSERT INTO reminders.timezones(userid, timezone) VALUES ($1, $2)", user_id, timezone)

    async def remove_user_timezone(self, user_id):
        """Remove user timezone"""
        try:
            self.cache.timezones.pop(user_id)
            await self.conn.execute("DELETE FROM reminders.timezones WHERE userid = $1", user_id)
        except:
            pass

    @staticmethod
    async def process_timezone_input(input_timezone, input_country_code=None):
        """Convert timezone abbreviation and country code to standard timezone name"""

        try:
            input_timezone = input_timezone.upper()
            input_country_code = input_country_code.upper()
        except:
            pass

        # Format if user inputs number timezones
        if any(char.isdigit() for char in input_timezone):
            try:
                timezone_offset = (re.findall(r"[+-]\d+", input_timezone))[0]
                UTC_offset = f"-{timezone_offset[1]}" if timezone_offset[0]=="+" else f"+{timezone_offset[1]}"
                input_timezone = 'Etc/GMT' + UTC_offset
            except:
                pass

        # Filter for all timezones which are equivalent to the user inputted timezone
        matching_timezones = None
        try:
            matching_timezones = set(
                filter(lambda x: datetime.datetime.now(pytz.timezone(x)).strftime("%Z") ==
                                 datetime.datetime.now(pytz.timezone(input_timezone)).strftime("%Z"),
                       pytz.common_timezones))
        except pytz.exceptions.UnknownTimeZoneError:
            matching_timezones = set(
                filter(lambda x: datetime.datetime.now(pytz.timezone(x)).strftime("%Z") == input_timezone,
                       pytz.common_timezones))
        except:
            pass

        # Find the timezones which share both same timezone input and the same country code
        if input_country_code:
            try:
                country_timezones = set(pytz.country_timezones[input_country_code])
                possible_timezones = matching_timezones.intersection(country_timezones)
            except:
                possible_timezones = matching_timezones
        else:
            possible_timezones = matching_timezones

        if not possible_timezones:
            return None

        return random.choice(list(possible_timezones))

    async def get_locale_time(self, m_time, user_timezone=None):
        """ Return a string containing locale date format. For now, enforce all weekdays to be en_US format"""
        # Set locale to server locale
        time_format = '%I:%M:%S%p %Z'
        locale.setlocale(locale.LC_ALL, '')

        if not user_timezone:
            return m_time.strftime('%a %x %I:%M:%S%p %Z')

        # Use weekday format of server
        weekday = m_time.strftime('%a')

        locale.setlocale(locale.LC_ALL, self.cache.locale_by_timezone[user_timezone])  # Set to user locale
        locale_date = m_time.strftime('%x')
        locale.setlocale(locale.LC_ALL, '')  # Reset locale back to server locale

        local_time = m_time.astimezone(pytz.timezone(user_timezone))
        local_time = local_time.strftime(time_format)
        return f"{weekday} {locale_date} {local_time}"

    async def set_reminder(self, remind_reason, remind_time, user_id):
        """Add reminder date to cache and db."""
        await self.conn.execute("INSERT INTO reminders.reminders(userid, reason, timestamp) VALUES ($1, $2, $3)", user_id, remind_reason, remind_time)
        remind_id = self.first_result(await self.conn.fetchrow("SELECT id FROM reminders.reminders WHERE userid=$1 AND reason=$2 AND timestamp=$3 ORDER BY id DESC", user_id, remind_reason, remind_time))
        user_reminders = self.cache.reminders.get(user_id)
        remind_info = [remind_id, remind_reason, remind_time]
        if user_reminders:
            user_reminders.append(remind_info)
        else:
            self.cache.reminders[user_id] = [remind_info]

    async def get_reminders(self, user_id):
        """Get the reminders of a user"""
        return self.cache.reminders.get(user_id)

    async def remove_user_reminder(self, user_id, reminder_id):
        """Remove a reminder from the cache and the database."""
        try:
            # remove from cache
            reminders = self.cache.reminders.get(user_id)
            if reminders:
                for reminder in reminders:
                    current_reminder_id = reminder[0]
                    if current_reminder_id == reminder_id:
                        reminders.remove(reminder)
        except Exception as e:
            log.console(e)
        await self.conn.execute("DELETE FROM reminders.reminders WHERE id = $1", reminder_id)

    async def get_all_reminders_from_db(self):
        """Get all reminders from the db (all users)"""
        return await self.conn.fetch("SELECT id, userid, reason, timestamp FROM reminders.reminders")

    async def get_all_timezones_from_db(self):
        """Get all timezones from the db (all users)"""
        return await self.conn.fetch("SELECT userid, timezone FROM reminders.timezones")



resources = Utility()
