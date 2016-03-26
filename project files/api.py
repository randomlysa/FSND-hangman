"""api.py - Create and configure the Game API exposing the resources.
This can also contain game logic. For more complex games it would be wise to
move game logic to another file. Ideally the API will be simple, concerned
primarily with communication to/from the API's users."""


import logging
import endpoints
from datetime import date
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import User, Game, Score
from models import StringMessage, NewGameForm, GameForm, GameKeys, \
    MakeMoveForm, ScoreForms
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
        urlsafe_game_key=messages.StringField(1),)
MAKE_MOVE_REQUEST = endpoints.ResourceContainer(
    MakeMoveForm,
    urlsafe_game_key=messages.StringField(1),)
USER_REQUEST = endpoints.ResourceContainer(user_name=messages.StringField(1),
                                           email=messages.StringField(2))

MEMCACHE_MOVES_REMAINING = 'MOVES_REMAINING'

@endpoints.api(name='hangman', version='v1')
class GuessANumberApi(remote.Service):
    """Game API"""
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user_name).get():
            raise endpoints.ConflictException(
                    'A User with that name already exists!')
        user = User(name=request.user_name, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
                request.user_name))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates new game"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        try:
            game = Game.new_game(
                                    user.key,
                                    request.attempts,
                                    request.min_letters,
                                    request.max_letters
            )
        except ValueError:
            raise endpoints.BadRequestException('Attempts must be 6, 8, or 12!')

        # Use a task queue to update the average attempts remaining.
        # This operation is not needed to complete the creation of a new game
        # so it is performed out of sequence.
        taskqueue.add(url='/tasks/cache_average_attempts')
        return game.to_form('Good luck playing Hangman!')

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='get_game',
                      http_method='GET')
    def get_game(self, request):
        """Return the current game state."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        if game:
            return game.to_form('Time to make a move!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=GameKeys,
                      path='get_user_games',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns websafe keys of all unfinished games by the user"""
        user_name = request.user_name
        user = User.query(User.name==user_name).get()
        games = Game.query(Game.user==user.key).fetch()
        gameKeys = []
        for game in games:
            gameKeys.append(game.key.urlsafe())
        return GameKeys(keys=[key for key in gameKeys])

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='cancel_game',
                      name='cancel_game',
                      http_method='GET')
    def cancel_game(self, request):
        """Cancel a non-completed game. ---"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)

        if game.game_over != True and game.cancelled != True:
            game.cancelled = True
            game.put()
            return StringMessage(message="Game canceled.")
        elif game.game_over == True:
            raise endpoints.BadRequestException("You cannot cancel a game that is over.")
            return StringMessage(message="You cannot cancel a game that is over.")
        elif game.cancelled == True:
            raise endpoints.BadRequestException("This game is already canceled!")
            return StringMessage(message="This game is already canceled!")
        else:
            return StringMessage(message="Something odd happened!")


    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Makes a move. Returns a game state with message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        user = User.query(User.key==game.user).get()

        # set up scoring
        if Score.query(ancestor=game.key).get() == None:
            score = Score(
                    parent=game.key,
                    user_name=user.key,
                    date=date.today(),
                    won=False,
                    complete=False,
                    total_guesses=0
            )
            score.put()

        score = Score.query(ancestor=game.key).get()
        # get these from datastore so they can be updated
        total_guesses = score.total_guesses
        correct_guesses = score.correct_guesses
        incorrect_guesses = score.incorrect_guesses
        not_valid_guesses = score.not_valid_guesses

        if game.game_over:
            return game.to_form('Game already over!')

        # make the guess lowercase, to be safe.
        guess = request.guess.lower()
        target = game.target
        targetLower = target.lower()
        if game.correct_letters == None:
            correct_letters = ''
        else:
            correct_letters = game.correct_letters

        def reveal_word(guess=''):
            """
                convert 'target' word into word with correctly guessed letters
                and underscores for unguessed letters
            """
            # logging.info(target)
            show_target = []
            # logging.info(show_target)
            i = 0 # keep track of what letter we are on / to replace
            for letter in targetLower:
                if letter == guess:
                    # append currently correctly guessed letter
                    # to target_revealed
                    show_target.append(guess)
                    i += 1
                elif letter in correct_letters:
                    # append previously correctly guessed letter(s)
                    # to target_revealed
                    show_target.append(letter)
                    i += 1
                else:
                    # otherwise append an underscore '_'
                    show_target.append(" _ ")
                    i += 1
            # convert show_target (list with correct letters and underscores)
            # into a string
            show_target_string = ''.join(x for x in show_target)
            # set the revealed word in datastore
            game.correct_guesses = show_target_string
            return show_target_string

        # begin evaluating guesses
        # allow solving
        if guess == targetLower:
            game.end_game(True)
            correct_letters = target
            score.solved=True
            score.put()
            return game.to_form(
                        'You solved the puzzle! The correct word is: ' + target
            )
        elif len(guess) == 0:
            score.not_valid_guesses = not_valid_guesses + 1
            score.put()
            msg = "You didn't guess a letter!"
        elif len(guess) > 1:
            score.not_valid_guesses = not_valid_guesses + 1
            score.put()
            msg = 'You cannot guess more than one letter at a time!'
        elif guess in correct_letters:
            score.not_valid_guesses = not_valid_guesses + 1
            score.put()
            msg = "You already correctly guessed this letter!"
        elif guess in game.target:
            # save and log the correct guess so the target word can be revealed
            score.correct_guesses = correct_guesses + 1
            score.put()
            game.correct_letters = reveal_word(guess)
            # check if this letter completed the word
            reveal_word_solve = game.correct_letters
            if reveal_word_solve == target:
                game.end_game(True)
                # game.correct_letters = reveal_word()
                return game.to_form('You win!')
            else:
                msg = 'Correct! Guess another letter.'
                # game.correct_letters = reveal_word()
        else:
            score.incorrect_guesses = incorrect_guesses + 1
            score.put()
            msg = 'Incorrect! That letter is not in the word.'
            game.attempts_remaining -= 1
        # end evaluating guesses
        
        # save msg and guess to game.all_guesses for get_game_history
        if game.all_guesses == None:
            game.all_guesses = ("['Guess: %s', 'Message %s']") % (guess, msg)
        else:
            game.all_guesses += ("[]'Guess: %s', 'Message %s']") % (guess, msg)

        if game.attempts_remaining < 1:
            game.end_game(False)
            return game.to_form(msg + ' Game over!')
        else:
            game.put()
            return game.to_form(msg)

    @endpoints.method(response_message=ScoreForms,
                      path='scores',
                      name='get_scores',
                      http_method='GET')
    def get_scores(self, request):
        """Return all scores"""
        return ScoreForms(items=[score.to_form() for score in Score.query()])

    @endpoints.method(request_message=USER_REQUEST,
                      response_message=ScoreForms,
                      path='scores/user/{user_name}',
                      name='get_user_scores',
                      http_method='GET')
    def get_user_scores(self, request):
        """Returns all of an individual User's scores"""
        user = User.query(User.name == request.user_name).get()
        if not user:
            raise endpoints.NotFoundException(
                    'A User with that name does not exist!')
        scores = Score.query(Score.user == user.key)
        return ScoreForms(items=[score.to_form() for score in scores])

    @endpoints.method(response_message=StringMessage,
                      path='games/average_attempts',
                      name='get_average_attempts_remaining',
                      http_method='GET')
    def get_average_attempts(self, request):
        """Get the cached average moves remaining"""
        return StringMessage(message=memcache.get(MEMCACHE_MOVES_REMAINING) or '')

    @staticmethod
    def _cache_average_attempts():
        """Populates memcache with the average moves remaining of Games"""
        games = Game.query(Game.game_over == False).fetch()
        if games:
            count = len(games)
            total_attempts_remaining = sum([game.attempts_remaining
                                        for game in games])
            average = float(total_attempts_remaining)/count
            memcache.set(MEMCACHE_MOVES_REMAINING,
                         'The average moves remaining is {:.2f}'.format(average))


api = endpoints.api_server([GuessANumberApi])
