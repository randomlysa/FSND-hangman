#!/usr/bin/env python

"""main.py - This file contains handlers that are called by taskqueue and/or
cronjobs."""
import logging

import webapp2
from google.appengine.api import mail, app_identity
from api import HangmanApi

from models import User, Game


class SendReminderEmail(webapp2.RequestHandler):
    def get(self):
        """Send a reminder email to each User with an email about games.
        Called every hour using a cron job"""
        app_id = app_identity.get_application_id()
        users = User.query(User.email != None)
        for user in users:
            # get all games for user
            games = Game.query(ancestor=user.key).fetch()
            unfinished = 0
            for game in games:
                # count games that are not over
                if game.game_over==False:
                    unfinished +=1

            subject = \
                'Reminder! You have %d unfinished hangman games!' \
                % unfinished
            body = \
                'Hello {}, come back and finish one of your hangman games!'\
                .format(user.name)

            # This will send test emails, the arguments to send_mail are:
            # from, to, subject, body
            # check if the user has unfinished games
            if unfinished > 0:
                mail.send_mail(
                    'noreply@{}.appspotmail.com'.format(app_id),
                    user.email,
                    subject,
                    body
                )


class UpdateAverageMovesRemaining(webapp2.RequestHandler):
    def post(self):
        """Update game listing announcement in memcache."""
        HangmanApi._cache_average_attempts()
        self.response.set_status(204)


app = webapp2.WSGIApplication([
    ('/crons/send_reminder', SendReminderEmail),
    ('/tasks/cache_average_attempts', UpdateAverageMovesRemaining),
], debug=True)
