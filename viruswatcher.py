#!/usr/bin/env python3
import json
import logging
import random
import re
import smtplib
import threading
import traceback
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from logging import handlers

import sys
import time
import yaml

name = "viruswatcher"


class email:
    def __init__(self, conf):
        self._logger = logging.getLogger()
        self._conf = conf
        try:
            self._pwd = self._conf['pwd']
        except BaseException as e:
            raise Exception("get email pwd err: {}".format(e))

        try:
            self._user = self._conf['user']
        except BaseException as e:
            raise Exception("get email user err: {}".format(e))
        try:
            self._to = str(self._conf['to']).split(",")
        except BaseException as e:
            raise Exception("get email to err: {}".format(e))
        try:
            self._smtp = self._conf['smtp']
        except BaseException as e:
            raise Exception("get email smtp err: {}".format(e))

    def send(self, subject: str, content: str):
        smtp = smtplib.SMTP(self._smtp)
        smtp.login(self._user, self._pwd)
        try:
            message = MIMEText(content, 'plain', 'utf-8')
            message['From'] = Header(name, 'utf-8')
            message['Subject'] = Header(subject, 'utf-8')
            smtp.sendmail(self._user, self._to, message.as_string())
            self._logger.info("send email {} to {} success".format(subject, self._to))
        except smtplib.SMTPException as e:
            self._logger.error("send email {} to {} fail: {}".format(subject, self._to, e))
        finally:
            smtp.quit()


class tabList:
    text: str
    contentList: []
    extra: str

    def __str__(self):
        return json.dumps(self, default=lambda obj: obj.__dict__,
                          ensure_ascii=False)

    def __hash__(self):
        return hash(self.text) ^ hash("".join(self.contentList)) ^ hash(self.extra)

    def __init__(self, m):
        self.text = m["text"]
        self.contentList = m["contentList"]
        self.extra = m["extra"]


class textLineProps:
    text: str
    label: str

    def __init__(self, m):
        self.text = m["text"]
        self.label = m["label"]

    def __hash__(self):
        return hash(self.text) ^ hash(self.label)

    def __str__(self):
        return json.dumps(self, default=lambda obj: obj.__dict__,
                          ensure_ascii=False)


class timeLine:
    time: str
    textInfo: str
    tabList: []
    textLineProps: textLineProps

    def format(self) -> str:
        content = """{} {}:
            {}
            """.format(self.textLineProps.text, self.textLineProps.label, self.time)
        if self.textInfo:
            content += "总政策: " + self.textInfo
        if self.tabList:
            content += "风险区政策:\n"
            for tl in self.tabList:
                content += "===> " + tl.text + ": " + ",".join(tl.contentList) + ", " + tl.extra + "\n"
        return content + "\n"

    def __str__(self):
        return json.dumps(self, default=lambda obj: obj.__dict__,
                          ensure_ascii=False)

    def __hash__(self):
        h = 0
        for tl in self.tabList:
            h ^= hash(tl)
        return hash(self.textInfo) ^ hash(self.textLineProps) ^ h

    def __init__(self, m):
        self.time = m["time"]
        self.textLineProps = textLineProps(m['textLineProps'])
        self.textInfo = m.get("textInfo")
        self.tabList = []
        tls = m.get("tabList")
        for tl in tls:
            self.tabList.append(tabList(tl))


class watcher:
    def __init__(self, conf):
        self._logger = logging.getLogger()
        self._conf = conf
        self._info_m = {}
        self._last_in = None
        self._last_out = None
        self._email = email(conf['email'])
        try:
            self._url = self._conf["url"]
        except BaseException as e:
            raise Exception("get url err: {}".format(e))
        try:
            self._headers = self._conf["headers"]
        except BaseException as e:
            raise Exception("get headers err: {}".format(e))
        try:
            self._name = self._conf["name"]
        except BaseException as e:
            raise Exception("get name err: {}".format(e))
        return

    def name(self) -> str:
        return self._name

    def analyze(self):
        req = urllib.request.Request(self._url, data=None, headers=self._headers)
        resp = urllib.request.urlopen(req)
        resp = resp.read().decode("utf-8")
        p = re.compile("""jsonp_[0-9]+\\(""")
        s = p.findall(resp)[0]
        resp = resp.replace(s, "")
        resp = resp[:len(resp) - 1]
        resp = json.loads(resp)
        self._logger.info("fetch {} resp code: {}".format(self._name, resp['ResultCode']))
        self._logger.debug("fetch {} resp: {}".format(self._name, json.dumps(resp, ensure_ascii=False)))
        result = resp["Result"][0]
        provider0 = result["DisplayData"]["resultData"]["tplData"]["provider"][0]
        # title = provider0["title"]
        time_line = provider0["timeLine"]
        out_ = timeLine(time_line[0])
        in_ = timeLine(time_line[1])
        self._logger.debug("fetch {} key info: {} ===> {}".format(self._name, out_, in_))
        first = self._last_in is None or self._last_out is None
        if first or hash(self._last_in) != hash(in_) or hash(
                self._last_out) != hash(out_):
            self._last_in = in_
            self._last_out = out_
            suf = "调整"
            if first:
                suf = "提示"
            self._email.send(self._name + suf, out_.format() + "\n" + in_.format())


class viruswatcher:
    def __init__(self, conf: {}):
        self._logger = logging.getLogger()
        self._conf = conf
        self._watchers = []
        try:
            watchers = self._conf["watchers"]
            for rep in watchers:
                self._watchers.append(watcher(rep))
        except BaseException as e:
            raise Exception("get watchers err: {}".format(e))

    def __str__(self):
        return str(self._conf)

    def analyze(self, rep: watcher):
        while 1:
            try:
                rep.analyze()
            except BaseException as e:
                self._logger.info("analyze {} err: {}, {}".format(rep.name(), e, traceback.format_exc()))
            sec = random.randint(30, 300)
            # sec = random.randint(1, 5)
            self._logger.info("fetch {} in {}s...".format(rep.name(), sec))
            time.sleep(sec)

    def start(self):
        for rep in self._watchers:
            t = threading.Thread(target=self.analyze, args=(rep,))
            t.setDaemon(True)
            t.start()
        while 1:
            time.sleep(1000)


def main():
    if len(sys.argv) != 2:
        config_file = "./{}.yaml".format(name)
    else:
        config_file = sys.argv[1]
    with open(config_file, 'r') as f:
        conf = yaml.safe_load(f)
    lev = logging.INFO
    try:
        debug = conf['debug']
    except BaseException as e:
        debug = False
    if debug:
        lev = logging.DEBUG
    hs = []
    file_handler = handlers.TimedRotatingFileHandler(filename="./{}.log".format(name), when='D', backupCount=1,
                                                     encoding='utf-8')
    hs.append(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    hs.append(console_handler)
    logging.basicConfig(level=lev,
                        format='%(asctime)s %(levelname)s %(pathname)s:%(lineno)d %(thread)s %(message)s', handlers=hs)
    logger = logging.getLogger()
    rm = viruswatcher(conf)
    logger.info("{} info: {}".format(name, rm))
    rm.start()


if __name__ == "__main__":
    main()
