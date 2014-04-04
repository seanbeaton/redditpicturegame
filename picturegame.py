import praw
import random
import string
import time
import requests
import itertools
import sys
import re
from config import config

class Constants:
    TWENTY_MINUTES = 20 * 60
    NO_NEW_POST = 0
    INVALID_POST = 1
    VALID_POST = 2
    IGNORE = set(['and', 'the', 'in', 'or'])

class Bot(object):

    def __init__(self, game_password, current_op, current_post, current_round):
        self.r = praw.Reddit(user_agent='/r/picturegame bot')
        self.r.login(config['USERNAME'], config['PASSWORD'])
        self.game_acc = self.r.get_redditor(config['GAMEACCOUNT'])
        self.game_password = game_password
        self.post_up = True
        self.correct_answer_time = 0.0
        self.current_round = int(current_round)
        self.current_op = current_op
        self.current_post = current_post
        self.checked_comments = set()
        self.round_given = False

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

        # just to make sure we didn't muck up any login data
        self.r.login(config['USERNAME'], config['PASSWORD'])


    def flair_winner(self):
        cur_flair = self.r.get_flair(config['SUBREDDIT'], self.current_op)
        new_flair = ''
        if not cur_flair.get('flair_text', None):
            new_flair = "Round %d" % (self.current_round,)
        else:
            new_flair = cur_flair['flair_text'] + ', ' + str(self.current_round)
            while len(new_flair) >= 64:
                idx = new_flair.find(',')
                new_flair = "Round" + new_flair[idx+1:]
        self.r.set_flair(config['SUBREDDIT'], self.current_op, flair_text=new_flair,
            flair_css_class="winner")


    def remove_last_flair(self):
        cur_flair = self.r.get_flair(config['SUBREDDIT'], self.current_op)
        new_flair = ''
        if not cur_flair.get('flair_text', None):
            new_flair = "Round %d" % (self.current_round,)
        else:
            new_flair = re.sub(", " + str(self.current_round-1), '', cur_flair['flair_text']) + ", Fair Play Award"#removes the part of flair that matches with the last round, and adds a fair play award
            while len(new_flair) >= 64:
                idx = new_flair.find(',')
                new_flair = "Round" + new_flair[idx+1:]
        self.r.set_flair(config['SUBREDDIT'], self.current_op, flair_text=new_flair,
            flair_css_class="winner")


    def win(self, cmt):
        reply = cmt.reply("Congratulations, that was the correct answer! Please continue the game as soon as possible. You have been PM'd instructions for continuing the game.\n\nIf you think someone else should have won this round, you can give them the round by replying '+give round' to their answer.")
        reply.distinguish()
        self.post_up = False
        self.checked_comments = set()
#        self.reset_game_password()
        self.correct_answer_time = time.time()
        # first update the op, then call flair_winner!
        self.current_op = str(cmt.author)
        self.flair_winner()
        self.round_given = False
        self.current_round += 1
        won_post = self.r.get_submission(submission_id=self.current_post)
        self.prev_post = self.current_post
        self.current_post = ''
        won_post.set_flair(flair_text="ROUND OVER", flair_css_class="over")
        subject = "Congratulations, you can post the next round!"
        msg_text = 'The password for /u/%s is %s. DO NOT CHANGE THIS PASSWORD. It will be automatically changed once someone solves your riddle. \
Post the next round and reply to the first correct answer with "+correct". The post must have "[Round %d]" in the title. \ Please put your post up within \
20 minutes starting from now.' % (self.game_acc, self.game_password, self.current_round)
        self.r.send_message(self.current_op, subject, msg_text)


    def give_win(self, comment):
        reply = comment.reply("%s has decided that you should have won this round. Congratulations. Please continue the game as soon as possible. You have been PM'd the intructions to continue the game." % (str(self.current_op),))
        reply.distinguish()
#        self.reset_game_password()
        self.correct_answer_time = time.time()
        # remove the win from the first person, update the op, then call flair_winner!
        self.remove_last_flair()
        self.current_op = str(comment.author)
        self.flair_winner()
        self.round_given = True
        subject = "Congratulations, you can post the next round!"
        msg_text = 'The password for /u/%s is %s. DO NOT CHANGE THIS PASSWORD. It will be automatically changed once someone solves your riddle. \
Post the next round and reply to the first correct answer with "+correct". The post must have "[Round %d]" in the title. \ Please put your post up within \
20 minutes starting from now.' % (self.game_acc, self.game_password, self.current_round)
        self.r.send_message(self.current_op, subject, msg_text)


    def get_random_password(self, size=8):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for x in range(size))

    def correct_answer(self, text):
        text = ''.join(filter(lambda x: x in string.ascii_letters + ' ' + string.digits, text))
        text = itertools.permutations(filter(lambda x: x not in Constants.IGNORE, text.split(' ')))
        for perm in text:
            if ''.join(perm) == self.solution:
                return True
        return False

    def run(self):
        while True:
            if self.post_up:
                # check if any of the comments got it right
                post = self.r.get_submission(submission_id=self.current_post, comment_sort='new')
                for cmt in post.comments:
#                    if cmt.id in self.checked_comments:
#                       break
                    self.checked_comments.add(cmt.id)
                    if str(cmt.author).lower() == str(self.current_op).lower():
                        continue
                    for reply in cmt.replies:
                        if not (str(reply.author).lower() == str(self.game_acc).lower()):
                            continue
                        text = reply.body.lower()
                        if "+correct" in text:
                            self.win(cmt)
                            break



            else:
                # wait for the last winner to give us the new solution and put up the next post
                newest_post, status = self.get_newest_post()
                if status == Constants.NO_NEW_POST:

                    if time.time() - self.correct_answer_time > Constants.TWENTY_MINUTES:
                        subject = "OP inactivity"
                        message = "The current OP, /u/%s, didn't do anything with the account for twenty minutes." % (self.current_op,)
                        self.r.send_message('/r/' + config['SUBREDDIT'], subject, message)
                        subject = "Reminder"
                        message = "Twenty minutes have passed. Please put up a post soon. ^(This message is sent to both your account and the game account.)"
                        self.r.send_message(self.game_acc, subject, message)
                        self.r.send_message(self.current_op, subject, message)
                        self.correct_answer_time = time.time()
                elif status == Constants.INVALID_POST:
                    subject = "Invalid Post"
                    message = "Please resubmit your post and put [Round XXXX] at the beginning."
                    self.r.send_message(self.game_acc, subject, message)
                    newest_post.remove()
                elif status == Constants.VALID_POST:
                    self.current_post = newest_post.id
                    self.post_up = True

            if (not self.post_up and not self.round_given):    #if the next post isn't up yet, see if the previous winner wants to give it to someone else.
                print str(self.prev_post)
                post = self.r.get_submission(submission_id=self.prev_post, comment_sort='new')
                inbox = self.r.get_inbox()
                for (message in inbox):
                    if (message.author = "malz_") and ("+restart" in message.body.lower()):
                        self.text = message.body.split()
                        self.newOP = self.text[1]
                        self.newPW = self.text[2]
                        self.game_acc = self.newOP
                        self.game_password = self.newPW
                for comment in post.comments:
                    for c_reply in comment.replies:
                        if ((str(c_reply.author)).lower() == str(self.current_op).lower()):
                            text = c_reply.body.lower()
                        print text
                        if "+give round" in text:
                            self.give_win(comment)
                            break




            time.sleep(2)



if __name__ == "__main__":
    if len(sys.argv) == 5:
        Bot(*sys.argv[1:]).run()
    else:
        print """Please provide the current password to the picturegame account, \
the current OP, the ID of the current post and the current round
number as CLI argument."""

