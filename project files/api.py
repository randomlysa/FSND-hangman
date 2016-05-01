"""api.py - Create and configure the Game API exposing the resources."""


import textwrap
import endpoints
from protorpc import remote, messages
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb


from models import User, Game, Score
from models import StringMessage, NewGameForm, GameForm, GameKeysForm, \
    MakeMoveForm, ScoreForms, UserRank, UserRankForms, GameHistoryForm
from utils import get_by_urlsafe

NEW_GAME_REQUEST = endpoints.ResourceContainer(NewGameForm)
GET_GAME_REQUEST = endpoints.ResourceContainer(
    urlsafe_game_key=messages.StringField(1),)
MAKE_MOVE_REQUEST = endpoints.ResourceContainer(
    MakeMoveForm,
    urlsafe_game_key=messages.StringField(1),
)
USER_REQUEST = endpoints.ResourceContainer(
    user=messages.StringField(1),
    email=messages.StringField(2)
)
USER_NAME = endpoints.ResourceContainer(
    user_name=messages.StringField(1)
)
HIGH_SCORE_REQUEST = endpoints.ResourceContainer(
    number_of_results=messages.IntegerField(1)
)
MEMCACHE_MOVES_REMAINING = 'MOVES_REMAINING'


@endpoints.api(name='hangman', version='v1')
class HangmanApi(remote.Service):
    """Game API"""
    @endpoints.method(request_message=USER_REQUEST,
                      response_message=StringMessage,
                      path='user',
                      name='create_user',
                      http_method='POST')
    def create_user(self, request):
        """Create a User. Requires a unique username"""
        if User.query(User.name == request.user).get():
            raise endpoints.ConflictException(
                'A User with that name already exists!')
        user = User(name=request.user, email=request.email)
        user.put()
        return StringMessage(message='User {} created!'.format(
            request.user))

    @endpoints.method(request_message=NEW_GAME_REQUEST,
                      response_message=GameForm,
                      path='game',
                      name='new_game',
                      http_method='POST')
    def new_game(self, request):
        """Creates new game"""
        user = User.query(User.name == request.user).get()
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
            raise endpoints.BadRequestException(
                'Attempts must be 6, 9, or 12!'
            )

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
        if game.cancelled:
            return game.to_form('This game has been cancelled.')
        elif game.game_over:
            return game.to_form('This game has ended.')
        elif game:
            return game.to_form('Time to make a move!')
        else:
            raise endpoints.NotFoundException('Game not found!')

    @endpoints.method(request_message=USER_NAME,
                      response_message=GameKeysForm,
                      path='user/{user_name}/games',
                      name='get_user_games',
                      http_method='GET')
    def get_user_games(self, request):
        """Returns websafe keys of all unfinished games by the user"""
        user = request.user_name
        user = User.query(User.name == user).get()
        games = Game.query(Game.user == user.key).fetch()
        game_keys = []
        for game in games:
            if game.game_over is False and game.cancelled is False:
                game_keys.append(game.key.urlsafe())
        return GameKeysForm(keys=[key for key in game_keys])

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=StringMessage,
                      path='user/cancel/{urlsafe_game_key}',
                      name='cancel_game',
                      http_method='DELETE')
    def cancel_game(self, request):
        """Cancel a non-completed game."""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        # user is needed for updating user rank
        user = game.key.parent().get().key

        if game.game_over is not True and game.cancelled is not True:
            game.cancelled = True
            # note in the game history that the game has been cancelled
            game.game_history.append("('guess': 'None', \
                'result': 'Game Cancelled', \
                'remaining': %d)" % game.attempts_remaining)
            game.put()

            # update user's rank - might be affected if % of cancelled games
            # goes over 10%
            difficulty = game.convert_int_to_difficulty(game.attempts_allowed)
            UserRank.set_user_rank(user, difficulty)
            return StringMessage(message="Game cancelled.")
        elif game.game_over is True:
            raise endpoints.BadRequestException(
                "You cannot cancel a game that is over."
            )
            return StringMessage(
                message="You cannot cancel a game that is over."
            )
        elif game.cancelled is True:
            raise endpoints.BadRequestException(
                "This game is already cancelled!"
            )
            return StringMessage(message="This game is already cancelled!")
        else:
            return StringMessage(message="Something odd happened!")

    @endpoints.method(request_message=MAKE_MOVE_REQUEST,
                      response_message=GameForm,
                      path='game/{urlsafe_game_key}',
                      name='make_move',
                      http_method='PUT')
    def make_move(self, request):
        """Guess a letter or attempt to solve! Returns a game state with
        message"""
        game = get_by_urlsafe(request.urlsafe_game_key, Game)
        user = User.query(User.key == game.user).get()
        user_urlsafe = user.key.urlsafe()

        # needed for UserRank.set_user_rank
        difficulty = game.convert_int_to_difficulty(game.attempts_allowed)

        if game.game_over:
            return game.to_form('Game already over!')
        if game.cancelled:
            return game.to_form('This game has been cancelled!')

        # make the guess lowercase, to be safe.
        guess = request.guess.lower()
        target_word = game.target_word
        target_lower = target_word.lower()
        # set game.target_revealed to be a string
        if game.target_revealed is None:
            target_revealed = ''
        else:
            target_revealed = game.target_revealed

        def reveal_word(guess=''):
            """Convert 'target_word' into a string with correctly guessed
            letters and underscores for unguessed letters"""
            show_target_list = []
            i = 0  # keep track of what letter we are on / to replace
            # build the revealed word using correctly guessed letters and
            # underscores for not guessed letters
            for letter in target_lower:
                # if this letter in the target word is the same as the letter
                # that was just guessed
                if letter == guess:
                    # append currently correctly guessed letter
                    # to show_target_list
                    show_target_list.append(guess)
                    i += 1
                elif letter in target_revealed:
                    # append previously correctly guessed letter(s)
                    # to show_target_list
                    show_target_list.append(letter)
                    i += 1
                else:
                    # for letters not yet guessed, append an underscore ' _ '
                    show_target_list.append(" _ ")
                    i += 1
            # convert show_target_list (list with correct letters and
            # underscores) into a string
            show_target_string = ''.join(x for x in show_target_list)
            # set the revealed word in datastore
            game.correct_guesses = show_target_string
            return show_target_string

        # begin evaluating guesses

        # an attempt to solve was correct. game over!
        if guess == target_lower:
            # calculate the letters that were 'guessed' in order to solve
            # the word
            letters_guessed_for_solve = []
            for letter in target_lower:
                # add letters from the target word that were not already
                # guessed and are not already in the letters_guessed list
                # to the list
                if letter not in game.correct_letters and \
                        letter not in letters_guessed_for_solve:
                    letters_guessed_for_solve.append(letter)

            # add the guessed letters to game.correct_letters
            # for scoring purposes
            add_letters = ''.join(x for x in letters_guessed_for_solve)
            game.correct_letters += add_letters

            # add the solve to game.history
            history = (
                "(\
                'guess': %s, \
                'result': 'You solved the puzzle! The correct word \
                    is: %s', \
                'remaining': %d \
                )"
            ) % (guess, target_word, game.attempts_remaining)
            game.game_history.append(history)
            game.put()

            # set game.game_over = True and game.won = True
            game.end_game(
                request.urlsafe_game_key, user_urlsafe, True, difficulty
            )

            target_revealed = target_word
            return game.to_form(
                'You solved the puzzle! The correct word is: ' + target_word
            )
        # an attempt to solve was incorrect. game over!
        elif len(guess) > 4 and guess != target_lower:
            # add the failed solve to game.history
            history = textwrap.dedent(
                "(\
                'guess': %s, \
                'result': 'Your attempt to solve was unsuccessful! Game over! \
                 The correct word is: %s', \
                'remaining': %d \
                )"
            ) % (guess, target_word, game.attempts_remaining)
            game.game_history.append(history)

            # log the incorrect guess
            game.incorrect_letters = guess

            # set game.game_over = True and game.won = False
            game.end_game(
                request.urlsafe_game_key, user_urlsafe, False, difficulty
            )
            msg = "Your attempt to solve was unsuccessful! Game over!"
            return game.to_form(msg)

        # handle miscellaneous errors/mistakes
        elif len(guess) == 0:
            msg = "You didn't guess a letter!"
        # since all words 0 to 4 characters long were removed from the word
        # list, guesses of 1 to 4 characters long can be assumed to be
        # errant guesses, not attempts to solve.
        elif len(guess) > 1 and len(guess) < 5:
            msg = 'You cannot guess more than one letter at a time!'
        elif guess in game.incorrect_letters:
            msg = "You already incorrectly guessed this letter!"
        elif guess in target_revealed:
            msg = "You already correctly guessed this letter!"

        # a letter was guessed correctly!
        elif guess in game.target_word:
            # save and log the correct guess so the target word can be revealed
            game.correct_letters += guess
            game.target_revealed = reveal_word(guess)
            # check if this letter solved the word
            if game.target_revealed == target_word:
                # game won!
                # set game.game_over = True and game.won = True
                game.end_game(
                    request.urlsafe_game_key, user_urlsafe, True, difficulty
                )
                msg = 'Correct! You solved the puzzle!'
                return game.to_form('You win!')
            # the guess was correct but did not solve the word
            else:
                msg = 'Correct! Guess another letter.'

        # a letter was guessed incorrectly
        else:
            msg = 'Incorrect! That letter is not in the word.'
            game.incorrect_letters += guess
            game.attempts_remaining -= 1

        # end evaluating guesses

        """the code below runs in the following cases:
        misc errors guessed, incorrect guess
        it does NOT run for:
        solve correct, solve incorrect, game won by all correct letters guessed
        """

        if game.attempts_remaining < 1:
            # add "Game over" to msg for game history clarity
            msg += " Game over!"

        # save msg and guess to game.game_history for get_game_history
        # set the message for game history
        history = ("('guess': %s, 'result': '%s', 'remaining': %d)") % (
            guess, msg, game.attempts_remaining
        )
        if game.game_history is None:
            game.game_history = history
        else:
            game.game_history.append(history)

        # check if the user has run out of attempts
        if game.attempts_remaining < 1:
            # set game.game_over = True and game.won = False
            game.end_game(
                request.urlsafe_game_key, user_urlsafe, False, difficulty
            )
            return game.to_form(msg)
        # still attempts remaining. keep playing!
        else:
            game.put()
            return game.to_form(msg)

    @endpoints.method(request_message=GET_GAME_REQUEST,
                      response_message=GameHistoryForm,
                      path='game/history/{urlsafe_game_key}',
                      name='get_game_history',
                      http_method='GET')
    def get_game_history(self, request):
        """Return a move-by-move history of a game."""
        game = ndb.Key(urlsafe=request.urlsafe_game_key).get()
        # convert game.game_history from list to string
        history = ', '.join(x for x in game.game_history)
        gh = GameHistoryForm()
        gh.history = history
        gh.check_initialized()
        return gh

    @endpoints.method(response_message=ScoreForms,
                      path='scores',
                      name='get_scores',
                      http_method='GET')
    def get_scores(self, request):
        """Return all scores"""
        scores = Score.query()
        return ScoreForms(items=[score.to_form() for score in scores])

    @endpoints.method(request_message=USER_NAME,
                      response_message=ScoreForms,
                      path='user/scores/{user_name}',
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

    @endpoints.method(request_message=HIGH_SCORE_REQUEST,
                      response_message=ScoreForms,
                      path='highscores',
                      name='get_high_scores',
                      http_method='GET')
    def get_high_scores(self, request):
        """Return high scores for all difficulty levels, sorted high score to
        low"""
        high_scores = Score.query().order(-Score.score)\
            .fetch(request.number_of_results)
        return ScoreForms(items=[score.to_form() for score in high_scores])

    @endpoints.method(response_message=UserRankForms,
                      path='rankings',
                      name='get_user_rankings',
                      http_method='GET')
    def get_user_rankings(self, request):
        """Return user rankings (won/loss %), grouped by difficulty."""
        user_rank = \
            UserRank.query()\
            .order(UserRank.difficulty, -UserRank.performance)
        return UserRankForms(rankings=[rank.to_form() for rank in user_rank])

    @endpoints.method(response_message=StringMessage,
                      path='games/average_attempts',
                      name='get_average_attempts_remaining',
                      http_method='GET')
    def get_average_attempts(self, request):
        """Get the cached average moves remaining"""
        return StringMessage(
            message=memcache.get(MEMCACHE_MOVES_REMAINING) or ''
        )

    @staticmethod
    def _cache_average_attempts():
        """Populates memcache with the average moves remaining of Games"""
        games = Game.query(Game.game_over == False).fetch()
        if games:
            count = len(games)
            total_attempts_remaining = \
                sum([game.attempts_remaining for game in games])
            average = float(total_attempts_remaining) / count
            memcache.set(
                MEMCACHE_MOVES_REMAINING,
                'The average moves remaining is {:.2f}'.format(average)
            )


api = endpoints.api_server([HangmanApi])
