"""models.py - This file contains the class definitions for the Datastore
entities used by the Game. Because these classes are also regular Python
classes they can include methods (such as 'to_form' and 'new_game')."""

import random
from datetime import date
from protorpc import messages
from google.appengine.ext import ndb


class User(ndb.Model):
    """User profile"""
    name = ndb.StringProperty(required=True)
    email =ndb.StringProperty()


class Game(ndb.Model):
    """Game object"""
    target = ndb.StringProperty()
    correct_letters = ndb.StringProperty()
    all_guesses = ndb.StringProperty(repeated=True)
    attempts_allowed = ndb.IntegerProperty(required=True)
    attempts_remaining = ndb.IntegerProperty(required=True, default=6)
    cancelled = ndb.BooleanProperty(required=True, default=False)
    game_over = ndb.BooleanProperty(required=True, default=False)
    user = ndb.KeyProperty(required=True, kind='User')

    @classmethod
    def new_game(cls, user, attempts, min_letters, max_letters):
        """Creates and returns a new game"""
        valid_attempts_allowed = [6, 8, 12]

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
        max_lines_correct_length_words = len(correct_length_words)
        pick_line = random.randrange(0, max_lines_correct_length_words)
        word = correct_length_words[pick_line].rstrip('\n')
        # set correct guesses to be the same number of underscores as the words
        # otherwise the first letter guessed will cause an error because
        # correct_letters is None in datastore,but it is expected to be a string
        correct_letters = "_ " * len(word)


        if attempts not in valid_attempts_allowed:
            raise ValueError('Attempts allowed must be 6, 8, or 12')
        if max_letters < min_letters:
            raise ValueError(
                            'Maximum letters must be greater \
                            than minimum letters.'
            )
        game = Game(parent = user,
                    user=user,
                    target=word,
                    attempts_allowed=attempts,
                    attempts_remaining=attempts,
                    correct_letters = correct_letters,
                    game_over=False)
        game.put()
        return game

    def to_form(self, message):
        """Returns a GameForm representation of the Game"""
        form = GameForm()
        form.urlsafe_key = self.key.urlsafe()
        form.user_name = self.user.get().name
        form.attempts_remaining = self.attempts_remaining
        form.correct_letters = self.correct_letters
        form.game_over = self.game_over
        form.message = message
        return form

    def end_game(self, won=False):
        """Ends the game - if won is True, the player won. - if won is False,
        the player lost."""
        self.game_over = True
        self.put()
        # Add the game to the score 'board' - this is now done every move
        """
        score = Score(
                      user=self.user,
                      date=date.today(),
                      complete=yes,
                      won=won,
                      total_guesses = self.total_guesses,
                      correct_guesses = self.correct_guesses,
                      incorrect_guesses = self.incorrect_guesses,
                      not_valid_guesses = self.not_valid_guesses,
                      solved = self.solved
                      )
        score.put()
        """


class Score(ndb.Model):
    """Score object"""
    user_name = ndb.KeyProperty(required=True, kind='User')
    date = ndb.DateProperty(required=True)
    won = ndb.BooleanProperty(required=True)
    complete = ndb.BooleanProperty(required=True)
    total_guesses = ndb.IntegerProperty(required=True, default=0)
    correct_guesses = ndb.IntegerProperty(default=0)
    incorrect_guesses = ndb.IntegerProperty(default=0)
    not_valid_guesses = ndb.IntegerProperty(default=0)
    solved = ndb.BooleanProperty(default=False)
    difficulty = ndb.StringProperty()

    def to_form(self):
        return ScoreForm(user_name=self.user_name.get().name,
                         date=str(self.date),
                         won=self.won,
                         complete=self.complete,
                         total_guesses=self.total_guesses,
                         correct_guesses=self.correct_guesses,
                         incorrect_guesses=self.incorrect_guesses,
                         not_valid_guesses=self.not_valid_guesses,
                         solved=self.solved
                         )


class GameForm(messages.Message):
    """GameForm for outbound game state information"""
    urlsafe_key = messages.StringField(1, required=True)
    attempts_remaining = messages.IntegerField(2, required=True)
    correct_letters = messages.StringField(3)
    game_over = messages.BooleanField(4, required=True)
    message = messages.StringField(5, required=True)
    user_name = messages.StringField(6, required=True)

class GameKeys(messages.Message):
    """Return keys of unfinished games per user."""
    keys = messages.StringField(1, repeated=True)

class NewGameForm(messages.Message):
    """Used to create a new game"""
    user_name = messages.StringField(1, required=True)
    # target = messages.StringField(2)
    attempts = messages.IntegerField(2, default=8)
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


class ScoreForms(messages.Message):
    """Return multiple ScoreForms"""
    items = messages.MessageField(ScoreForm, 1, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    message = messages.StringField(1, required=True)
