# coding = utf-8
import ctypes
import hashlib
import json
import os
import random
import re
import socket
import sqlite3
import sys
import time
import win32gui
from ctypes import wintypes
from html.parser import HTMLParser
from multiprocessing import Process

import requests
import win32api
import win32com
import win32com.client
import win32con
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu, QAction, qApp
from flask import Flask

from CTransaction import CTransaction
from MDXTools.mdict_query import IndexBuilder
from UI.UI_MainWindow import Ui_MainWindow
from ext import *


class MyHTMLParser(HTMLParser):
    def __init__(self):
        super(MyHTMLParser, self).__init__()
        self.data = ''

    def handle_starttag(self, tag, attrs):
        """
        recognize start tag, like <div>
        :param tag:
        :param attrs:
        :return:
        """
        # print("Encountered a start tag:", tag)

    def handle_endtag(self, tag):
        """
        recognize end tag, like </div>
        :param tag:
        :return:
        """
        # print("Encountered an end tag :", tag)

    def handle_data(self, data):
        """
        recognize data, html content string
        :param data:
        :return:text
        """
        if '•' in data:
            if not re.search(r"[a-zA-Z]", data):
                if not len(data)<4:
                    self.data += data + '\n'

    def handle_startendtag(self, tag, attrs):
        """
        recognize tag that without endtag, like <img />
        :param tag:
        :param attrs:
        :return:
        """
        # print("Encountered startendtag :", tag)

    def handle_comment(self, data):
        """

        :param data:
        :return:
        """
        # print("Encountered comment :", data)


class CGlobalHotKCListener(QThread):
    addTrigger = pyqtSignal()
    cancelTrigger = pyqtSignal()

    def __init__(self):
        super(CGlobalHotKCListener, self).__init__()
        self.byref = ctypes.byref
        self.user32 = ctypes.windll.user32

        self.HOTKEYS = {
            1: (ord('D'), win32con.MOD_CONTROL),
            2: (ord('S'), win32con.MOD_CONTROL)
        }

        self.HOTKEY_ACTIONS = {
            1: self.handle_crtl_d,
            2: self.handle_crtl_s
        }

    def handle_crtl_d(self):
        self.addTrigger.emit()
        return True

    def handle_crtl_s(self):
        self.cancelTrigger.emit()
        return True

    def cancelHotKey(self):
        for id in self.HOTKEYS.keys():
            self.user32.UnregisterHotKey(None, id)

    def run(self):
        for id, (vk, modifiers) in self.HOTKEYS.items():
            print("Registering id", id, "for key", vk)
            if not self.user32.RegisterHotKey(None, id, modifiers, vk):
                print("Unable to register id", id)

        try:
            msg = wintypes.MSG()
            while self.user32.GetMessageA(self.byref(msg), None, 0, 0) != 0:
                if msg.message == win32con.WM_HOTKEY:
                    action_to_take = self.HOTKEY_ACTIONS.get(msg.wParam)
                    if action_to_take:
                        action_to_take()

                self.user32.TranslateMessage(self.byref(msg))
                self.user32.DispatchMessageA(self.byref(msg))

        finally:
            self.cancelHotKey()


class TrayIcon(QSystemTrayIcon):
    switchTrigger = pyqtSignal()
    quitTrigger = pyqtSignal()

    def __init__(self, parent=None):
        super(TrayIcon, self).__init__(parent)
        self.switch = True
        self.showMenu()
        self.other()

    def showMenu(self):
        # Menu
        self.menu = QMenu()
        self.switchAction = QAction("Close Transaction", self, triggered=self.switchSolve)
        self.quitAction = QAction("退出", self, triggered=self.quit)

        self.menu.addAction(self.switchAction)
        self.menu.addAction(self.quitAction)
        self.setContextMenu(self.menu)

    def other(self):
        # self.activated.connect(self.iconClied)
        self.setIcon(QIcon("resources/ico.jpg"))
        self.icon = self.MessageIcon()

    def iconClied(self, reason):
        if reason == 2 or reason == 3:
            pw = self.parent()
            if pw.isVisible():
                pw.hide()
            else:
                pw.show()
        # print(reason)

    def switchSolve(self):
        self.switch = not self.switch
        self.switchTrigger.emit()
        self.switchAction.setText("Close Transaction") if self.switch else self.switchAction.setText("Open Transaction")
        self.showMessage("Switch", str(self.switch), self.icon)

    def quit(self):
        # Quit
        self.quitTrigger.emit()

"""
Transaction process
"""

def ServerProcess():
    ServerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ServerSocket.bind((HOST, PORT))
    ServerSocket.listen(1)
    print('Serving HTTP on port %s ...' % PORT)
    while True:
        ClientConnection, ClientAddress = ServerSocket.accept()
        Word = ClientConnection.recv(10240).decode()
        # Dict Parser
        builder = IndexBuilder('MDXData/niujin.mdx')
        ResultWord = builder.mdx_lookup(Word)
        ResultTransaction=""
        if len(ResultWord) == 0:
            # # YouDao
            # appKey = '4fd37dd83c3b4a86'
            # secretKey = '0euicKCl8dubyDXbvwbgYDMF3Rt6TWGf'
            # q = Word
            # fromLang = 'EN'
            # toLang = 'zh-CHS'
            # salt = random.randint(1, 65536)
            # sign = appKey + q + str(salt) + secretKey
            # m1 = hashlib.md5()
            # m1.update(sign.encode())
            # sign = m1.hexdigest()
            # r = requests.post("http://openapi.youdao.com/api"
            #                   , data={"appKey": appKey
            #         , "q": q
            #         , "from": fromLang
            #         , "to": toLang
            #         , "salt": salt
            #         , "sign": sign})
            # result = json.loads(r.text)
            # ResultTransaction = "From YouDao\n" + result["translation"][0]
            # Baidu
            appKey = '20180418000147886'
            secretKey = '8tuKIpNnEoAOzrr8mrPn'
            q = Word
            fromLang = 'en'
            toLang = 'zh'
            salt = random.randint(32768, 65536)
            sign = appKey + q + str(salt) + secretKey
            m1 = hashlib.md5()
            m1.update(sign.encode())
            sign = m1.hexdigest()
            r = requests.post("http://api.fanyi.baidu.com/api/trans/vip/translate"
                              , data={"appid": appKey
                    , "q": q
                    , "from": fromLang
                    , "to": toLang
                    , "salt": salt
                    , "sign": sign})
            result = json.loads(r.text)
            ResultTransaction = "From BaiDu\n" + result["trans_result"][0]['dst']
        else:
            parser = MyHTMLParser()
            parser.feed(ResultWord[0])
            ResultTransaction = parser.data

        ClientConnection.sendall(ResultTransaction.encode())
        ClientConnection.close()

class CMainApplication(Ui_MainWindow, QtWidgets.QMainWindow):
    def __init__(self):
        super(CMainApplication, self).__init__()
        #Transaction Process
        self.p = Process(target=ServerProcess)
        self.p.start()

        self.setupUi(self)
        # # Flask's pid
        # self.serverPID = pid

        # Tray Menu
        self.tray = TrayIcon(self)
        self.tray.show()
        self.tray.switchTrigger.connect(self.__bSwitchTransactionOn)
        self.tray.quitTrigger.connect(self.__bQuit)

        # IS transaction on
        self.__switch = True

        # Hotkey listener
        self.__globalHotKCListener = CGlobalHotKCListener()
        self.__globalHotKCListener.start()
        self.__globalHotKCListener.addTrigger.connect(self.__bStartDescription)
        self.__globalHotKCListener.cancelTrigger.connect(self.__bCancelDescription)

        # Attribute relates on transaction
        self.__descriptionSwitch = False
        self.__word = ''
        self.__transaction = ''

        # Transaction widget
        self.__transactionWidget = CTransaction()
        self.__transactionWidget.cancelSignal.connect(self.__bCancelTransaction)

        self.initUI()

    def closeEvent(self, *args, **kwargs):
        self.__bQuit()

    def initUI(self):
        # self.setGeometry(300, 300, 300, 220)
        self.setWindowTitle('Dict')

        NowTime=time.time()
        Midnight=NowTime-NowTime%86400
        cn=sqlite3.connect(WORDRECORD)
        cu=cn.cursor()
        cu.execute('SELECT * FROM record')
        res=cu.fetchall()
        TotalCount=len(res)
        cu.execute('SELECT * FROM record WHERE insertTime>?',(Midnight,))
        res=cu.fetchall()
        TodayCount=len(res)
        cu.execute("SELECT * FROM record WHERE alreadyOut='false' ")
        res=cu.fetchall()
        IncrementCount=len(res)
        cn.close()
        self.incrementLine.setText(str(IncrementCount))
        self.todayLine.setText(str(TodayCount))
        self.totalLine.setText(str(TotalCount))

        self.addClipbordListener()
        self.show()
        # self.hide()

    def addClipbordListener(self):
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.onClipboradChanged)

    def onClipboradChanged(self):
        # Add description of the word
        if self.__descriptionSwitch == True:
            try:
                self.__globalHotKCListener.quit()
                hld = win32gui.FindWindow("Qt5QWindowIcon", "Form")
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys('%')
                win32gui.SetForegroundWindow(hld)
            except Exception as e:
                print(e)

            reply = QMessageBox.information(self,
                                            "Tips",
                                            "Sure you want to add this words?",
                                            QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.No:
                return
            win32api.keybd_event(18,0,0,0)      # Alt
            win32api.keybd_event(27,0,0,0)     # F
            win32api.keybd_event(27,0,win32con.KEYEVENTF_KEYUP,0)  #释放按键
            win32api.keybd_event(18,0,win32con.KEYEVENTF_KEYUP,0)
            clipboard = QApplication.clipboard()
            description = clipboard.text()

            # Save the word and description
            self.__saveData(self.__word, self.__transaction, description)

            # Tip to window
            self.tray.showMessage("Tips", "Insert Successful", self.tray.icon)
            self.incrementLine.setText(str(int(self.incrementLine.text())+1))
            self.todayLine.setText(str(int(self.todayLine.text())+1))
            self.totalLine.setText(str(int(self.totalLine.text())+1))
            self.__bCancelDescription()
            self.__globalHotKCListener.start()
        else:
            try:
                # Get the text in clipboard
                clipboard = QApplication.clipboard()
                text = clipboard.text()
                if len(text)<2:
                    return
                # text = re.search(r' ?[a-zA-Z ]+ ?', text).group()
                text=text.strip()
                text = str.lower(text)

                # Find the transaction
                ClientSocket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                ClientSocket.connect(("localhost",PORT))
                ClientSocket.send(text.encode())

                TransactionData=ClientSocket.recv(10240).decode()
                self.__transaction = TransactionData
                # self.__transaction = r.text
                self.__word = text

                # Show the transaction window
                self.__transactionWidget.wordLabel.setText(self.__word)
                self.__transactionWidget.transactionBrowser.setText(self.__transaction)
                self.__transactionWidget.statusLabel.setText("Search Mode")
                self.__transactionWidget.show()
            except Exception as e:
                print(e)
            # self.__transactionWidget

    def incrementButtonPushed(self):
        cn=sqlite3.connect(WORDRECORD)
        cu=cn.cursor()
        cu.execute("SELECT word,wordTransaction,description "
                   "FROM record WHERE alreadyOut='false'")
        with open(EXPORTPATH+"increment.txt","w+",encoding='utf-8') as f:
            for res in cu.fetchall():
                f.write(res[0])
                f.write(",")
                f.write(res[1])
                f.write('\n')
                f.write(res[2])
                f.write('@\n')
            f.close()
        cu.execute("UPDATE record SET alreadyOut='true' WHERE alreadyOut='false'")
        cn.commit()
        cn.close()
        self.statusbar.showMessage("Successful!")

    def todayButtonPushed(self):
        NowTime=time.time()
        Midnight=NowTime-NowTime%86400
        cn=sqlite3.connect(WORDRECORD)
        cu=cn.cursor()
        cu.execute("SELECT word,wordTransaction,description "
                   "FROM record WHERE insertTime>?",(Midnight,))
        with open(EXPORTPATH+"today.txt","w+",encoding='utf-8') as f:
            for res in cu.fetchall():
                f.write(res[0])
                f.write(",")
                f.write(res[1])
                f.write('\n')
                f.write(res[2])
                f.write('@\n')
            f.close()
        cu.execute("UPDATE record SET alreadyOut='true' WHERE insertTime>?",(Midnight,))
        cn.commit()
        cn.close()
        self.statusbar.showMessage("Successful!")

    def totalButtonPushed(self):
        cn=sqlite3.connect(WORDRECORD)
        cu=cn.cursor()
        cu.execute("SELECT word,wordTransaction,description "
                   "FROM record")
        with open(EXPORTPATH+"total.txt","w+",encoding='utf-8') as f:
            for res in cu.fetchall():
                f.write(res[0])
                f.write(",")
                f.write(res[1])
                f.write('\n')
                f.write(res[2])
                f.write('@\n')
            f.close()
        cu.execute("UPDATE record SET alreadyOut='true'")
        cn.commit()
        cn.close()
        self.statusbar.showMessage("Successful!")

    def __saveData(self, vWord, vTransaction, vDescription):
        cn = sqlite3.connect(WORDRECORD)
        cu = cn.cursor()
        cu.execute("INSERT INTO record (word, wordTransaction, description, insertTime) "
                   "VALUES (?,?,?,?)", (vWord, vTransaction, vDescription, time.time()))
        cn.commit()
        cn.close()

    def __bCancelTransaction(self):
        self.__transactionWidget.close()

    def __bSwitchTransactionOn(self):
        if self.__switch:
            self.__descriptionSwitch = False
            self.__globalHotKCListener.addTrigger.disconnect()
            self.__globalHotKCListener.cancelTrigger.disconnect()
            self.__globalHotKCListener.quit()
            self.__switch = not self.__switch
            self.clipboard.dataChanged.disconnect()
        else:
            self.__descriptionSwitch = False
            self.__globalHotKCListener.start()
            self.__globalHotKCListener.addTrigger.connect(self.__bStartDescription)
            self.__globalHotKCListener.cancelTrigger.connect(self.__bCancelDescription)
            self.__switch = not self.__switch
            self.clipboard.dataChanged.connect(self.onClipboradChanged)

    def __bStartDescription(self):
        self.__descriptionSwitch = True
        self.__transactionWidget.statusLabel.setText("Insert Mode")

    def __bCancelDescription(self):
        self.__descriptionSwitch = False
        self.__transactionWidget.statusLabel.setText("Search Mode")

    def __bQuit(self):
        self.p.terminate()
        self.tray.setVisible(False)
        # self.tray.close()
        self.__transactionWidget.close()
        self.close()
        # qApp.__bQuit()
        sys.exit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CMainApplication()
    sys.exit(app.exec_())