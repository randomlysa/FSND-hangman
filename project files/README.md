#Full Stack Nanodegree Project 4 Refresh

## Set-Up Instructions:
1.  Update the value of application in app.yaml to the app ID you have registered
 in the App Engine admin console and would like to use to host your instance of this sample.
1.  Run the app with the devserver using dev_appserver.py DIR, and ensure it's
 running by visiting the API Explorer - by default localhost:8080/_ah/api/explorer.
1.  (Optional) Generate your client library(ies) with the endpoints tool.
 Deploy your application.



##Game Description:
A simple implementation of hangman. Each game begins with a random 'target'
word with  a maximum number of 'attempts' allowed.
'Guesses' are sent to the `make_move` endpoint which will reply
with either:
  * 'You win' if you guess all the letters, or
  * 'Game over!' if you run out of attempts,
whether the guessed letter was correct or not,
as well messages for the following events:
Empty guess, letter already correctly guessed, letter already incorrectly
guessed, and more than one letter guessed.

After any guess, the following information is returned:
  * attempts_allowed,
  * attempts_remaining,
  * body_parts: items to be drawn based on incorrect guesses and difficulty level,
  * correct_letters: the target word with correct letters shown and incorrect letters represented with an underscore,
  * game_over - if the game is over,
  * incorrect_letters,
  * message: a message about the game or about the last guess,
  * urlsafe_key - the urlsafe game key,
  * user_name.

Many different Hangman games can be played by many different Users at any
given time. Each game can be retrieved or played by using the path parameter
`urlsafe_game_key`.

##Playing the Game:
  * Make a user using the create_user endpoint.
  * Make a new game using the new_game endpoint.
  * Guess letters using the make_move endpoint until you win or run out of guesses!

##Files Included:
 - api.py: Contains endpoints and game playing logic.
 - app.yaml: App configuration.
 - cron.yaml: Cronjob configuration.
 - main.py: Handler for taskqueue handler.
 - models.py: Entity and message definitions including helper methods.
 - utils.py: Helper function for retrieving ndb.Models by urlsafe Key string.

##Endpoints Included:
 - **create_user**
    - Path: 'user'
    - Method: POST
    - Parameters: user_name, email (optional)
    - Returns: Message confirming creation of the User.
    - Description: Creates a new User. user_name provided must be unique. Will
    raise a ConflictException if a User with that user_name already exists.

 - **new_game**
    - Path: 'game'
    - Method: POST
    - Parameters: user_name, max_letters, min_letters, attempts
    - Returns: GameForm with initial game state.
    - Description: Creates a new Game. user_name provided must correspond to an
    existing user - will raise a NotFoundException if not.
    Attempts must be 6 (hard), 9 (medium), or 12 (easy).
    max_letters (default = 12) and min_letters (default = 6) specifies what
    length you want the target word to be.
    Also adds a task to a task queue to update the average moves remaining
    for active games.

 - **get_user_games**
    - Path: 'user/{user_name}/games'
    - Method: GET
    - Parameters: user_name, email
    - Returns: GameKeysForm.
    - Description: Returns websafe keys of all unfinished games by the user

 - **cancel_game**
     - Path: 'user/cancel/{urlsafe_game_key}'
     - Method: POST
     - Parameters: urlsafe_game_key
     - Returns: StringMessage.
     - Description: marks a non-completed game as canceled.

 - **make_move**
    - Path: 'game/{urlsafe_game_key}'
    - Method: PUT
    - Parameters: urlsafe_game_key, guess
    - Returns: GameForm with new game state.
    - Description: Accepts a 'guess' and returns the updated state of the game.
    The score is updated after every move.

 - **get_game_history**
    - Path: 'game/history/{urlsafe_game_key}'
    - Method: GET
    - Parameters: urlsafe_game_key
    - Returns: GameHistoryForm.
    - Description: Returns a move-by-move history of a game.

 - **get_scores**
      - Path: 'scores'
      - Method: GET
      - Parameters: None
      - Returns: ScoreForms.
      - Description: Returns all Scores in the database (unordered).

 - **get_user_scores**
     - Path: 'user/scores/{user_name}'
     - Method: GET
     - Parameters: user_name
     - Returns: ScoreForms.
     - Description: Returns all Scores recorded by the provided player (unordered).
     Will raise a NotFoundException if the User does not exist.

 - **get_high_scores**
      - Path: 'highscores'
      - Method: GET
      - Parameters: number_of_results (optional)
      - Returns: ScoreForms.
      - Description: Return high scores for all users for all difficulty levels

 - **get_game**
    - Path: 'game/{urlsafe_game_key}'
    - Method: GET
    - Parameters: urlsafe_game_key
    - Returns: GameForm with current game state.
    - Description: Returns the current state of a game, which includes:
      attempts_remaining, the target word with correct letters added and
      underscores for letters that have not been guessed, whether the game is
      over, a message, the game urlsafe_key, and the user name.

 - **get_user_rankings**
     - Path: 'rankings'
     - Method: GET
     - Parameters: None
     - Returns: UserRankForms.
     - Description: Return user rankings (won/loss %), grouped by difficulty.

 - **get_average_attempts_remaining**
    - Path: 'games/average_attempts'
    - Method: GET
    - Parameters: None
    - Returns: StringMessage
    - Description: Gets the average number of attempts remaining for all games
    from a previously cached memcache key.


##Models Included:
 - **User**
    - Stores unique user_name and (optional) email address.

 - **Game**
    - Stores unique game states. Associated with User model via KeyProperty.

 - **Score**
    - Records completed games. Associated with User model via KeyProperty.

- **UserRank**
    - Stores user ranks for each difficulty. Associated with User model via
      KeyProperty.

##Forms Included:
 - **GameForm**
    - Representation of a Game's state (urlsafe_key, attempts_remaining,
    correct guesses, game_over flag, message, user_name).
 - **GameKeysForm**
    - Used to return keys of unfinished games per user.
 - **NewGameForm**
    - Used to create a new game (user_name, target, attempts)
 - **MakeMoveForm**
    - Inbound make move form (guess).
 - **ScoreForm**
    - Representation of a completed game's Score (user_name, date, won flag,
    guesses, difficulty, and score for the game).
 - **ScoreForms**
    - Multiple ScoreForm container.
 - **StringMessage**
    - General purpose String container.
 - **UserRankForm**
     - Representation of a user's rank (won/loss%) grouped by difficulty
      levels.
 - **UserRankForms**
     - Multiple UserRanksForm container
 - **GameHistoryForm**
    - Represents a move by move description of a game.
