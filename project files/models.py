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
    correct_guesses = ndb.StringProperty(repeated=True)
    attempts_allowed = ndb.IntegerProperty(required=True)
    correct_guesses = ndb.StringProperty()
    attempts_remaining = ndb.IntegerProperty(required=True, default=5)
    game_over = ndb.BooleanProperty(required=True, default=False)
    user = ndb.KeyProperty(required=True, kind='User')

    @classmethod
    def new_game(cls, user, attempts, min_letters, max_letters):
        """Creates and returns a new game"""
        valid_attempts_allowed = [6, 8, 12]

        # pick random word from file, with correct length
        words_file = open('wordsEn.txt', 'r')
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

        if attempts not in valid_attempts_allowed:
            raise ValueError('Attempts allowed must be 6, 8, or 12')
        if max_letters < min_letters:
            raise ValueError(
                            'Maximum letters must be greater \
                            than minimum letters.'
            )
        game = Game(user=user,
                    target=word,
                    attempts_allowed=attempts,
                    attempts_remaining=attempts,
                    game_over=False)
        game.put()
        return game

    def to_form(self, message):
        """Returns a GameForm representation of the Game"""
        form = GameForm()
        form.urlsafe_key = self.key.urlsafe()
        form.user_name = self.user.get().name
        form.attempts_remaining = self.attempts_remaining
        form.correct_guesses = self.correct_guesses
        form.game_over = self.game_over
        form.message = message
        return form

    def end_game(self, won=False):
        """Ends the game - if won is True, the player won. - if won is False,
        the player lost."""
        self.game_over = True
        self.put()
        # Add the game to the score 'board'
        score = Score(user=self.user, date=date.today(), won=won,
                      guesses=self.attempts_allowed - self.attempts_remaining)
        score.put()


class Score(ndb.Model):
    """Score object"""
    user = ndb.KeyProperty(required=True, kind='User')
    date = ndb.DateProperty(required=True)
    won = ndb.BooleanProperty(required=True)
    guesses = ndb.IntegerProperty(required=True)

    def to_form(self):
        return ScoreForm(user_name=self.user.get().name, won=self.won,
                         date=str(self.date), guesses=self.guesses)


class GameForm(messages.Message):
    """GameForm for outbound game state information"""
    urlsafe_key = messages.StringField(1, required=True)
    attempts_remaining = messages.IntegerField(2, required=True)
    correct_guesses = messages.StringField(3)
    correct_guesses = messages.StringField(4)
    game_over = messages.BooleanField(5, required=True)
    message = messages.StringField(6, required=True)
    user_name = messages.StringField(7, required=True)


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
    guesses = messages.IntegerField(4, required=True)


class ScoreForms(messages.Message):
    """Return multiple ScoreForms"""
    items = messages.MessageField(ScoreForm, 1, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    message = messages.StringField(1, required=True)
