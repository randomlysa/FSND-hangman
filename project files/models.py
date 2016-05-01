"""models.py - This file contains the class definitions for the Datastore
entities used by the game Hangman."""

import random
from datetime import date
from protorpc import messages
from google.appengine.ext import ndb


class User(ndb.Model):
    """User profile"""
    name = ndb.StringProperty(required=True)
    email = ndb.StringProperty()


class Game(ndb.Model):
    """Game object"""
    target_word = ndb.StringProperty()
    target_revealed = ndb.StringProperty(default='')
    correct_letters = ndb.StringProperty(default='')
    incorrect_letters = ndb.StringProperty(default='')
    game_history = ndb.StringProperty(repeated=True)
    attempts_allowed = ndb.IntegerProperty(required=True)
    attempts_remaining = ndb.IntegerProperty(required=True, default=6)
    cancelled = ndb.BooleanProperty(required=True, default=False)
    game_over = ndb.BooleanProperty(required=True, default=False)
    user = ndb.KeyProperty(required=True, kind='User')
    won = ndb.BooleanProperty(default=False)

    @classmethod
    def new_game(cls, user, attempts, min_letters, max_letters):
        """Creates and returns a new game"""
        valid_attempts_allowed = [6, 9, 12]

        # pick random word from file, with correct length
        # https://github.com/first20hours/google-10000-english
        # removed words shorter than 4 letters
        words_file = open('google-10000-english-usa.txt', 'r')
        all_words = words_file.readlines()

        # create a list of words that are the correct length
        correct_length_words = []
        for word in all_words:
            # if word lenth is less than max letters and more than min letters
            if len(word) <= max_letters + 1 and len(word) >= min_letters + 1:
                correct_length_words.append(word)

        # now we are working with a list of words that are the correct length
        # get the number of 'correct length words' this will be the upper
        # range for randrange.
        max_lines_correct_length_words = len(correct_length_words)
        # assign a random number to pick_line. this will be the word that is
        # used for this hangman game.
        pick_line = random.randrange(0, max_lines_correct_length_words)
        word = correct_length_words[pick_line].rstrip('\n')
        # set target_revealed to be the same number of underscores
        # as the number of letters in the word
        target_revealed = "_ " * len(word)

        if attempts not in valid_attempts_allowed:
            raise ValueError('Attempts allowed must be 6, 9, or 12')
        if max_letters < min_letters:
            raise ValueError(
                'Maximum letters must be greater than minimum letters.'
            )
        # create the game and save it to datastore.
        game = Game(parent=user,
                    user=user,
                    target_word=word,
                    attempts_allowed=attempts,
                    attempts_remaining=attempts,
                    target_revealed=target_revealed,
                    game_over=False)
        game.put()
        return game

    def to_form(self, message):
        """Returns a GameForm representation of the Game"""
        form = GameForm()
        form.urlsafe_key = self.key.urlsafe()
        form.target_revealed = self.target_revealed
        form.correct_letters = self.correct_letters
        form.incorrect_letters = self.incorrect_letters
        form.attempts_allowed = self.attempts_allowed
        form.attempts_remaining = self.attempts_remaining
        form.game_over = self.game_over
        form.user = self.user.get().name
        form.won = self.won
        form.message = message

        # convert attempts_remaining to body_parts to be drawn
        if form.attempts_allowed == 6:
            body_parts = [
                'head', 'body', 'left leg', 'right leg', 'left hand',
                'right hand'
            ]
        elif form.attempts_allowed == 9:
            body_parts = [
                'head', 'eyes', 'ears', 'hair', 'body', 'left leg',
                'right leg', 'left hand', 'right hand'
            ]
        elif form.attempts_allowed == 12:
            body_parts = [
                'head', 'left eye', 'right eye', 'mouth', 'nose',
                'left ear', 'right ear', 'body', 'left leg', 'right leg',
                'left hand', 'right hand'
            ]

        # count incorrect guesses so we know how many body parts to draw/return
        incorrect_guesses = form.attempts_allowed - form.attempts_remaining
        form.body_parts = str(body_parts[0:incorrect_guesses])

        return form

    def convert_int_to_difficulty(self, int_difficulty):
        """ Converts attempts_allows (int representation of difficulty level)
        to a word representation of difficulty level (easy, medium, hard) """
        if int_difficulty == 6:
            set_difficulty = 'hard'
        elif int_difficulty == 9:
            set_difficulty = 'medium'
        elif int_difficulty == 12:
            set_difficulty = 'easy'

        return set_difficulty

    def end_game(self, game, user, result, difficulty):
        """Ends the game, sets the score, and updates user rank.
        If result is True, the player won.
        If result is False, the player lost."""
        self.won = result
        self.game_over = True
        # save game result
        self.put()

        # calculate the score
        set_score = int(
            (
                float(
                    len(self.correct_letters)
                ) /
                (
                    len(self.correct_letters) + len(self.incorrect_letters)
                ) * 1000
            )
        )

        user = ndb.Key(urlsafe=user)
        game_key = ndb.Key(urlsafe=game)

        # set the score
        score = Score(
            # game is the parent
            parent=game_key,
            user=user,
            difficulty=difficulty,
            score=set_score,
            date=date.today()
        )
        score.put()

        # update user rank
        UserRank.set_user_rank(user, difficulty)


class Score(ndb.Model):
    """Score object. *Each game* has a score, which is the percent of letters
    that was correctly guessed:
    len(correct_letters) / (len(correct_letters) + len(incorrect_letters))"""
    user = ndb.KeyProperty(required=True, kind='User')
    date = ndb.DateProperty(required=True)
    difficulty = ndb.StringProperty()
    score = ndb.IntegerProperty(default=0)

    def to_form(self):
        """Sends Score message."""
        return ScoreForm(
            user=self.user.get().name,
            date=str(self.date),
            difficulty=self.difficulty,
            score=self.score
        )


class UserRank(ndb.Model):
    """User Rank object. This is the users overall win percentage per each
    difficulty level. For each difficuly level, if a user's cancelled games
    is over 10%, his overall rank for that difficulty level is affected:
    UserRank *= completion percentage for this rank."""
    user = ndb.KeyProperty(required=True, kind='User')
    difficulty = ndb.StringProperty(required=True)
    performance = ndb.IntegerProperty(required=True)

    def to_form(self):
        """Sends UserRank message."""
        return UserRankForm(
            user=self.user.get().name,
            performance=self.performance,
            difficulty=self.difficulty
        )

    @classmethod
    def set_user_rank(cls, user, difficulty):
        """Updates a users rank after a game has been completed."""
        # get scores for all games by this user in every difficulty level
        all_games_played = Game.query(ancestor=user).fetch()
        games_this_difficulty_level = 0  # game.game_over = True
        games_cancelled = 0
        games_won = 0

        # convert difficulty to int_difficulty
        if difficulty == 'hard':
            int_difficulty = 6
        elif difficulty == 'medium':
            int_difficulty = 9
        elif difficulty == 'easy':
            int_difficulty = 12

        # count games/games_won/cancelled for this difficulty level
        for game in all_games_played:
            if game.attempts_allowed == int_difficulty:
                # count only games that are over. the user might have several
                # not started games. we aren't looking for those.
                if game.game_over is True:
                    games_this_difficulty_level += 1
                if game.won is True:
                    games_won += 1
                if game.cancelled is True:
                    games_cancelled += 1

        if games_this_difficulty_level != 0:
            win_percentage = \
                int((float(games_won) / games_this_difficulty_level) * 1000)

            percent_finished = float(games_this_difficulty_level) \
                / (games_cancelled + games_this_difficulty_level)
        else:
            # if no games have been finished, 100% of the games must have been
            # cancelled
            percent_finished = 0
            win_percentage = 0

        # a user must keep his percent_finished above 90%. otherwise, his Rank
        # is multiplied by the percent of games he has finished
        if percent_finished < 0.9:
            # set user's new_performance to win_percentage * percent_finished
            new_performance = int(percent_finished * win_percentage)
        else:
            # otherwise the new_performance is the win_percentage
            new_performance = win_percentage

        # try to get the user's current rank
        rank = UserRank.query(
            ndb.AND(UserRank.user == user,
                    ndb.AND(UserRank.difficulty == difficulty))
        ).get()

        if rank is None:
            # rank is empty, create and save it
            rank = UserRank(
                user=user,
                difficulty=difficulty,
                performance=new_performance
            )
            rank.put()
        else:
            # rank exists. update it.
            rank.performance = new_performance
            rank.put()


class GameForm(messages.Message):
    """GameForm for outbound game state information"""
    urlsafe_key = messages.StringField(1, required=True)
    attempts_allowed = messages.IntegerField(3, required=True)
    attempts_remaining = messages.IntegerField(4, required=True)
    target_word = messages.StringField(5)
    target_revealed = messages.StringField(6)
    correct_letters = messages.StringField(7)
    incorrect_letters = messages.StringField(8)
    game_over = messages.BooleanField(9, required=True)
    message = messages.StringField(10, required=True)
    user = messages.StringField(11, required=True)
    body_parts = messages.StringField(12)
    won = messages.BooleanField(13)


class GameKeysForm(messages.Message):
    """Return keys of unfinished games per user."""
    keys = messages.StringField(1, repeated=True)


class NewGameForm(messages.Message):
    """Used to create a new game"""
    user = messages.StringField(1, required=True)
    # target = messages.StringField(2)
    attempts = messages.IntegerField(2, default=9)
    min_letters = messages.IntegerField(3, default=6)
    max_letters = messages.IntegerField(4, default=12)


class MakeMoveForm(messages.Message):
    """Used to make a move in an existing game"""
    guess = messages.StringField(1, required=True)


class ScoreForm(messages.Message):
    """ScoreForm for outbound Score information"""
    user = messages.StringField(1, required=True)
    date = messages.StringField(2, required=True)
    difficulty = messages.StringField(3)
    score = messages.IntegerField(4)


class ScoreForms(messages.Message):
    """Return multiple ScoreForms"""
    items = messages.MessageField(ScoreForm, 1, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    message = messages.StringField(1, required=True)


class UserRankForm(messages.Message):
    user = messages.StringField(1, required=True)
    difficulty = messages.StringField(3, required=True)
    performance = messages.IntegerField(2, required=True)


class UserRankForms(messages.Message):
    rankings = messages.MessageField(UserRankForm, 1, repeated=True)


class GameHistoryForm(messages.Message):
    """StringMessage-- outbound (single) string message"""
    history = messages.StringField(1)
