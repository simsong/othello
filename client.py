#!/usr/bin/python

import xmlrpclib
import sys

server_url = 'http://othello.nitroba.org/game.cgi'
server = xmlrpclib.Server(server_url)

if(__name__=="__main__"):
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("-n","--new",action="store_true",help="Create a new game; returns the gameid")
    parser.add_option("-g","--gameID",dest="gameID",help="Specify the gameID");
    parser.add_option("-q","--quit",action="store_true",help="Quits the game");
    parser.add_option("-p","--playerID",dest="playerID",help="specify the playerID")
    parser.add_option("-m","--messages",action="store_true",help="Check messages for 30 seconds, then exit")
    parser.add_option("-s","--send",dest="message",help="Send a message")
    parser.add_option("-r","--recipientID",dest="recipientID",help="Specify recipient of the message")
    (options,args) = parser.parse_args()
    if options.new:
        print "gameID:",server.joinGame(options.playerID)
        sys.exit(0)
    if options.quit:
        print "Quit Game:",server.quitGame(options.playerID,options.gameID)
        sys.exit(0)
    if options.message:
        server.sendMessage(options.gameID,options.playerID,options.recipientID,options.message)
        sys.exit(0)
    if options.messages:
        import time
        print "Checking messages..."
        for i in range(0,30):
            time.sleep(1)
            print i,server.getMessages(options.gameID,options.playerID)
        sys.exit(0)
