from Utility import resources as ex
from discord.ext import commands
from module import keys, logger as log
import asyncio
import random


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

            user_position = 0
            lb_string = ""
            for user_id, score in top_user_scores:
                user_position += 1
                score = await ex.u_guessinggame.get_user_score(difficulty.lower(), user_id)
                lb_string += f"**{user_position})** <@{user_id}> - {score}\n"
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
        await ctx.send(f"> Starting a guessing game for `{gender if gender != 'all' else 'both male and female'}` idols"
                       f" with `{difficulty}` difficulty, `{rounds}` rounds, and `{timeout}s` of guessing time.")
        await self.start_game(ctx, rounds, timeout, gender, difficulty)
        # Bot has been crashing without issue being known. Reverting creating a separate task for every game.
        # task = asyncio.create_task(self.start_game(ctx, rounds, timeout, gender, difficulty))

    @commands.command()
    async def stopgg(self, ctx):
        """Force-end a guessing game if you are a moderator or host of the game. This command is meant for any issues or if a game happens to be stuck.
        [Format: %stopgg]"""
        await ex.stop_game(ctx, ex.cache.guessing_games)

    @staticmethod
    async def start_game(ctx, rounds, timeout, gender, difficulty):
        game = Game()
        ex.cache.guessing_games.append(game)
        await game.start_game(ctx, max_rounds=rounds, timeout=timeout, gender=gender, difficulty=difficulty)
        if game in ex.cache.guessing_games:
            ex.cache.guessing_games.remove(game)


# noinspection PyBroadException,PyPep8
class Game:
    def __init__(self):
        self.photo_link = None
        self.host_ctx = None
        self.host = None
        # user_id : score
        self.players = {}
        self.rounds = 0
        self.channel = None
        self.idol = None
        self.group_names = None
        self.correct_answers = []
        self.timeout = 0
        self.max_rounds = 0
        self.force_ended = False
        self.idol_post_msg = None
        self.gender = None
        self.gender_forced = False
        # difficulty must be in this list in order for it to
        self.difficulty = None

    async def start_game(self, ctx, max_rounds=20, timeout=20, gender="all", difficulty="medium"):
        """Start a guessing game."""
        self.host_ctx = ctx
        self.channel = ctx.channel
        self.host = ctx.author.id
        self.max_rounds = max_rounds
        self.timeout = timeout
        if gender.lower() in ex.cache.male_aliases:
            self.gender = 'm'
            self.gender_forced = True
        elif gender.lower() in ex.cache.female_aliases:
            self.gender = 'f'
            self.gender_forced = True
        self.difficulty = ex.cache.difficulty_aliases.get(difficulty)
        if not self.difficulty:
            self.difficulty = 2  # set to medium by default
        await self.process_game()

    async def check_message(self):
        """Check incoming messages in the text channel and determine if it is correct."""
        if self.force_ended:
            return

        stop_phrases = ['stop', 'end']

        def check_correct_answer(message):
            """Check if the user has the correct answer."""
            return ((message.content.lower() in self.correct_answers) or
                    ((message.content.lower() == 'skip' or message.content.lower() in stop_phrases)
                     and message.author.id == self.host)) and message.channel == self.channel
        try:
            msg = await ex.client.wait_for('message', check=check_correct_answer, timeout=self.timeout)
            await msg.add_reaction(keys.check_emoji)
            if msg.content.lower() == 'skip':
                await self.print_answer(question_skipped=True)
            elif msg.content.lower() in stop_phrases and not self.force_ended:
                return await self.end_game()
            else:
                score = self.players.get(msg.author.id)
                if not score:
                    self.players[msg.author.id] = 1
                else:
                    self.players[msg.author.id] = score + 1
                self.rounds += 1
        except asyncio.TimeoutError:
            # reveal the answer
            self.rounds += 1
            if not self.force_ended:
                await self.print_answer()

    async def create_new_question(self):
        """Create a new question and send it to the channel."""
        # noinspection PyBroadException
        try:
            if self.idol_post_msg:
                try:
                    await self.idol_post_msg.delete()
                except:
                    # message does not exist.
                    pass
            if self.rounds >= self.max_rounds:
                if not self.force_ended:
                    await self.end_game()
                return True  # will properly end the game.
            self.idol = await ex.u_group_members.get_random_idol()
            if not self.gender_forced:
                self.gender = random.choice(['m', 'f'])

            while self.idol.gender != self.gender or ex.cache.difficulty_aliases[self.idol.difficulty] > self.difficulty:
                # will result in an infinite loop if there are no idols on easy mode and difficulty is easy mode.
                self.idol = await ex.u_group_members.get_random_idol()

            self.group_names = [(await ex.u_group_members.get_group(group_id)).name for group_id in self.idol.groups]
            self.correct_answers = []
            for alias in self.idol.aliases:
                self.correct_answers.append(alias.lower())
            self.correct_answers.append(self.idol.full_name.lower())
            self.correct_answers.append(self.idol.stage_name.lower())
            log.console(f'{", ".join(self.correct_answers)} - {self.channel.id}')
            self.idol_post_msg, self.photo_link = await ex.u_group_members.idol_post(self.channel, self.idol, user_id=self.host, guessing_game=True, scores=self.players)
            await self.check_message()
        except:
            pass

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
        while not await self.create_new_question():
            # the game will only end if True is returned from create_new_question()
            pass
