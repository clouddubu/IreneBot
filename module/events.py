from module import logger as log, keys
from Utility import resources as ex
from discord.ext import commands
import discord


# noinspection PyBroadException,PyPep8
class Events(commands.Cog):
    @staticmethod
    async def catch_on_message_errors(method, message):
        """Process Methods individually incase of errors. (This was created for commands in DMs)."""
        try:
            await method(message)
        except Exception as e:
            log.console(f"{e} - {method.__name__}")

    @staticmethod
    async def process_on_message(message):
        try:
            # increment message count per minute
            ex.cache.messages_received_per_minute += 1
            # delete messages that are in temp channels
            await Events.catch_on_message_errors(ex.u_miscellaneous.delete_temp_messages, message)
            # check for the n word
            await Events.catch_on_message_errors(ex.u_miscellaneous.check_for_nword, message)
            # check for self-assignable roles and process it.
            await Events.catch_on_message_errors(ex.u_self_assign_roles.check_for_self_assignable_role, message)
            # process the commands with their prefixes.
            await Events.catch_on_message_errors(ex.u_miscellaneous.process_commands, message)
        except Exception as e:
            log.console(e)

    @staticmethod
    async def error(ctx, error):
        try:
            embed = discord.Embed(title="Error", description=f"** {error} **", color=0xff00f6)
            await ctx.send(embed=embed)
            log.console(f"{error}")
            # increment general error count per minute -> Does not include unable to send messages to people.
            ex.cache.errors_per_minute += 1
        except:
            pass

    @staticmethod
    @ex.client.event
    async def on_ready():
        app = await ex.client.application_info()
        keys.bot_name = app.name
        log.console(f'{app.name} is online')
        ex.discord_cache_loaded = True

    @staticmethod
    @ex.client.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.errors.CommandNotFound):
            pass
        elif isinstance(error, commands.errors.CommandInvokeError):
            try:
                if error.original.status == 403:
                    return
            except AttributeError:
                pass

            log.console(f"Command Invoke Error -- {error} -- {ctx.command.name}")
            ex.cache.errors_per_minute += 1

        elif isinstance(error, commands.errors.CommandOnCooldown):
            await Events.error(ctx, f"You are on cooldown. Try again in {await ex.u_miscellaneous.get_cooldown_time(error.retry_after)}.")
            log.console(f"{error}")
        elif isinstance(error, commands.errors.BadArgument):
            await Events.error(ctx, error)
            ctx.command.reset_cooldown(ctx)
        elif isinstance(error, commands.errors.MissingPermissions) or isinstance(error, commands.errors.UserInputError):
            await Events.error(ctx, error)

    @staticmethod
    @ex.client.event
    async def on_guild_join(guild):
        try:
            if guild.system_channel:
                await guild.system_channel.send(f">>> Hello!\nMy prefix for this server is set to {await ex.get_server_prefix(guild.id)}.\nIf you have any questions or concerns, you may join the support server ({await ex.get_server_prefix(guild.id)}support).")
        except:
            pass
        log.console(f"{guild.name} ({guild.id}) has invited Irene.")

    @staticmethod
    @ex.client.event
    async def on_message(message):
        await Events.process_on_message(message)

    @staticmethod
    @ex.client.event
    async def on_message_edit(msg_before, message):
        msg_created_at = msg_before.created_at
        msg_edited_at = message.edited_at
        if msg_edited_at:
            difference = msg_edited_at - msg_created_at  # datetime.timedelta
            # the message has to be edited at least 60 seconds within it's creation.
            if difference.total_seconds() > 60:
                return
            await Events.process_on_message(message)

    @staticmethod
    @ex.client.event
    async def on_command(ctx):
        msg_content = ctx.message.clean_content
        if not ex.check_if_mod(ctx.author.id, 1):
            log.console(
                f"CMD LOG: ChannelID = {ctx.channel.id} - {ctx.author} ({ctx.author.id})|| {msg_content} ")
        else:
            log.console(
                f"MOD LOG: ChannelID = {ctx.channel.id} - {ctx.author} ({ctx.author.id})|| {msg_content} ")
        if await ex.u_miscellaneous.check_if_bot_banned(ctx.author.id):
            ex.u_miscellaneous.send_ban_message(ctx.channel)

    @staticmethod
    @ex.client.event
    async def on_command_completion(ctx):
        await ex.u_miscellaneous.add_command_count(ctx.command.name)
        await ex.u_miscellaneous.add_session_count()

    @staticmethod
    @ex.client.event
    async def on_guild_remove(guild):
        try:
            await ex.conn.execute("INSERT INTO stats.leftguild (id, name, region, ownerid, membercount) VALUES($1, "
                                  "$2, $3, $4, $5)", guild.id, guild.name,
                                  str(guild.region), guild.owner_id, guild.member_count)
        except Exception as e:
            log.console(f"{guild.name} ({guild.id})has already kicked Irene before. - {e}")

    @staticmethod
    @ex.client.event
    async def on_raw_reaction_add(payload):
        """Checks if a bot mod is deleting an idol photo."""
        try:
            message_id = payload.message_id
            user_id = payload.user_id
            emoji = payload.emoji
            channel_id = payload.channel_id

            async def get_msg_and_image():
                """Gets the message ID if it matches with the reaction."""
                try:
                    if channel_id == keys.dead_image_channel_id:
                        channel = ex.cache.dead_image_channel
                        msg_t = await channel.fetch_message(message_id)
                        msg_info = ex.cache.dead_image_cache.get(message_id)
                        if msg_info:
                            dead_link = msg_info[0]
                            member_id = msg_info[2]
                            guessing_game = msg_info[3]
                            image_link = await ex.u_group_members.get_google_drive_link(dead_link)
                            return msg_t, image_link, member_id, guessing_game
                except Exception as err:
                    log.console(err)
                return None, None, None, None

            if ex.check_if_mod(user_id, mode=1):
                if str(emoji) == keys.trash_emoji:
                    msg, link, idol_id, is_guessing_game = await get_msg_and_image()
                    if link:
                        await ex.conn.execute("DELETE FROM groupmembers.imagelinks WHERE link = $1 AND memberid = $2",
                                              link, idol_id)
                        await ex.u_group_members.delete_dead_link(link, idol_id)
                        await ex.u_group_members.set_forbidden_link(link, idol_id)
                        await msg.delete()

                elif str(emoji) == keys.check_emoji:
                    msg, link, idol_id, is_guessing_game = await get_msg_and_image()
                    if link:
                        await ex.u_group_members.delete_dead_link(link, idol_id)
                        await msg.delete()

                elif str(emoji) == '➡':
                    msg, link, idol_id, is_guessing_game = await get_msg_and_image()
                    if link:
                        await ex.u_group_members.set_as_group_photo(link)
                        await msg.delete()

        except Exception as e:
            log.console(e)

    @staticmethod
    @ex.client.event
    async def on_member_update(member_before, member_after):
        if not member_before.bot:
            before_roles = member_before.roles
            after_roles = member_after.roles
            added_roles = (list(set(after_roles) - set(before_roles)))
            removed_roles = (list(set(before_roles) - set(after_roles)))
            # if the user received the patron or super patron role, update cache
            if added_roles:
                for role in added_roles:
                    if role.id == keys.patreon_super_role_id:
                        ex.cache.patrons[member_after.id] = True
                    if role.id == keys.patreon_role_id:
                        ex.cache.patrons[member_after.id] = False
            # if the user was removed from patron or super patron role, update cache
            after_role_ids = [after_role.id for after_role in after_roles]
            if removed_roles:
                # only update if there were removed roles
                if keys.patreon_super_role_id in after_role_ids:
                    ex.cache.patrons[member_after.id] = True
                elif keys.patreon_role_id in after_role_ids:
                    ex.cache.patrons[member_after.id] = False
                else:
                    ex.cache.patrons.pop(member_after.id, None)

    @staticmethod
    @ex.client.event
    async def on_member_join(member):
        guild = member.guild
        server = ex.cache.welcome_messages.get(guild.id)
        if server:
            if server.get('enabled'):
                channel = guild.get_channel(server.get('channel_id'))
                if channel:
                    message = server.get("message")
                    message = message.replace("%user", f"<@{member.id}>")
                    message = message.replace("%guild_name", guild.name)
                    try:
                        await channel.send(message)
                    except:
                        pass

    @staticmethod
    @ex.client.event
    async def on_guild_post():
        """Update the server count on Top.GG and discord boats [Every 30 minutes]"""
        log.console("Server Count Updated on Top.GG")

        # discord.boats
        try:
            if ex.u_miscellaneous.get_server_count():
                await keys.discord_boats.post_stats(botid=keys.bot_id, server_count=ex.u_miscellaneous.get_server_count())
                log.console("Server Count Updated on discord.boats")
        except Exception as e:
            log.console(f"Server Count Update FAILED on discord.boats - {e}")

    @staticmethod
    @ex.client.check
    async def check_maintenance(ctx):
        """Return true if the user is a mod. If a maintenance is going on, return false for normal users."""
        try:
            check = not ex.cache.maintenance_mode or ex.check_if_mod(ctx) or ctx.author.bot
            if not check:
                await ex.u_miscellaneous.send_maintenance_message(ctx)
            return check
        except Exception as e:
            log.console(f"{e} - Check Maintenance")
            return False
