import praw
import random
import string
import time
import requests
import re
import sys
from config import config

class Constants:
	TWO_HOURS = 2 * 60 * 60
	NO_NEW_POST = 0
	INVALID_POST = 1
	VALID_POST = 2

class Bot(object):

	def __init__(self, game_password, solution, current_op, current_post, current_round):
		self.r = praw.Reddit(user_agent='/r/picturegame bot')
		self.r.login(config['USERNAME'], config['PASSWORD'])
		self.game_acc = self.r.get_redditor(config['GAMEACCOUNT'])
		self.game_password = game_password
		self.post_up = True
		self.correct_answer_time = 0.0
		self.current_round = int(current_round)
		self.current_op = current_op
		self.current_post = current_post
		self.solution = solution
		self.checked_comments = set()

	def get_newest_post(self):
		posts = self.r.get_subreddit(config['SUBREDDIT']).get_new()
		newest_post = posts.next()
		while newest_post.author != self.game_acc:
			newest_post = posts.next()
		title = newest_post.title
		if -1 < title.lower().find("round " + str(self.current_round - 1)) < 3:
			# no new post - the current post has last round's tag
			return (newest_post, Constants.NO_NEW_POST)
		idx = title.lower().find("round " + str(self.current_round))
		if idx == -1:
			# the current post has neither this nor last round's tag
			return (newest_post, Constants.INVALID_POST)
		return (newest_post, Constants.VALID_POST)

	def reset_game_password(self):
		# PRAW does not offer a password change feature. We're doing this manually
		client = requests.session()
		data = {'api_type': 'json', 'user': self.game_acc, 'passwd': self.game_password}
		headers = {'User-Agent': '/r/picturegame bot'}
		response = client.post('https://ssl.reddit.com/api/login', data=data, headers=headers)
		while response.status_code != 200:
			time.sleep(2)
			response = client.post('https://ssl.reddit.com/api/login', data=data, headers=headers)
		modhash = response.json()['json']['data']['modhash']
		new_password = self.get_random_password()
		data = {'api_type': 'json', 'uh': modhash, 'curpass': self.game_password,
				'newpass': new_password, 'verpass': new_password, 'dest': '', 'verify': False}
		response = client.post('http://www.reddit.com/api/update', data=data, headers=headers)
		while response.status_code != 200:
			time.sleep(2)
			response = client.post('http://www.reddit.com/api/update', data=data, headers=headers)
		self.game_password = new_password

		print new_password

		# just to make sure we didn't muck up any login data
		self.r.login(config['USERNAME'], config['PASSWORD'])


	def win(self, cmt):
		cmt.reply("Congratulations, that was the correct answer! Please continue the game as soon as possible. You have been PM'd the new account info.")
		self.post_up = False
		self.checked_comments = set()
		self.solution = ''
		self.reset_game_password()
		self.correct_answer_time = time.time()
		self.current_op = str(cmt.author)
		self.current_round += 1
		won_post = self.r.get_submission(submission_id=self.current_post)
		self.current_post = ''
		won_post.set_flair(flair_text="ROUND OVER")
		subject = "Congratulations, you can post the next round!"
		msg_text = 'The password for /u/%s is %s. DO NOT CHANGE THIS PASSWORD. It will be automatically changed once someone solves your riddle. \
Please send your solution to me via the link in the sidebar, THEN post the next round. The post should have the format "Round %d: ..."' % (self.game_acc, self.game_password, self.current_round)
		self.r.send_message(self.current_op, subject, msg_text)


	def get_random_password(self, size=8):
		chars = string.ascii_letters + string.digits
		return ''.join(random.choice(chars) for x in range(size))

	def run(self):
		while True:
			if self.post_up:
				# check if any of the comments got it right
				print "Entered post_up branch"
				post = self.r.get_submission(submission_id=self.current_post, comment_sort='new')
				for cmt in post.comments:
					if cmt.id in self.checked_comments:
						break
					self.checked_comments.add(cmt.id)
					text = cmt.body.lower()
					if text.startswith('guess: '):
						text = text.lstrip('guess:').replace(' ', '')
						if text == self.solution:
							self.win(cmt)
							break

			else:
				# wait for the last winner to give us the new solution and put up the next post
				print "Entered else branch"
				newest_post, status = self.get_newest_post()
				for msg in self.r.get_unread():
					msg.mark_as_read()
					if (msg.subject.lower() == "round " + str(self.current_round)
					    and str(msg.author) == self.current_op or str(msg.author) == str(self.game_acc)):
						if self.solution:
							subject = "Sorry..."
							message = "But you can't change the password during the round."
						else:
							subject = "Success"
							message = "Password successfully set."
							self.solution = msg.body.lower().replace(' ', '')
						self.r.send_message(self.current_op, subject, message)
				if status == Constants.NO_NEW_POST:
					if time.time() - self.correct_answer_time > Constants.TWO_HOURS:
						#TODO: Handle lazy users
						pass
				elif status == Constants.INVALID_POST:
					subject = "Invalid Post"
					message = "Please resubmit your post and put [Round XXX] at the beginning."
					self.r.send_message(self.current_op, subject, message)
					newest_post.remove()
				elif status == Constants.VALID_POST:
					if self.solution:
						print "pls no"
						self.current_post = newest_post.id
						self.post_up = True
					else:
						subject = "Invalid Post"
						message = "Please set up the solution first before submitting your post. Instructions can be found in the sidebar."
						self.r.send_message(self.current_op, subject, message)
						newest_post.remove()


			time.sleep(2)
					


if __name__ == "__main__":
	if len(sys.argv) != 6:
		print """Please provide the current password to the picturegame account, the current
solution, the current OP, the ID of the current post and the current round
number as CLI argument."""
	Bot(*sys.argv[1:]).run()