# coding = utf-8
import codecs
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

import keyboard
import requests
import win32api
import win32com
import win32com.client
import win32con
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QThread, pyqtSignal, QPoint, QEvent
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu, QAction, qApp, QAbstractItemView, \
    QTableWidgetItem, QFileDialog, QDesktopWidget
from flask import Flask

from CTransaction import CTransaction
from MDXTools.mdict_query import IndexBuilder
from MyHtmlParser import MyHTMLParser
from UI.UI_MainWindow import Ui_MainWindow
from ext import *


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
        # keyboard.remove_all_hotkeys()


    def run(self):
        # keyboard.add_hotkey('ctrl+d',self.handle_crtl_d)
        # keyboard.add_hotkey('ctrl+s',self.handle_crtl_s)
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

    def __init__(self, vParent=None):
        super(TrayIcon, self).__init__(vParent)
        self.switch = True
        self.showMenu(vParent)
        self.other()

    def showMenu(self,vParent):
        # Menu
        self.menu = QMenu(vParent)
        self.switchAction = QAction("Close Transaction", self, triggered=self.switchSolve)
        self.quitAction = QAction("Quit", self, triggered=self.quit)

        self.menu.addAction(self.switchAction)
        self.menu.addAction(self.quitAction)
        self.setContextMenu(self.menu)

    def other(self):
        self.activated.connect(self.iconClied)
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

class CMainApplication(Ui_MainWindow, QtWidgets.QMainWindow):
    def __init__(self):
        super(CMainApplication, self).__init__()

        self.setupUi(self)

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

        # Database widget showed?
        self.databaseShowed=True

        # Init the database
        self.__initDatabase()

        self.initUI()

    def closeEvent(self, vEvent):
        vEvent.ignore()
        self.hide()

    def hideEvent(self, vEvent):
        self.tray.showMessage("title","hide in tray icon")
        self.hide()
        vEvent.ignore()

    def initUI(self):
        # self.setGeometry(300, 300, 300, 220)
        self.setWindowTitle('Dict')

        # AX
        self.__transactionWidget.transactionAx.setControl(u"{8856F961-340A-11D0-A96B-00C04FD705A2}")
        # self.transactionAx.setFocusPolicy(Qt::StrongFocus);//设置控件接收键盘焦点的方式：鼠标单击、Tab键
        self.__transactionWidget.transactionAx.setProperty("DisplayAlerts",False) # 不显示任何警告信息。
        self.__transactionWidget.transactionAx.setProperty("DisplayScrollBars",True) # 显示滚动条

        #self.setMouseTracking(True)
        self.addClipbordListener()
        self.show()

        # self.__transactionWidget.show()
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
            win32api.keybd_event(18,0,0,0)     # Alt
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

            self.__initDatabase()
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
                Transaction=self.__transact(text)

                self.__transaction = Transaction
                self.__word = text

                File=codecs.open('resources/index.html','w','utf-8')
                if Transaction[0]!='<':
                    File.write(HTMLSTATIC1+Transaction+HTMLSTATIC2)
                else:
                    File.write(Transaction)
                File.close()

                # Show the transaction window
                # self.__transactionWidget.transactionBrowser.setText(self.__transaction)
                self.__transactionWidget.transactionAx.dynamicCall("Navigate(str)",BASEDIR+"/resources/index.html")
                self.__transactionWidget.statusLabel.setText("Search Mode")
                CursurPoint = QCursor.pos()
                desktopWidget = QApplication.desktop();
                DesktopPoint=desktopWidget.availableGeometry()
                if CursurPoint.x()+620>DesktopPoint.width():
                    CursurPoint.setX(DesktopPoint.width()-620)
                if CursurPoint.y()+400>DesktopPoint.height():
                    CursurPoint.setY(DesktopPoint.height()-400)
                self.__transactionWidget.move(CursurPoint)
                # self.__transactionWidget.setWindowFlags(self.__transactionWidget.windowFlags() |QtCore.Qt.WindowStaysOnTopHint)
                # self.__transactionWidget.show()
                # self.__transactionWidget.setWindowFlags(QtCore.Qt.Widget)
                self.__transactionWidget.activateWindow()
                self.__transactionWidget.show()
            except Exception as e:
                print(e)

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

    def displayButtonPushed(self):
        if self.databaseShowed:
            self.databaseWidget.hide()
            self.databaseShowed=not self.databaseShowed
            self.displayButton.setText(">>")
            self.resize(500,650)
        else:
            self.databaseWidget.show()
            self.databaseShowed=not self.databaseShowed
            self.displayButton.setText("<<")
            self.resize(1200,650)

    def removeButtonPushed(self):
        if self.databaseWidget.currentRow()==-1:
            pass
        RemoveLists=[]
        for SelectedRange in self.databaseWidget.selectedRanges():
            for SelectIndex in range(SelectedRange.rowCount()):
                Word=self.databaseWidget.item(SelectedRange.topRow()+SelectIndex,2).text()
                try:
                    requests.post(HOST+"/remove",data={'word':Word})
                except:
                    self.statusbar.showMessage("No network!")
                # Remove
                cn = sqlite3.connect(WORDRECORD)
                cu = cn.cursor()
                cu.execute('delete from record where word=?',(Word,))
                cn.commit()
                cn.close()
                RemoveLists.append(SelectedRange.topRow()+SelectIndex)
        RemoveLists.sort(reverse=True)
        for RowIndex in RemoveLists:
            self.databaseWidget.removeRow(RowIndex)

        self.__initCounts()

    def addWordsButtonPushed(self):
        FileName = QFileDialog.getOpenFileName(self,"select your words file","","Txt files(*.txt)")
        Results= self.__parseImportWords(FileName[0])

        # Add words to database
        cn = sqlite3.connect(WORDRECORD)
        cu = cn.cursor()
        for Result in Results:
            Word = Result.get('word')
            Transaction = Result.get('transaction')
            Description = ""

            # Find if it is exist
            cu.execute('select proficiency from record where word=?',(Word,))
            res=cu.fetchone()
            if res is None:
                cu.execute("INSERT INTO record (word, wordTransaction, description, insertTime) "
                           "VALUES (?,?,?,?)", (Word, Transaction, Description, time.time()))
            else:
                ProficiencyIncreament=100 if res[0]+25>100 else 100
                cu.execute("update record set proficiency=? where word = ?",(ProficiencyIncreament,Word))

        cn.commit()
        cn.close()

        self.__initDatabase()

    def synchronizeButtonPushed(self):
        self.__initDatabase()

    def __parseImportWords(self,vFileName):
        File = open(vFileName, 'r', encoding='UTF-16 LE', errors='ignore')
        lines = File.readlines()
        tempList = []
        temp = ""
        flag = 0

        final = []
        word = ""
        transaction = ""

        for line in lines:
            line.encode("utf8")
            if flag == 0:
                pattern0 = re.compile(r'\ufeff(.*\n)')
                match0 = pattern0.match(line)
                temp += match0.group(1)
            else:
                pattern = re.compile(r'\d,')
                match = pattern.match(line)
                if match:
                    tempList.append(temp)
                    temp = ""
                    temp += line
                else:
                    temp += line
            flag += 1
        tempList.append(temp)

        for temp in tempList:
            transaction = ""
            pattern = re.compile(r'\d, (.*?)  (.*)\n')
            match = pattern.match(temp)
            word = match.group(1)
            transction0 = match.group(2)
            transaction += transction0 + "\n"

            end = match.end()
            translationLine = temp[end:]
            translations = translationLine.split("\n\n")
            length = len(translations)
            for i in range(length):
                tmp = translations[i].partition(".")
                transaction += str(i+1) + ". [" + tmp[0] + "]" + tmp[2] + "\n"

            element = {"word": word, "transaction": transaction}
            final.append(element)
        return final

    def __transact(self,vWord):
        try:
            # Dict Parser
            builder = IndexBuilder('MDXData/Oxford.mdx')
            ResultWord = builder.mdx_lookup(vWord)

            # Internet Based Transaction
            if len(ResultWord) == 0:
                TransactionRequest=requests.post(HOST+"/transaction"
                                                 ,data={'word':vWord})
                return json.loads(TransactionRequest.text)
            # Using local dictionary
            else:
                parser = MyHTMLParser(ResultWord[0])
                return parser.getData()

        except Exception as e:
            print(e)

    def __synchronize(self):
        try:
            response=requests.get(HOST+"/sychronize",timeout=10,data={"LocalTime":os.stat(WORDRECORD).st_mtime})
            if response.status_code==200:
                with open(WORDRECORD,'wb') as TargetFile:
                    TargetFile.write(response.content)
                self.statusbar.showMessage("Download Successful")
            elif response.status_code==302:
                with open(WORDRECORD,"rb") as File:
                    data=File.read()
                if requests.post(HOST+"/sychronize",data=data).status_code==200:
                    self.statusbar.showMessage("Upload successful")
                else:
                    self.statusbar.showMessage("Upload Error")
            else:
                QMessageBox.information(self,
                                        "Warning",
                                        "Can't synchronize with remote database, using local mode",
                                        QMessageBox.Yes)
        except:
            QMessageBox.information(self,
                                    "Warning",
                                    "Can't synchronize with remote database, using local mode",
                                    QMessageBox.Yes)

        self.__initCounts()

    def __initCounts(self):
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

    def __initDatabase(self):
        self.databaseWidget.clear()
        self.databaseWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.databaseWidget.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Synchronize
        self.__synchronize()

        cn=sqlite3.connect(WORDRECORD)
        cu=cn.cursor()

        # Get the record
        cu.execute("select insertTime,proficiency,word,description,wordTransaction from record")
        reses=cu.fetchall()
        self.databaseWidget.setRowCount(len(reses))
        self.databaseWidget.setColumnCount(5)
        self.databaseWidget.setHorizontalHeaderItem(0,QTableWidgetItem("Date"))
        self.databaseWidget.setHorizontalHeaderItem(1,QTableWidgetItem("P"))
        self.databaseWidget.setHorizontalHeaderItem(2,QTableWidgetItem("Word"))
        self.databaseWidget.setHorizontalHeaderItem(3,QTableWidgetItem("D"))
        self.databaseWidget.setHorizontalHeaderItem(4,QTableWidgetItem("Transaction"))
        Header = self.databaseWidget.horizontalHeader()
        Header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        Header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        index=0
        for res in reses:
            self.databaseWidget.setItem(index,0,QTableWidgetItem(
                time.strftime("%m-%d", time.localtime(res[0]))))  # Date
            self.databaseWidget.setItem(index,1,QTableWidgetItem(str(res[1]))) # Proficiency
            self.databaseWidget.setItem(index,2,QTableWidgetItem(res[2])) #Word
            self.databaseWidget.setItem(index,3,QTableWidgetItem(res[3])) #wordTransaction
            self.databaseWidget.setItem(index,4,QTableWidgetItem(res[4])) #description

            index+=1
        cn.close()

        # Display details signals
        for x in range(self.databaseWidget.rowCount()):
            self.databaseWidget.item(x,3).setToolTip(self.databaseWidget.item(x,3).text())
            self.databaseWidget.item(x,4).setToolTip(self.databaseWidget.item(x,4).text())

    def __saveData(self, vWord, vTransaction, vDescription):
        try:
            cn = sqlite3.connect(WORDRECORD)
            cu = cn.cursor()

            # Find if it is exist
            cu.execute('select proficiency from record where word=?',(vWord,))
            res=cu.fetchone()
            if res is None:
                cu.execute("INSERT INTO record (word, wordTransaction, description, insertTime) "
                           "VALUES (?,?,?,?)", (vWord, vTransaction, vDescription, time.time()))
            else:
                ProficiencyIncreament=100 if res[0]+5>100 else 100
                cu.execute("update record set proficiency=? where word = ?",(ProficiencyIncreament,vWord))
            cn.commit()
            cn.close()

            return True
        except Exception as e:
            return False

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
        self.__transactionWidget.close()
        self.__initDatabase()
        #self.p.terminate()
        self.tray.setVisible(False)
        # self.tray.close()
        self.close()
        # qApp.__bQuit()
        sys.exit()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        ex = CMainApplication()
        sys.exit(app.exec_())
    except Exception as e:
        print(e)

