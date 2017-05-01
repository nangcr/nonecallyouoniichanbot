#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import json
import logging
import configparser
from reminder import Reminder

import requests

logging.basicConfig(stream=sys.stderr, format='%(asctime)s [%(name)s:%(levelname)s] %(message)s',
                    level=logging.DEBUG if sys.argv[-1] == '-v' else logging.INFO)

rmd = Reminder()

HSession = requests.Session()

help_text = '''输入 /add 小时:分钟 重复天数 待办事项 来设置一个提醒
 例如： /add 08:30 7 收远征
 /clear 可以清除记录
 /list 可以列出已设置的记录'''
add_successd_text = '''添加成功！在接下来的%s天里，每天%s将会提醒你%s'''
clear_successd_text = '''已清除全部记录'''
no_data_text = '''无可奉告'''
list_text = '''在接下来的%s天里，每天%s将会提醒你%s'''
command_err_text = '''命令有误，输入 /help 获取帮助'''


class BotAPIFailed(Exception):
    def __init__(self, ret):
        self.ret = ret
        self.description = ret['description']
        self.error_code = ret['error_code']
        self.parameters = ret.get('parameters')

    def __repr__(self):
        return 'BotAPIFailed(%r)' % self.ret


class TelegramBotClient:
    def __init__(self, apitoken, username=None):
        self.token = apitoken
        if username:
            self.username = username
        else:
            self.username = self.bot_api('getMe')['username']
        self.offset = None
        self.run = True

    def bot_api(self, method, **params):
        for att in range(3):
            try:
                req = HSession.post(('https://api.telegram.org/bot%s/' %
                                     self.token) + method, data=params, timeout=45)
                retjson = req.content
                ret = json.loads(retjson.decode('utf-8'))
                break
            except Exception as ex:
                if att < 1:
                    time.sleep((att + 1) * 2)
                else:
                    raise ex
        if not ret['ok']:
            raise BotAPIFailed(ret)
        return ret['result']

    def parse_cmd(self, text: str):
        t = text.strip().replace('\xa0', ' ').split(' ', 1)
        if not t:
            return None, None
        cmd = t[0].rsplit('@', 1)
        if len(cmd[0]) < 2 or cmd[0][0] != '/':
            return None, None
        if len(cmd) > 1 and cmd[-1] != self.username:
            return None, None
        expr = t[1] if len(t) > 1 else ''
        return cmd[0][1:], expr

    def serve(self, **kwargs):
        '''
        **kwargs is a map for callbacks. For example: {'message': process_msg}
        '''
        current_time = time.strftime("%H:%M", time.localtime())
        while self.run:
            if current_time != time.strftime("%H:%M", time.localtime()):
                current_time = time.strftime("%H:%M", time.localtime())
                for chat_id, rmd_msg in rmd.check(current_time):
                    self.sendMessage(chat_id=chat_id, text=rmd_msg,
                                     parse_mode='Markdown', disable_web_page_preview=True)
            try:
                updates = self.bot_api('getUpdates', offset=self.offset, timeout=30)
            except BotAPIFailed as ex:
                if ex.parameters and 'retry_after' in ex.parameters:
                    time.sleep(ex.parameters['retry_after'])
            except Exception:
                logging.exception('Get updates failed.')
                continue
            if not updates:
                continue
            self.offset = updates[-1]["update_id"] + 1
            for upd in updates:
                for k, v in upd.items():
                    if k == 'update_id':
                        continue
                    elif kwargs.get(k):
                        kwargs[k](self, v)
            time.sleep(.2)

    def __getattr__(self, name):
        return lambda **kwargs: self.bot_api(name, **kwargs)


def message_handler(cli, msg):
    cmd, expr = cli.parse_cmd(msg.get('text', ''))
    if not cmd:
        return
    elif cmd == 'help':
        cli.sendMessage(chat_id=msg['chat']['id'], text=help_text,
                        parse_mode='Markdown', disable_web_page_preview=True)
    elif cmd == 'add':
        try:
            rmd_time, rmd_times, rmd_msg = expr.split()
            rmd_time = time.strftime("%H:%M", time.strptime(rmd_time, "%H:%M"))
            uid = msg['chat']['id']
            rmd.add(uid, rmd_time, int(rmd_times), rmd_msg)
            cli.sendMessage(chat_id=msg['chat']['id'], text=add_successd_text % (
                rmd_times, rmd_time, rmd_msg),
                            parse_mode='Markdown', disable_web_page_preview=True)
            logging.info(' '.join(('New set', str(uid), rmd_time, rmd_times, rmd_msg)))
        except:
            cli.sendMessage(chat_id=msg['chat']['id'], text=command_err_text,
                            parse_mode='Markdown', disable_web_page_preview=True)
    elif cmd == 'clear':
        uid = msg['chat']['id']
        rmd.clear(uid)
        cli.sendMessage(chat_id=msg['chat']['id'], text=clear_successd_text,
                        parse_mode='Markdown', disable_web_page_preview=True)
        logging.info(' '.join((str(uid), 'clear')))
    elif cmd == 'list':
        uid = msg['chat']['id']
        user_list = rmd.list(uid)
        if user_list is None or user_list == []:
            cli.sendMessage(chat_id=msg['chat']['id'], text=no_data_text,
                            parse_mode='Markdown', disable_web_page_preview=True)
        else:
            for rmd_time, rmd_times, rmd_msg in user_list:
                cli.sendMessage(chat_id=msg['chat']['id'], text=list_text % (
                    rmd_times, rmd_time, rmd_msg),
                                parse_mode='Markdown', disable_web_page_preview=True)
    elif cmd == 'start':
        return
    else:
        cli.sendMessage(chat_id=msg['chat']['id'], text=command_err_text,
                        parse_mode='Markdown', disable_web_page_preview=True)


def load_config(filename):
    cp = configparser.ConfigParser()
    cp.read(filename)
    return cp


def main():
    config = load_config('config.ini')
    botcli = TelegramBotClient(
        config['Bot']['apitoken'], config['Bot'].get('username'))
    logging.info('Satellite launched.')
    botcli.serve(message=message_handler)


if __name__ == '__main__':
    main()
