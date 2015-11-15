#!/usr/bin/python

#
# game table:
# game.playerturn = ' ' : waiting for a player to join
# game.playerturn = 'W' : white's turn
# game.playerturn = 'B" : black's turn
# game.playerturn = 'X' : game over
#                 = "A" : game abandoned
#                 = "F" : game forfeited

# White goes first
# Right now the first player to join goes first; this may be randomized


from DocXMLRPCServer import DocCGIXMLRPCRequestHandler
import sys

server = DocCGIXMLRPCRequestHandler()
server.register_introspection_functions()
#server.register_multicall_functions()

#
# Board Defines
#

idle_timeout = 30                        # how often keepalive must be sent
move_timeout = 30                       # you have this many seconds to move

mysql = None

blankrow = " "*8
newboard = blankrow + blankrow + blankrow + '   WB   ' + \
    '   BW   ' + blankrow+blankrow+blankrow


def get_mysql():
    """Get a database cursor for use in a query.a"""
    global mysql
    if mysql: return mysql
    import MySQLdb,_mysql_exceptions
    password = open("/home/domex/mysql_password","r").read().strip()
    mysql = MySQLdb.connect(user='simsong', passwd=password, db='othello',host='127.0.0.1');
    return mysql

def get_cursor():
    return get_mysql().cursor()

def board_str2array(boardstr):
    """Turns a board string into a board array"""
    boardstr = boardstr + (" "*64)
    ret = []
    for row in range(0,8):
        r = []
        for col in range(row*8,row*8+8):
            try:
                r.append(boardstr[col])
            except ValueError:
                r.append(0)
        ret.append(r)
    return ret
            
def board_array2str(boardarray):
    """Turns a board array into a board string"""
    boardstr = ""
    for row in range(0,8):
        for col in range(0,8):
            boardstr += boardarray[row][col]
    return boardstr
            
def board_count(boardarray,color):
    count = 0
    for row in boardarray:
        for col in row:
            if(col==color): count += 1
    return count


# Board is stored in the SQL database as a 64-character string with " " for blank,
# "W" for white, "B" for black

def other_player(p):
    if(p=='W'): return 'B'
    return 'W'

def print_board(board):
    score = {" ":0,"W":0,"B":0}
    print "     0  1  2  3  4  5  6  7 "
    for row in range(0,8):
        sys.stdout.write(" %d: " % row)
        for col in range(0,8):
            sys.stdout.write(" %c " % board[row][col])
            score[board[row][col]] += 1
        sys.stdout.write("\n")
    print "Score W: %d  B: %d " % (score["W"],score["B"])
    print "============="
    
def make_move(board,player,row,col):
    """ Make a move. Returns the new board or None if the move is invalid """
    if board[row][col]!=" ": return None
    import copy
    board = copy.deepcopy(board) # make a local copy
    def count_flips(dx,dy):
        """ Counts the flips starting at row,col for a given direction."""
        count = 0
        r = row; c = col
        while True:
            r += dy
            c += dx
            if r<0 or r>7 or c<0 or c>7: return 0
            if board[r][c]==" ": return 0
            if board[r][c]==player: return count
            count+=1
    def do_flips(dx,dy):
        """ Performs the flips starting at row, col for a given direction."""
        count = count_flips(dx,dy)
        if count==0: return 0
        r = row ; c = col
        while True:
            r += dy
            c += dx
            if board[r][c]==player: return count # we reached the end
            board[r][c] = player           # we didn't reach end, so set
    count = 0
    for dx in range(-1,2):
        for dy in range(-1,2):
            if(dx==0 and dy==0): continue
            count += do_flips(dx,dy)
    if count==0: return None
    board[row][col] = player    # and move here
    return board
            
def all_possible_moves(board,player):
    """ Returns all of the possible moves for player in board """
    moves = []
    for r in range(0,8):
        for c in range(0,8):
            if make_move(board,player,r,c): moves.append((r,c))
    return moves

def random_move(board,player):
    """ Returns a random move for player in board """
    import random
    moves = all_possible_moves(board,player)
    if moves: return moves[random.randint(0,len(moves)-1)]
    return None

def expire_games(c):
    """ Kill the games where either nobody has polled recently """
    c.execute("update games set playerturn='A' where playerturn in ('W','B',' ') and ((now()-whiteAlive > %d) or (now()-blackAlive> %d))" % (idle_timeout,idle_timeout))
    """ Forfeit any games where a player hasn't moved in time """
    c.execute("update games set playerturn='F' where playerturn in ('W','B',' ') and (now()-lastmove > %d)" % move_timeout)
    c.execute("commit;")

def not_idle(c,gameID,playerID):
    """ note that gameID playerID is not idle """
    c.execute("update games set whiteAlive=now() where gameID=%s and white=%s",(gameID,playerID))
    c.execute("update games set blackAlive=now() where gameID=%s and black=%s",(gameID,playerID))
    c.execute("commit;")


################################################################
################################################################
### RPCXML Functions Follow ###


def add(a,b):
    """ Demonstration RPCXML: Adds A and B and returns the sum."""
    return int(a)+int(b)
server.register_function(add)

def sendMessage(gameID,senderID,recipientID,message):
    """ Send a message to senderID from recipientID for game gameID"""
    my = get_mysql()
    c = my.cursor()
    c.execute("insert into messages (gameID,sender,recipient,message,timesent) values (%s,%s,%s,%s,now())",
              (gameID,senderID,recipientID,message))
    my.commit()
    return False
server.register_function(sendMessage)

def getMessages(gameID,playerID):
    """ Gets the messages for playerID in gameID. Returns an array 
    where each element is a (sender,message) array. """
    my = get_mysql()
    c = my.cursor()
    c.execute("select sender,message from messages where gameID=%s and recipient=%s",(gameID,playerID))
    res = c.fetchall()
    c.execute("delete from messages where gameID=%s and recipient=%s",(gameID,playerID))
    not_idle(c,gameID,playerID)
    my.commit()
    return res
server.register_function(getMessages)

def joinGame(playerID):
    """PlayerID requests to join a game. Creates a new game if necessary.
    Returns the GameID of the newly-created game."""
    my = get_mysql()
    # See if there is a game available to join
    c = my.cursor()
    c.execute("lock tables games write")
    expire_games(c)
    # Don't let players play themselves:
    c.execute("select gameID from games where isnull(black) and white!=%s and isnull(playerturn)",(playerID))
    res = c.fetchone()
    if res:
        gameid = res[0]
        c.execute("update games set black=%s,playerturn='W' where gameID=%s",(playerID,gameid))
        my.commit()
        c.execute("unlock tables")
        return gameid
    # Looks like we need to create a new game
    c.execute("insert into games (white,board,whiteAlive) values (%s,%s,now())",(playerID,newboard))
    gameid = c.lastrowid
    c.execute("unlock tables")
    return gameid
server.register_function(joinGame)

def quitGame(playerID,gameID):
    """PlayerID gameID quits the game.
    Returns True. (It really should return True only if the game got quit.)"""
    my = get_mysql()
    c = my.cursor()
    c.execute("lock tables games write")
    c.execute("update games set playerturn='A' where gameID=%s and white=%s",(gameID,playerID))
    c.execute("update games set playerturn='A' where gameID=%s and black=%s",(gameID,playerID))
    c.execute("unlock tables")
    return True
server.register_function(quitGame)

def join(playerID):
    """Legacy name; calls joinGame()"""
    return joinGame(playerID)
server.register_function(join)

def getGameState(gameID):
    """
    Returns the current state of game {@code gameID}. This state will be represented by a
    {@link java.util.Map from  Strings to  Objects with the following entries:
    
          "board": An Integer[8][8] array, where each Integer
                           in the represents a square on the board. A black 
                           cell is represented by 0, a white piece is represented by 
                           1, and a black piece is represented by 2. The convention is that
                           cell (0,0) is the top-left cell, and that cell (3,2) is the cell in
                           the 4th column from the left and the third row down.  
          "player": An  Object which can be safely cast to 
                            Boolean, which will be  true if the current player is
                           White and  false if the current player is Black
          "blackScore": An  Object which can be safely cast to 
                            Integer representing the Black player's current score
          "whiteScore": An  Object which can be safely cast to 
                            Integer representing the White player's current score
          "gameOver": An  Object which can be safely cast to 
                            Boolean, which will be  true if the game has
                           ended. Note: This will be  false when the game is in the 
                           "Waiting for player" state.
          "waitingForOpp": A Boolean which will be  true while the game has only one player.
                           When the second player joins the game, this will be set to false and will remain so permanently.
          "blacksID": A string, holding the  playerID of the Black player. 
          "whitesID": A string holding the  playerID of the White player. 
          "playerturn": A string.
                             "W" = white's turn;
                             "B" = Black's turn;
                             "X" = Game over.
                             "A" = Game abandoned due to inactivity
          "timeleft": An integer of the amount of time left for playerturn to move before the game is forfeit.
   """
    map = {}
    c = get_mysql().cursor()
    expire_games(c)
    c.execute("select gameID,board,playerturn,black,white,lastmove,now() from games where gameID=%s",(gameID))
    (gid,board,playerturn,black,white,lastmove,now) = c.fetchone()
    if(black==None): black=""
    if(white==None): white=""
    if(lastmove==None): lastmove=now
    if(playerturn==None): playerturn=""
    array = board_str2array(board)
    # Recode the array for the broken API
    for r in range(0,8):
        for c in range(0,8):
            if(array[r][c]=='B'): array[r][c]=0
            if(array[r][c]=='W'): array[r][c]=1
            if(array[r][c]==' '): array[r][c]=2
    map['board']  = array
    map['player'] = (playerturn=='W')
    map['blackScore'] = board_count(board,'B')
    map['whiteScore'] = board_count(board,'W')
    map['gameOver']   = (playerturn=='X') or (playerturn=='A')
    map['waitingForOpp'] = (white=="") or (black=="")
    map['blacksID']   = black
    map['whitesID']   = white
    map['playerturn'] = playerturn
    seconds_since_lastmove = (now-lastmove).seconds
    sys.stderr.write("now="+str(now)+" lastmove="+str(lastmove)+" seconds="+str(seconds_since_lastmove))
    map['timeleft']  = move_timeout - seconds_since_lastmove
    return map
server.register_function(getGameState)


def submitMove(gameID,playerID,column,row):
    """
    Submission of a move by player {@code playerID} in game {@code gameID}. Moves are
    represented by the row and column of the cell in which the new piece is placed. The server
    will determine the color of the new piece from the ({@code playerID}, {@code gameID}) pair.
    This method will return {@code true} if the move was valid and {@code false} otherwise.

    gameID   The identifier for move's game
    playerID The identifier for the acting player
    column   The column-number of the newly-placed piece
    row      The row-number of the newly-placed piece

    Returns true if the move is valid, false if it is not.
    See getGameState for how rows and columns are numbered
    """
    my = get_mysql()
    c = my.cursor()
    c.execute("select board,playerturn,white,black from games where gameID=%s and playerturn in ('W','B') and (white=%s or black=%s)",
              (gameID,playerID,playerID))
    r = c.fetchone()
    if not r:
        return False              # not a valid game, or not valid player, or something
    (boardstr,playerturn,white,black) = r

    # Make sure that playerID is appropriate for the player whose turn it is to move
    if(playerturn=='W' and playerID==black): return False
    if(playerturn=='B' and playerID==white): return False

    # Make sure that the move is valid
    boardarray = board_str2array(boardstr)
    new_boardarray = make_move(boardarray,playerturn,row,column)
    if not new_boardarray: return False

    # See if the other player can move now...
    next_player = other_player(playerturn)
    if not all_possible_moves(new_boardarray,next_player):
        next_player = playerturn        # player gets to go again... if player has a move
        if not all_possible_moves(new_boardarray,playerturn):
            # Game is over
            next_player = 'X'
    # Update the database
    new_boardstr = board_array2str(new_boardarray)
    c.execute("update games set board=%s,playerturn=%s,lastmove=now() where gameID=%s",(new_boardstr,next_player,gameID))
    return True
server.register_function(submitMove)
              

def stillAlive(playerID,gameID):
    """Tell the server the playerID is still alive in gameID but has not moved yet
    Returns True if the game is still in progress, False if the game is not in progress anymore"""
    #sys.stderr.write("playerID="+playerID+"\n")
    my = get_mysql()
    c = my.cursor()
    c.execute("select gameID from games where gameID=%s and (white=%s or black=%s)",(gameID,playerID,playerID))
    r = c.fetchone()
    if not r: return False
    not_idle(c,gameID,playerID)
    return True
server.register_function(stillAlive)    

def gamelist(title,where):
    c = mysql.cursor()
    cmd = "select count(*) from games where "+where
    c.execute(cmd)
    m = c.fetchone()
    count = m[0]
    ret = "%s: %d\n" % (title,count)
    if(count>0):
        c.execute("select gameid,white,now()-whiteAlive,black,now()-blackAlive,playerturn from games "+
                  "where %s order by gameid desc limit 10" % where)
        for (gameid,white,idlew,black,idleb,playerturn) in c.fetchall():
            ret += "    gameid: %s   white: %s (idle %s)  black: %s (idle %s) playerturn: %s \n" % \
                   (gameid,white,idlew,black,idleb,playerturn)
    return ret
    

def status():
    """ Returns human-readable status about the server """
    my = get_mysql()
    c = my.cursor()
    expire_games(c)
    ret = ""
    ret += gamelist("Games awaiting a player","playerturn=' '")
    ret += gamelist("Games properly terminated","playerturn='X'")
    ret += gamelist("Games abandoned","playerturn='A'")
    ret += gamelist("Games abandoned","playerturn='F'")
    return ret
server.register_function(status)

def wipe():
    c = get_mysql().cursor()
    c.execute("delete from games");
    c.execute("delete from messages");

def do_random_game(do_print):
    import copy
    board = board_str2array(newboard)
    last_board = board
    if do_print: print "Play a random game:"
    player = 'W'
    skipped = 0
    while True:
        if board:
            last_board=copy.deepcopy(board)
        move = random_move(board,player)
        if not move:
            if skipped>2: break
            skipped += 1
            player = other_player(player)   # swaps player
            continue            
        if do_print: print "making move",move
        board = make_move(board,player,move[0],move[1])
        if do_print: print_board(board)
        player = other_player(player)   # swaps player
    if do_print: print "Game over"
    return last_board

def do_multiple_games(count):
    print "Run %d games" % count
    for i in range(0,count):
        board = do_random_game(False)
        print "Game %d" % i
        print_board(board)
    sys.exit(0)
    
 



def do_test():
    assert board_array2str(board_str2array(newboard))==newboard
    print_board(board_str2array(newboard))
    do_random_game(True)
    sys.exit(0)



if(__name__=="__main__"):
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("-t","--test",action="store_true",help="test")
    parser.add_option("-w","--wipe",action="store_true",help="test")
    parser.add_option("-s","--status",action="store_true",help="test")
    parser.add_option("-r","--repeat",dest="repeat",help="Run multiple games")
    (options,args) = parser.parse_args()
    if options.repeat:
        do_multiple_games(int(options.repeat))
    if options.test:
        do_test()
    if options.wipe:
        wipe()
        print "wiped"
        sys.exit(0)

    if options.status:
        print status()
        sys.exit(0)
    import cgitb; cgitb.enable()            # provides traceback in the event of an error
    server.handle_request()
