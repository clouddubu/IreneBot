from Utility import resources as ex
from discord.ext import commands
from module import keys, logger as log
import asyncio
import random
import async_timeout


# noinspection PyPep8,PyBroadException
class GuessingGame(commands.Cog):
    @commands.command(aliases=['ggl', 'gglb'])
    async def ggleaderboard(self, ctx, difficulty="medium", mode="server"):
        """Shows global leaderboards for guessing game
        [Format: %ggleaderboard (easy/medium/hard) (server/global)]"""
        if difficulty.lower() not in ['easy', 'medium', 'hard']:
            difficulty = "medium"

        try:
            if mode.lower() not in ["server", "global"]:
                mode = "server"
            if mode == "server":
                server_id = await ex.get_server_id(ctx)
                if not server_id:
                    return await ctx.send("> You should not use this command in DMs.")
                members = f"({', '.join([str(member.id) for member in ex.client.get_guild(server_id).members])})"
                top_user_scores = await ex.u_guessinggame.get_guessing_game_top_ten(difficulty, members=members)

            else:
                top_user_scores = await ex.u_guessinggame.get_guessing_game_top_ten(difficulty)

            lb_string = ""
            for user_position, (user_id, score) in enumerate(top_user_scores):
                score = await ex.u_guessinggame.get_user_score(difficulty.lower(), user_id)
                lb_string += f"**{user_position + 1})** <@{user_id}> - {score}\n"
            m_embed = await ex.create_embed(title=f"Guessing Game Leaderboard ({difficulty.lower()}) ({mode})",
                                            title_desc=lb_string)
            await ctx.send(embed=m_embed)
        except Exception as e:
            log.console(e)
            return await ctx.send(f"> You may not understand this error. Please report it -> {e}")

    @commands.command(aliases=['gg'])
    async def guessinggame(self, ctx, gender="all", difficulty="medium", rounds=20, timeout=20):
        """Start an idol guessing game in the current channel. The host of the game can use `stop`/`end` to end the game or `skip` to skip the current round without affecting the round number.
        [Format: %guessinggame (Male/Female/All) (easy/medium/hard) (# of rounds - default 20) (timeout for each round - default 20s)]"""
        if not ctx.guild:
            return await ctx.send("> You are not allowed to play guessing game in DMs.")
        if ex.find_game(ctx.channel, ex.cache.guessing_games):
            server_prefix = await ex.get_server_prefix_by_context(ctx)
            return await ctx.send(f"> **A guessing game is currently in progress in this channel. If this is a mistake, use `{server_prefix}stopgg`.**")
        if rounds > 60 or timeout > 60:
            return await ctx.send("> **ERROR -> The max rounds is 60 and the max timeout is 60s.**")
        elif rounds < 1 or timeout < 3:
            return await ctx.send("> **ERROR -> The minimum rounds is 1 and the minimum timeout is 3 seconds.**")
        await self.start_game(ctx, rounds, timeout, gender, difficulty)
        # Bot has been crashing without issue being known. Reverting creating a separate task for every game.
        # task = asyncio.create_task(self.start_game(ctx, rounds, timeout, gender, difficulty))

    @commands.command()
    async def stopgg(self, ctx):
        """Force-end a guessing game if you are a moderator or host of the game. This command is meant for any issues or if a game happens to be stuck.
        [Format: %stopgg]"""
        await ex.stop_game(ctx, ex.cache.guessing_games)

    @commands.command()
    async def gglist(self, ctx, set=1):
        """Shows the groups in your custom guessing game set.
        [Format: %gglist (preset number)]"""
        if not await ex.u_patreon.check_if_patreon(ctx.author.id):
            return await ctx.send("> You must be a patron in order to create your own custom guessing game sets.")
        idol_sets = ex.cache.guessing_game_set.get(ctx.guild.id)
        if not idol_sets:
            return await ctx.send(f"There are currently no groups in set {set}.")

    @commands.command()
    async def ggedit(self, ctx, set=1):
        """Enables edit mode for the groups available in a guessing game set.
        [Format: %%ggedit (set number)"""
        start_message = f"""
You are now editing guessing game set {set}.

To add a group, use a `+` followed by the name of the group you want added to this set (one group per message).
To remove a group, use a `-` followed by the name of the group to be removed (one group per message).

Example: `+loona` to add Loona to the set. `-bts` to remove bts from the set.
"""
        await ctx.send(start_message)

    @commands.command(aliases=["stopggedit"])
    async def ggstopedit(self, ctx):
        """Force ends the editing of a server's guessing game idol preset.
        [Format: %ggstopedit]"""
        pass

    @staticmethod
    async def process_guessing_game_edit_set(message):
        if not message.content or message.author.bot:
            return


    @commands.command()
    async def ggtest(self, ctx, *, group_name):
        group = next(iter(await ex.u_group_members.get_group_where_group_matches_name(group_name)), None)
        idol_string = ""
        for idol_id in group.members:
            idol = await ex.u_group_members.get_member(idol_id)
            idol_string += f"{idol.full_name} - {idol.stage_name}\n"
        await ctx.send(idol_string)

    @staticmethod
    async def start_game(ctx, rounds, timeout, gender, difficulty):
        game = Game(ctx, max_rounds=rounds, timeout=timeout, gender=gender, difficulty=difficulty)
        ex.cache.guessing_games.append(game)
        await ctx.send(f"> Starting a guessing game for `{game.gender if game.gender != 'all' else 'both male and female'}` idols"
                       f" with `{game.difficulty}` difficulty, `{rounds}` rounds, and `{timeout}s` of guessing time.")
        await game.process_game()
        if game in ex.cache.guessing_games:
            log.console(f"Ending Guessing Game in {ctx.channel.id}")
            ex.cache.guessing_games.remove(game)


    # @stopgg.before_invoke
    # @guessinggame.before_invoke
    # @ggleaderboard.before_invoke
    # async def disabled_weverse(self, ctx):
    #     await ctx.send(f"""**Guessing Game will be disabled until we find out Irene's API issue.**""")
    #     raise Exception

# noinspection PyBroadException,PyPep8
class Game:
    def __init__(self, ctx, max_rounds=20, timeout=20, gender="all", difficulty="medium"):
        self.photo_link = None
        self.host_ctx = ctx
        self.host = ctx.author.id
        # user_id : score
        self.players = {}
        self.rounds = 0
        self.channel = ctx.channel
        self.idol = None
        self.group_names = None
        self.correct_answers = []
        self.timeout = timeout
        self.max_rounds = max_rounds
        self.force_ended = False
        self.idol_post_msg = None
        self.gender = None
        self.post_attempt_timeout = 10
        if gender.lower() in ex.cache.male_aliases:
            self.gender = 'male'
        elif gender.lower() in ex.cache.female_aliases:
            self.gender = 'female'
        else:
            self.gender = "all"
        if difficulty in ex.cache.difficulty_selection.keys():
            self.difficulty = difficulty
        else:
            self.difficulty = "medium"

        # create the game's idol pool.
        idol_gender_set = ex.cache.gender_selection.get(self.gender)
        idol_difficulty_set = ex.cache.difficulty_selection.get(self.difficulty)
        self.idol_set = list(idol_gender_set & idol_difficulty_set)

    async def check_message(self):
        """Check incoming messages in the text channel and determine if it is correct."""
        if self.force_ended:
            return

        stop_phrases = ['stop', 'end']

        def check_correct_answer(message):
            """Check if the user has the correct answer."""
            if message.channel != self.channel:
                return False
            if message.content.lower() in self.correct_answers:
                return True
            if message.author.id == self.host:
                return message.content.lower() == 'skip' or message.content.lower() in stop_phrases

        try:
            msg = await ex.client.wait_for('message', check=check_correct_answer, timeout=self.timeout)
            await msg.add_reaction(keys.check_emoji)
            if msg.content.lower() == 'skip':
                await self.print_answer(question_skipped=True)
                return
            elif msg.content.lower() in self.correct_answers:
                score = self.players.get(msg.author.id)
                if not score:
                    self.players[msg.author.id] = 1
                else:
                    self.players[msg.author.id] = score + 1
                self.rounds += 1
            elif msg.content.lower() in stop_phrases or self.force_ended:
                self.force_ended = True
                return
            else:
                # Forbidden error
                raise ex.exceptions.ShouldNotBeHere(f"msg passed check_correct_message() but was not correct, "
                                                    f"'skip', or 'stop'. msg: {msg.content.lower()}")
        except asyncio.TimeoutError:
            if not self.force_ended:
                await self.print_answer()
                self.rounds += 1

    async def create_new_question(self):
        """Create a new question and send it to the channel."""
        # noinspection PyBroadException
        question_posted = False
        while not question_posted:
            try:
                if self.idol_post_msg:
                    try:
                        await self.idol_post_msg.delete()
                    except:
                        # message does not exist.
                        pass

                # Create random idol selection
                if not self.idol_set:
                    raise LookupError(f"No valid idols for the group {self.gender} and {self.difficulty}.")
                self.idol = random.choice(self.idol_set)

                # Create acceptable answers
                self.group_names = [(await ex.u_group_members.get_group(group_id)).name for group_id in self.idol.groups]
                self.correct_answers = [alias.lower() for alias in self.idol.aliases]
                self.correct_answers.append(self.idol.full_name.lower())
                self.correct_answers.append(self.idol.stage_name.lower())

                # Skip this idol if it is taking too long
                async with async_timeout.timeout(self.post_attempt_timeout) as posting:
                    self.idol_post_msg, self.photo_link = await ex.u_group_members.idol_post(self.channel, self.idol, user_id=self.host, guessing_game=True, scores=self.players)
                    log.console(f'{", ".join(self.correct_answers)} - {self.channel.id}')

                if posting.expired:
                    log.console(f"Posting for {self.idol.full_name} ({self.idol.stage_name}) [{self.idol.id}]"
                                f" took more than {self.post_attempt_timeout}")
                    continue
                question_posted = True
            except LookupError:
                raise
            except Exception as e:
                log.console(e)
                continue

    async def display_winners(self):
        """Displays the winners and their scores."""
        final_scores = ""
        if self.players:
            for user_id in self.players:
                final_scores += f"<@{user_id}> -> {self.players.get(user_id)}\n"
        return await self.channel.send(f">>> Guessing game has finished.\nScores:\n{final_scores}")

    async def end_game(self):
        """Ends a guessing game."""
        await self.channel.send(f"The current game has now ended.")
        self.force_ended = True
        self.rounds = self.max_rounds
        await self.update_scores()
        await self.display_winners()

    async def update_scores(self):
        """Updates all player scores"""
        for user_id in self.players:
            await ex.u_guessinggame.update_user_guessing_game_score(self.difficulty, user_id=user_id,
                                                                    score=self.players.get(user_id))

    async def print_answer(self, question_skipped=False):
        """Prints the current round's answer."""
        skipped = ""
        if question_skipped:
            skipped = "Question Skipped. "
        msg = await self.channel.send(f"{skipped}The correct answer was `{self.idol.full_name} ({self.idol.stage_name})`"
                                      f" from the following group(s): `{', '.join(self.group_names)}`", delete_after=15)
        # create_task should not be awaited because this is meant to run in the background to check for reactions.
        try:
            # noinspection PyUnusedLocal
            task = asyncio.create_task(ex.u_group_members.check_idol_post_reactions(msg, self.host_ctx.message, self.idol, self.photo_link, guessing_game=True))
        except Exception as e:
            log.console(e)

    async def process_game(self):
        """Ignores errors and continuously makes new questions until the game should end."""
        try:
            while self.rounds < self.max_rounds and not self.force_ended:
                try:
                    await self.create_new_question()
                except LookupError as e:
                    await self.channel.send(f"The gender and difficulty settings selected have no idols.")
                    log.console(e)
                    return
                await self.check_message()
            await self.end_game()
        except Exception as e:
            await self.channel.send(f"An error has occurred and the game has ended. Please report this.")
            log.console(e)
