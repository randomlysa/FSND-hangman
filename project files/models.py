"""models.py - This file contains the class definitions for the Datastore
entities used by the Game. Because these classes are also regular Python
classes they can include methods (such as 'to_form' and 'new_game')."""

import logging
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
    won = ndb.BooleanProperty()

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
        # set target_revealed to be the same number of underscores as the number
        # of letters in the word
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
        form.target_word = self.target_word
        form.target_revealed = self.target_revealed
        form.correct_letters = self.correct_letters
        form.incorrect_letters = self.incorrect_letters
        form.attempts_allowed = self.attempts_allowed
        form.attempts_remaining = self.attempts_remaining
        form.game_over = self.game_over
        form.user_name = self.user.get().name
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

    def end_game(self, game, user, result, difficulty):
        """Ends the game and sets the score.
        If result is True, the player won.
        If result is False, the player lost."""
        self.won = result
        self.game_over = True
        # save game result
        self.put()

        # calculate the score
        setScore = int(
            (
                float(len(self.correct_letters)) / (len(self.correct_letters) + len(self.incorrect_letters)) * 1000
            )
        )

        user_key = ndb.Key(urlsafe=user)
        game_key = ndb.Key(urlsafe=game)

        # set the score
        score = Score(
            # game is the parent
            parent=game_key,
            user_key=user_key,
            difficulty=difficulty,
            score=setScore,
            date=date.today()
        )
        score.put()


class Score(ndb.Model):
    """Score object"""
    user_key = ndb.KeyProperty(required=True, kind='User')
    date = ndb.DateProperty(required=True)
    difficulty = ndb.StringProperty()
    score = ndb.IntegerProperty(default=0)

    def to_form(self):
        return ScoreForm(
            user_key=self.user_key,
            date=str(self.date),
            difficulty=self.difficulty,
            score=self.score
        )


class UserRank(ndb.Model):
    """User Rank object"""
    user_name = ndb.KeyProperty(required=True, kind='User')
    difficulty = ndb.StringProperty(required=True)
    performance = ndb.IntegerProperty(required=True)

    def to_form(self):
        return UserRankForm(
                        user_name=self.user_name.get().name,
                        performance=self.performance,
                        difficulty=self.difficulty
                        )

    @classmethod
    def set_user_rank(cls, user, difficulty):
        """Updates a users rank after a game has been completed."""
        # get scores for all games by this user in every difficulty level
        all_games_played = Score.query(ancestor=user).fetch()
        games_this_difficulty_level = 0
        wins = 0
        # count games/wins for this difficulty level
        for game in all_games_played:
            if game.difficulty == difficulty and game.complete is True:
                games_this_difficulty_level += 1
                if game.won is True:
                    wins += 1

        win_percentage = \
            int((float(wins) / games_this_difficulty_level) * 1000)
        rank = UserRank.query(
                ndb.AND(UserRank.user_name == user,
                    ndb.AND(UserRank.difficulty == difficulty))
            ).get()
        if rank is None:
            # rank is empty, create and save it
            rank = UserRank(
                user_name=user,
                difficulty=difficulty,
                performance=win_percentage
            )
            rank.put()
        else:
            # rank exists. update it.
            rank.performance = win_percentage
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
    user_name = messages.StringField(11, required=True)
    body_parts = messages.StringField(12)


class GameKeysForm(messages.Message):
    """Return keys of unfinished games per user."""
    keys = messages.StringField(1, repeated=True)


class NewGameForm(messages.Message):
    """Used to create a new game"""
    user_name = messages.StringField(1, required=True)
    # target = messages.StringField(2)
    attempts = messages.IntegerField(2, default=9)
    min_letters = messages.IntegerField(3, default=6)
    max_letters = messages.IntegerField(4, default=12)


class MakeMoveForm(messages.Message):
    """Used to make a move in an existing game"""
    guess = messages.StringField(1, required=True)


class ScoreForm(messages.Message):
    """ScoreForm for outbound Score information"""
    user_name = messages.StringField(1, required=True)
    date = messages.StringField(2, required=True)
    won = messages.BooleanField(3, required=True)
    complete = messages.BooleanField(4, required=True, default=False)
    total_guesses = messages.IntegerField(5, required=True)
    correct_guesses = messages.IntegerField(6)
    incorrect_guesses = messages.IntegerField(7)
    not_valid_guesses = messages.IntegerField(8)
    solved = messages.BooleanField(9)
    difficulty = messages.StringField(10)
    score = messages.IntegerField(11)


class ScoreForms(messages.Message):
    """Return multiple ScoreForms"""
    items = messages.MessageField(ScoreForm, 1, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    message = messages.StringField(1, required=True)


class UserRankForm(messages.Message):
    user_name = messages.StringField(1, required=True)
    difficulty = messages.StringField(3, required=True)
    performance = messages.IntegerField(2, required=True)


class UserRankForms(messages.Message):
    rankings = messages.MessageField(UserRankForm, 1, repeated=True)


class GameHistoryForm(messages.Message):
    """StringMessage-- outbound (single) string message"""
    history = messages.StringField(1)
